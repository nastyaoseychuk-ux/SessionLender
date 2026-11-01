document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-confirm]').forEach((element) => {
    element.addEventListener('click', (event) => {
      if (!window.confirm(element.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  document.querySelectorAll('textarea[data-autogrow]').forEach((element) => {
    const resize = () => {
      element.style.height = 'auto';
      element.style.height = `${Math.min(element.scrollHeight, 320)}px`;
    };
    element.addEventListener('input', resize);
    resize();
  });

  document.querySelectorAll('[data-autohide]').forEach((element) => {
    if (element.classList.contains('alert-error')) {
      return;
    }
    window.setTimeout(() => {
      element.style.transition = 'opacity .25s ease, transform .25s ease';
      element.style.opacity = '0';
      element.style.transform = 'translateY(-6px)';
      window.setTimeout(() => element.remove(), 260);
    }, 6000);
  });

  const composeDialog = document.getElementById('composeDialog');

  if (composeDialog) {
    const openCompose = () => {
      if (typeof composeDialog.showModal === 'function') {
        composeDialog.showModal();
      }
    };

    document.querySelectorAll('[data-open-compose]').forEach((trigger) => {
      trigger.addEventListener('click', (event) => {
        event.preventDefault();
        openCompose();
      });
    });

    document.querySelectorAll('[data-close-compose]').forEach((button) => {
      button.addEventListener('click', () => composeDialog.close());
    });

    composeDialog.addEventListener('click', (event) => {
      if (event.target === composeDialog) {
        composeDialog.close();
      }
    });

    if (new URLSearchParams(window.location.search).get('compose') === '1') {
      openCompose();
    }
  }

  document.querySelectorAll('[data-image-input]').forEach((input) => {
    const form = input.closest('form');
    if (!form) {
      return;
    }
    const wrap = form.querySelector('[data-preview-wrap]');
    const image = form.querySelector('[data-preview-image]');
    const label = form.querySelector('[data-file-label]');
    let objectUrl = '';

    input.addEventListener('change', () => {
      const file = input.files && input.files[0];
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        objectUrl = '';
      }
      if (!file || !file.type.startsWith('image/')) {
        if (wrap) {
          wrap.hidden = true;
        }
        if (label) {
          label.textContent = 'Додати фото';
        }
        return;
      }
      objectUrl = URL.createObjectURL(file);
      if (image) {
        image.src = objectUrl;
      }
      if (wrap) {
        wrap.hidden = false;
      }
      if (label) {
        label.textContent = file.name.length > 28 ? `${file.name.slice(0, 25)}…` : file.name;
      }
    });
  });

  const likeForms = document.querySelectorAll('[data-like-form]');

  const sendLike = async (form) => {
    const button = form.querySelector('.like-button');
    if (!button) {
      return;
    }
    button.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!response.ok) {
        window.location.reload();
        return;
      }
      const data = await response.json();
      const post = form.closest('.post');
      button.classList.toggle('liked', data.liked);
      button.setAttribute('aria-pressed', data.liked ? 'true' : 'false');
      button.setAttribute('title', data.liked ? 'Прибрати вподобання' : 'Вподобати');
      const count = post ? post.querySelector('[data-like-count]') : null;
      if (count) {
        count.textContent = data.count;
      }
      button.classList.remove('pop');
      void button.offsetWidth;
      button.classList.add('pop');
    } catch (error) {
      form.submit();
    } finally {
      button.disabled = false;
    }
  };

  likeForms.forEach((form) => {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      sendLike(form);
    });
  });

  document.querySelectorAll('[data-post-image]').forEach((image) => {
    image.addEventListener('dblclick', () => {
      const form = image.closest('.post')?.querySelector('[data-like-form]');
      const button = form?.querySelector('.like-button');
      if (form && button && !button.classList.contains('liked')) {
        form.requestSubmit();
      }
    });
  });

  document.querySelectorAll('[data-comment-jump]').forEach((link) => {
    link.addEventListener('click', (event) => {
      const post = link.closest('.post');
      const input = post?.querySelector('.comment-form input[name="text"]');
      if (!input) {
        return;
      }
      event.preventDefault();
      input.focus();
      input.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });

  document.querySelectorAll('[data-tabs]').forEach((root) => {
    const buttons = Array.from(root.querySelectorAll('[data-tab]'));
    const panels = Array.from(root.querySelectorAll('[data-tab-panel]'));
    if (!buttons.length || !panels.length) {
      return;
    }
    root.classList.add('tabs-ready');
    const activate = (name) => {
      buttons.forEach((button) => button.classList.toggle('is-active', button.dataset.tab === name));
      panels.forEach((panel) => panel.classList.toggle('is-active', panel.dataset.tabPanel === name));
    };
    buttons.forEach((button) => {
      button.addEventListener('click', () => activate(button.dataset.tab));
    });
    activate(buttons[0].dataset.tab);
  });

  document.querySelectorAll('[data-copy]').forEach((button) => {
    button.addEventListener('click', async () => {
      const source = button.closest('.copy-field')?.querySelector('[data-copy-source]');
      if (!source) {
        return;
      }
      const original = button.textContent;
      try {
        await navigator.clipboard.writeText(source.value);
      } catch (error) {
        source.select();
        document.execCommand('copy');
      }
      button.textContent = 'Скопійовано';
      window.setTimeout(() => {
        button.textContent = original;
      }, 1800);
    });
  });

  const chatFilter = document.querySelector('[data-chat-filter]');
  if (chatFilter) {
    const rows = Array.from(document.querySelectorAll('[data-chat-row]'));
    const empty = document.querySelector('[data-chat-empty]');
    chatFilter.addEventListener('input', () => {
      const query = chatFilter.value.trim().toLowerCase();
      let visible = 0;
      rows.forEach((row) => {
        const matches = !query || row.textContent.toLowerCase().includes(query);
        row.hidden = !matches;
        if (matches) {
          visible += 1;
        }
      });
      if (empty) {
        const list = document.querySelector('[data-chat-list]');
        empty.hidden = !(list && list.querySelector('[data-chat-row]')) || visible > 0;
      }
    });
  }

  const shortcutsDialog = document.getElementById('shortcutsDialog');
  const openShortcuts = () => {
    if (shortcutsDialog && typeof shortcutsDialog.showModal === 'function') {
      shortcutsDialog.showModal();
    }
  };

  document.querySelectorAll('[data-open-shortcuts]').forEach((button) => {
    button.addEventListener('click', openShortcuts);
  });

  document.querySelectorAll('[data-close-shortcuts]').forEach((button) => {
    button.addEventListener('click', () => shortcutsDialog?.close());
  });

  if (shortcutsDialog) {
    shortcutsDialog.addEventListener('click', (event) => {
      if (event.target === shortcutsDialog) {
        shortcutsDialog.close();
      }
    });
  }

  const isTypingTarget = (target) => {
    if (!(target instanceof HTMLElement)) {
      return false;
    }
    return Boolean(
      target.closest('input, textarea, select, [contenteditable="true"]')
    );
  };

  let pendingGo = false;
  let pendingGoTimer = 0;

  document.addEventListener('keydown', (event) => {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) {
      return;
    }
    if (isTypingTarget(event.target) || (shortcutsDialog && shortcutsDialog.open)) {
      return;
    }

    if (event.key === '?') {
      event.preventDefault();
      openShortcuts();
      return;
    }

    if (event.key === '/') {
      const searchInput = document.querySelector('.search input[type="search"]');
      if (searchInput) {
        event.preventDefault();
        searchInput.focus();
      }
      return;
    }

    const key = event.key.toLowerCase();
    if (pendingGo) {
      window.clearTimeout(pendingGoTimer);
      pendingGo = false;
      const destinations = {
        h: 'home',
        r: 'rooms',
        p: 'people',
        m: 'chats',
        s: 'profile',
        a: 'admin',
        n: 'analyst',
      };
      const destination = destinations[key];
      const link = destination
        ? document.querySelector(`[data-shortcut="${destination}"]`)
        : null;
      if (link) {
        event.preventDefault();
        link.click();
      }
      return;
    }

    if (key === 'g') {
      pendingGo = true;
      pendingGoTimer = window.setTimeout(() => {
        pendingGo = false;
      }, 900);
    }
  });
});

// Friend removal uses the site's dialog; cancelling a follow submits directly.
document.addEventListener('DOMContentLoaded', () => {
  const dialog = document.createElement('dialog');
  dialog.className = 'friend-remove-dialog';
  dialog.setAttribute('aria-labelledby', 'friend-remove-title');
  dialog.setAttribute('aria-describedby', 'friend-remove-description');
  dialog.innerHTML = `
    <h2 id="friend-remove-title">Видалити з друзів?</h2>
    <p id="friend-remove-description" class="muted"></p>
    <div class="friend-remove-actions">
      <button type="button" class="btn btn-ghost" data-friend-cancel autofocus>Скасувати</button>
      <button type="button" class="btn btn-danger-ghost" data-friend-approve>Видалити</button>
    </div>`;
  const style = document.createElement('style');
  style.textContent = `
    .friend-remove-dialog { width:min(420px,calc(100vw - 32px)); box-sizing:border-box;
      padding:28px; border:1px solid var(--border,#2a333b); border-radius:22px;
      background:var(--panel,#12161a); color:var(--text,#eef3f6);
      box-shadow:0 24px 90px #0009; }
    .friend-remove-dialog::backdrop { background:#0009; backdrop-filter:blur(5px); }
    .friend-remove-dialog h2 { margin:0 0 12px; font-size:23px; }
    .friend-remove-dialog p { margin:0; overflow-wrap:anywhere; }
    .friend-remove-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:24px; }
    .friend-remove-actions [data-friend-approve] { color:#ff5c76; border-color:#ff5c7660; }
  `;
  document.head.append(style);
  document.body.append(dialog);
  let pending = null;
  let approved = null;
  document.addEventListener('submit', (event) => {
    const button = event.submitter;
    if (!button || !button.hasAttribute('data-friend-remove')) return;
    if (approved === event.target) {
      approved = null;
      return;
    }
    event.preventDefault();
    if (dialog.open) return;
    pending = { form: event.target, button };
    dialog.querySelector('p').textContent = `Видалити @${button.dataset.friendRemove} зі списку друзів?`;
    dialog.showModal();
    dialog.querySelector('[data-friend-cancel]').focus();
  });
  dialog.querySelector('[data-friend-cancel]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { pending = null; });
  dialog.querySelector('[data-friend-approve]').addEventListener('click', () => {
    const target = pending;
    pending = null;
    dialog.close();
    if (!target || !target.form.isConnected || !target.button.isConnected) return;
    approved = target.form;
    target.form.requestSubmit(target.button);
    approved = null;
  });
});
