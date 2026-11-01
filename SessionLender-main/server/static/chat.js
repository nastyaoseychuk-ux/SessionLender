document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-chat-poll]');
  if (!root) {
    return;
  }

  const list = document.getElementById('chatMessages');
  const form = root.querySelector('[data-chat-form]');
  const state = { last: root.dataset.last || '' };
  const canModerate = root.dataset.canModerate === '1';
  const csrfToken = (document.cookie.split('; ').find((item) => item.startsWith('csrftoken=')) || '').split('=')[1] || '';

  const scrollToBottom = () => {
    list.scrollTop = list.scrollHeight;
  };

  const buildIcon = (name) => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.classList.add('icon');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `#${name}`);
    svg.append(use);
    return svg;
  };

  const buildAvatar = (message) => {
    let avatar;
    if (message.avatar) {
      avatar = document.createElement('img');
      avatar.src = message.avatar;
      avatar.alt = `Аватар @${message.author}`;
      avatar.loading = 'lazy';
    } else {
      avatar = document.createElement('span');
      avatar.textContent = message.initials;
    }
    avatar.classList.add('avatar');
    return avatar;
  };

  const buildAttachment = (attachment) => {
    if (attachment.kind === 'image') {
      const link = document.createElement('a');
      link.className = 'chat-attachment-image';
      link.href = attachment.url;
      link.target = '_blank';
      link.rel = 'noopener';
      const image = document.createElement('img');
      image.src = attachment.url;
      image.alt = attachment.name;
      image.loading = 'lazy';
      link.append(image);
      return link;
    }

    if (attachment.kind === 'voice') {
      const wrap = document.createElement('div');
      wrap.className = 'chat-voice';
      const audio = document.createElement('audio');
      audio.controls = true;
      audio.preload = 'metadata';
      audio.src = attachment.url;
      wrap.append(audio);
      if (attachment.duration) {
        const duration = document.createElement('small');
        duration.textContent = `${Math.round(attachment.duration)} с`;
        wrap.append(duration);
      }
      return wrap;
    }

    const link = document.createElement('a');
    link.className = 'chat-file';
    link.href = attachment.url;
    const text = document.createElement('span');
    const name = document.createElement('b');
    name.textContent = attachment.name;
    const size = document.createElement('small');
    size.textContent = attachment.size_display;
    text.append(name, size);
    link.append(buildIcon('i-file'), text);
    return link;
  };

  const buildDeleteForm = (message) => {
    const deleteForm = document.createElement('form');
    deleteForm.className = 'chat-message-actions';
    deleteForm.method = 'post';
    deleteForm.action = root.dataset.deleteTemplate.replace('999999999', String(message.id));

    const token = document.createElement('input');
    token.type = 'hidden';
    token.name = 'csrfmiddlewaretoken';
    token.value = csrfToken;

    const button = document.createElement('button');
    button.className = 'icon-button icon-button-xs';
    button.type = 'submit';
    button.title = 'Видалити повідомлення';
    button.setAttribute('aria-label', 'Видалити повідомлення');
    button.append(buildIcon('i-close'));

    deleteForm.append(token, button);
    deleteForm.addEventListener('submit', (event) => {
      if (!window.confirm('Видалити це повідомлення?')) {
        event.preventDefault();
      }
    });
    return deleteForm;
  };

  const buildMessage = (message) => {
    const wrapper = document.createElement('div');
    wrapper.className = `chat-message${message.mine ? ' mine' : ''}`;
    wrapper.dataset.id = String(message.id);

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';

    const head = document.createElement('div');
    head.className = 'chat-bubble-head';

    const author = document.createElement('strong');
    author.textContent = `@${message.author}`;
    const time = document.createElement('small');
    time.textContent = message.time;

    if (message.mine) {
      const receipt = document.createElement('span');
      receipt.className = `chat-receipt${message.read ? ' is-read' : ''}`;
      receipt.textContent = message.read ? '✓✓' : '✓';
      receipt.title = message.read ? 'Прочитано' : 'Надіслано';
      time.append(' ', receipt);
    }

    head.append(author, time);
    bubble.append(head);

    if (message.attachments && message.attachments.length) {
      const attachments = document.createElement('div');
      attachments.className = 'chat-attachments';
      message.attachments.forEach((attachment) => {
        attachments.append(buildAttachment(attachment));
      });
      bubble.append(attachments);
    }

    if (message.text) {
      const text = document.createElement('p');
      text.textContent = message.text;
      bubble.append(text);
    }

    wrapper.append(buildAvatar(message), bubble);

    if (message.mine || canModerate) {
      wrapper.append(buildDeleteForm(message));
    }
    return wrapper;
  };

  // Older pages and new-message polling use independent cursors.
  let historyLoading = false;
  let hasEarlier = root.dataset.hasEarlier === '1';
  let pollLoading = false;
  const historyButton = document.createElement('button');
  historyButton.type = 'button';
  historyButton.className = 'btn btn-ghost btn-small';
  historyButton.textContent = 'Завантажити старіші повідомлення';
  historyButton.hidden = !hasEarlier;
  historyButton.setAttribute('aria-live', 'polite');
  list.before(historyButton);

  function insertInOrder(message) {
    if (list.querySelector(`[data-id="${message.id}"]`)) return false;
    const next = Array.from(list.children).find(
      node => Number(node.dataset.id) > message.id
    );
    list.insertBefore(buildMessage(message), next || null);
    return true;
  }

  async function loadHistory() {
    if (!hasEarlier || historyLoading || !root.dataset.historyUrl) return;
    const first = list.querySelector('[data-id]');
    if (!first) return;
    historyLoading = true;
    historyButton.disabled = true;
    historyButton.textContent = 'Завантаження історії…';
    const url = new URL(root.dataset.historyUrl, location.origin);
    url.searchParams.set('before', first.dataset.id);
    try {
      const response = await fetch(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!response.ok || response.redirected) throw new Error('History unavailable');
      const data = await response.json();
      // Capture the visible anchor AFTER the request: the user can scroll while waiting.
      const anchor = Array.from(list.querySelectorAll('[data-id]')).find(
        node => node.getBoundingClientRect().bottom > list.getBoundingClientRect().top
      ) || first;
      const anchorTop = anchor.getBoundingClientRect().top;
      const oldScrollTop = list.scrollTop;
      const oldHeight = list.scrollHeight;
      data.messages.forEach(insertInOrder);
      list.scrollTop = oldScrollTop + list.scrollHeight - oldHeight;
      list.scrollTop += anchor.getBoundingClientRect().top - anchorTop;
      hasEarlier = Boolean(data.has_more);
      historyButton.hidden = !hasEarlier;
      historyButton.textContent = 'Завантажити старіші повідомлення';
    } catch (error) {
      historyButton.textContent = 'Не вдалося завантажити. Повторити';
    } finally {
      historyLoading = false;
      historyButton.disabled = false;
    }
  }

  list.style.overflowAnchor = 'auto';
  historyButton.addEventListener('click', loadHistory);
  list.addEventListener('scroll', () => {
    if (list.scrollTop <= 80) loadHistory();
  }, { passive: true });

  function fitChatViewport() {
    const viewport = window.visualViewport;
    const height = viewport ? viewport.height : window.innerHeight;
    document.body.style.setProperty('--chat-viewport-height', `${height}px`);
    const nav = document.querySelector('.mobile-nav');
    const navHeight = nav ? nav.getBoundingClientRect().height : 0;
    document.body.style.setProperty('--chat-nav-height', `${navHeight}px`);
  }
  fitChatViewport();
  window.addEventListener('resize', fitChatViewport);
  window.visualViewport?.addEventListener('resize', fitChatViewport);
  const mobileNav = document.querySelector('.mobile-nav');
  if (mobileNav && typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(fitChatViewport).observe(mobileNav);
  }

  const poll = async () => {
    // Не опитуємо сервер, коли вкладка/вікно приховані (менеджер вікон ПК-додатка
    // тримає чати відкритими цілодобово — раніше це давало ~20 запитів/хв на вікно).
    if (pollLoading || document.hidden) return;
    pollLoading = true;
    const followLatest = list.scrollHeight - list.scrollTop - list.clientHeight < 100;
    const url = new URL(root.dataset.chatPoll, window.location.origin);
    if (state.last) {
      url.searchParams.set('after', state.last);
    }
    try {
      const response = await fetch(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      let appended = false;
      data.messages.forEach((message) => {
        if (list.querySelector(`[data-id="${message.id}"]`)) {
          return;
        }
        appended = insertInOrder(message) || appended;
      });
      if (data.messages.length) {
        const empty = document.getElementById('chatEmpty');
        if (empty) {
          empty.remove();
        }
      }
      if (data.last) {
        state.last = data.last;
      }
      if (appended && followLatest) {
        scrollToBottom();
      }
    } catch (error) {
      if (window.console) {
        console.warn('Не вдалося оновити чат', error);
      }
    } finally {
      pollLoading = false;
    }
  };

  if (form) {
    const textarea = form.querySelector('textarea[name="text"]');
    const sendButton = form.querySelector('.chat-send');
    const attachmentInput = form.querySelector('[data-attachment-input]');
    const preview = form.querySelector('[data-attachment-preview]');
    const voiceInput = form.querySelector('[data-voice-input]');
    const voiceDurationInput = form.querySelector('[data-voice-duration]');
    const voiceToggle = form.querySelector('[data-voice-toggle]');
    const recordingBar = form.querySelector('[data-recording]');
    const recordingTime = form.querySelector('[data-recording-time]');
    const recordingCancel = form.querySelector('[data-recording-cancel]');
    const voiceError = root.querySelector('[data-voice-error]');
    const supportsDataTransfer = typeof DataTransfer === 'function';
    const supportsRecording = Boolean(
      navigator.mediaDevices &&
        navigator.mediaDevices.getUserMedia &&
        typeof MediaRecorder !== 'undefined'
    );

    let selectedFiles = [];
    let previewUrls = [];
    let voiceFile = null;
    let voiceUrl = '';
    let mediaRecorder = null;
    let recordingStream = null;
    let recordingTimer = 0;
    let recordingStartedAt = 0;
    let recordingChunks = [];
    let discardRecording = false;
    let isRecording = false;

    let recordingPending = false;
    const hasPayload = () => Boolean((textarea && textarea.value.length) || selectedFiles.length || voiceFile);
    const updateComposeAction = () => {
      if (!sendButton) return;
      const send = hasPayload();
      const label = isRecording ? 'Зупинити запис' : send ? 'Надіслати повідомлення' : 'Записати голосове повідомлення';
      sendButton.type = !isRecording && send ? 'submit' : 'button';
      sendButton.title = label;
      sendButton.setAttribute('aria-label', label);
      sendButton.setAttribute('aria-pressed', String(isRecording));
      sendButton.querySelector('use')?.setAttribute('href', isRecording ? '#i-stop' : send ? '#i-send' : '#i-mic');
      sendButton.disabled = recordingPending || (!isRecording && !send && !supportsRecording);
    };

    const formatSize = (bytes) => {
      if (bytes < 1024) {
        return `${bytes} Б`;
      }
      if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} КБ`;
      }
      return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
    };

    const showVoiceError = (message) => {
      if (!voiceError) {
        return;
      }
      voiceError.textContent = message;
      voiceError.hidden = !message;
    };

    const clearPreviewUrls = () => {
      previewUrls.forEach((url) => URL.revokeObjectURL(url));
      previewUrls = [];
    };

    const setInputFiles = (input, files) => {
      if (!input || !supportsDataTransfer) {
        return;
      }
      const transfer = new DataTransfer();
      files.forEach((file) => transfer.items.add(file));
      input.files = transfer.files;
    };

    const syncAttachmentInput = () => {
      setInputFiles(attachmentInput, selectedFiles);
    };

    const removeSelectedFile = (index) => {
      selectedFiles.splice(index, 1);
      syncAttachmentInput();
      renderPreview();
    };

    const removeVoice = () => {
      voiceFile = null;
      if (voiceUrl) {
        URL.revokeObjectURL(voiceUrl);
        voiceUrl = '';
      }
      setInputFiles(voiceInput, []);
      if (voiceDurationInput) {
        voiceDurationInput.value = '';
      }
      renderPreview();
    };

    const renderPreview = () => {
      if (!preview) {
        return;
      }
      clearPreviewUrls();
      if (voiceUrl) {
        URL.revokeObjectURL(voiceUrl);
        voiceUrl = '';
      }
      preview.textContent = '';

      selectedFiles.forEach((file, index) => {
        const chip = document.createElement('span');
        chip.className = 'chat-preview-chip';
        if (file.type.startsWith('image/')) {
          const image = document.createElement('img');
          const url = URL.createObjectURL(file);
          previewUrls.push(url);
          image.src = url;
          image.alt = '';
          chip.append(image);
        } else {
          chip.append(buildIcon('i-file'));
        }
        const label = document.createElement('span');
        label.textContent = `${file.name} · ${formatSize(file.size)}`;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.title = 'Прибрати файл';
        remove.setAttribute('aria-label', `Прибрати ${file.name}`);
        remove.textContent = '×';
        remove.addEventListener('click', () => removeSelectedFile(index));
        chip.append(label, remove);
        preview.append(chip);
      });

      if (voiceFile) {
        const chip = document.createElement('span');
        chip.className = 'chat-preview-chip';
        const audio = document.createElement('audio');
        audio.controls = true;
        audio.preload = 'metadata';
        voiceUrl = URL.createObjectURL(voiceFile);
        audio.src = voiceUrl;
        const label = document.createElement('span');
        label.textContent = 'Голосове повідомлення';
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.title = 'Прибрати голосове';
        remove.setAttribute('aria-label', 'Прибрати голосове повідомлення');
        remove.textContent = '×';
        remove.addEventListener('click', removeVoice);
        chip.append(audio, label, remove);
        preview.append(chip);
      }

      preview.hidden = !selectedFiles.length && !voiceFile;
      updateComposeAction();
    };

    const updateRecordingTime = () => {
      if (!recordingTime) {
        return;
      }
      const total = Math.max(0, Math.floor((Date.now() - recordingStartedAt) / 1000));
      const minutes = String(Math.floor(total / 60)).padStart(2, '0');
      const seconds = String(total % 60).padStart(2, '0');
      recordingTime.textContent = `${minutes}:${seconds}`;
    };

    const resetRecorderUi = () => {
      window.clearInterval(recordingTimer);
      recordingTimer = 0;
      isRecording = false;
      if (recordingBar) {
        recordingBar.hidden = true;
      }
      if (voiceToggle) {
        voiceToggle.classList.remove('is-recording');
        voiceToggle.setAttribute('aria-pressed', 'false');
        const label = voiceToggle.querySelector('span');
        if (label) {
          label.textContent = 'Голос';
        }
        const use = voiceToggle.querySelector('use');
        if (use) {
          use.setAttribute('href', '#i-mic');
        }
      }
      updateComposeAction();
      if (recordingStream) {
        recordingStream.getTracks().forEach((track) => track.stop());
        recordingStream = null;
      }
    };

    const stopRecording = () => {
      if (!mediaRecorder || mediaRecorder.state === 'inactive') {
        resetRecorderUi();
        return;
      }
      mediaRecorder.stop();
      isRecording = false;
      window.clearInterval(recordingTimer);
      recordingTimer = 0;
      if (recordingBar) {
        recordingBar.hidden = true;
      }
    };

    const cancelRecording = () => {
      discardRecording = true;
      stopRecording();
    };

    const startRecording = async () => {
      showVoiceError('');
      if (!supportsRecording) {
        showVoiceError('Ваш браузер не підтримує запис голосу.');
        return;
      }
      try {
        recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (error) {
        showVoiceError('Немає доступу до мікрофона. Дозвольте запис у налаштуваннях браузера.');
        return;
      }

      const mimeCandidates = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/ogg;codecs=opus',
        'audio/mp4',
      ];
      const mimeType = mimeCandidates.find((type) => MediaRecorder.isTypeSupported(type)) || '';
      mediaRecorder = mimeType
        ? new MediaRecorder(recordingStream, { mimeType })
        : new MediaRecorder(recordingStream);
      recordingChunks = [];
      discardRecording = false;
      recordingStartedAt = Date.now();
      updateRecordingTime();

      mediaRecorder.addEventListener('dataavailable', (event) => {
        if (event.data && event.data.size) {
          recordingChunks.push(event.data);
        }
      });

      mediaRecorder.addEventListener('stop', () => {
        const elapsed = Math.max(1, Math.round((Date.now() - recordingStartedAt) / 1000));
        const type = (mediaRecorder && mediaRecorder.mimeType) || 'audio/webm';
        const extension = type.includes('ogg') ? 'ogg' : type.includes('mp4') ? 'm4a' : 'webm';
        const chunks = recordingChunks;
        recordingChunks = [];
        if (!discardRecording && chunks.length) {
          const blob = new Blob(chunks, { type });
          voiceFile = new File([blob], `voice-${Date.now()}.${extension}`, { type });
          setInputFiles(voiceInput, [voiceFile]);
          if (voiceDurationInput) {
            voiceDurationInput.value = String(elapsed);
          }
          renderPreview();
        }
        discardRecording = false;
        resetRecorderUi();
      });

      mediaRecorder.start();
      isRecording = true;
      if (recordingBar) {
        recordingBar.hidden = false;
      }
      if (voiceToggle) {
        voiceToggle.classList.add('is-recording');
        voiceToggle.setAttribute('aria-pressed', 'true');
        const label = voiceToggle.querySelector('span');
        if (label) {
          label.textContent = 'Стоп';
        }
        const use = voiceToggle.querySelector('use');
        if (use) {
          use.setAttribute('href', '#i-stop');
        }
      }
      recordingTimer = window.setInterval(updateRecordingTime, 500);
    };

    if (attachmentInput) {
      attachmentInput.addEventListener('change', () => {
        const incoming = Array.from(attachmentInput.files || []);
        incoming.forEach((file) => {
          const duplicate = selectedFiles.some(
            (item) =>
              item.name === file.name &&
              item.size === file.size &&
              item.lastModified === file.lastModified
          );
          if (!duplicate) {
            selectedFiles.push(file);
          }
        });
        syncAttachmentInput();
        renderPreview();
      });
    }

    if (voiceToggle) {
      voiceToggle.addEventListener('click', async () => {
        if (isRecording) {
          stopRecording();
        } else if (!hasPayload() && !recordingPending) {
          recordingPending = true;
          updateComposeAction();
          try { await startRecording(); }
          finally { recordingPending = false; updateComposeAction(); }
        }
      });
    }
    updateComposeAction();

    if (recordingCancel) {
      recordingCancel.addEventListener('click', cancelRecording);
    }

    if (textarea) {
      textarea.rows = 1;
      textarea.addEventListener('input', updateComposeAction);
      textarea.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          if (typeof form.requestSubmit === 'function') {
            form.requestSubmit();
          } else {
            form.submit();
          }
        }
      });
    }

    form.addEventListener('submit', (event) => {
      if (!hasPayload() && !isRecording) {
        event.preventDefault();
        return;
      }
      if (isRecording) {
        event.preventDefault();
        showVoiceError('Спочатку зупиніть запис голосового повідомлення.');
        return;
      }
      showVoiceError('');
      if (sendButton) {
        sendButton.disabled = true;
      }
    });
  }

  scrollToBottom();
  window.setInterval(poll, 3000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) poll();  // наздоганяємо повідомлення одразу після повернення
  });
});
