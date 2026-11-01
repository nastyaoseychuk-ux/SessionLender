// Enhance both existing messages and messages appended by chat.js.
(() => {
  function formatTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
    const value = Math.floor(seconds);
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
  }

  function icon(playing) {
    return playing
      ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14M16 5v14"/></svg>'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7Z"/></svg>';
  }

  function button(label, className) {
    const control = document.createElement('button');
    control.type = 'button';
    control.className = className;
    control.title = label;
    control.setAttribute('aria-label', label);
    return control;
  }

  function enhance(wrap) {
    const audio = wrap.querySelector('audio');
    if (!audio || wrap.dataset.voiceEnhanced) return;
    wrap.dataset.voiceEnhanced = '1';
    const originalDuration = wrap.querySelector('small');
    const durationHint = Number.parseFloat(originalDuration?.textContent.replace(',', '.')) || 0;
    let started = false;
    const duration = () => Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : durationHint;

    const player = document.createElement('div');
    player.className = 'voice-player';
    const play = button('Відтворити', 'voice-play');
    play.innerHTML = icon(false);
    const seek = document.createElement('input');
    seek.className = 'voice-seek';
    seek.type = 'range';
    seek.min = '0'; seek.max = '1'; seek.step = '0.01'; seek.value = '0';
    seek.setAttribute('aria-label', 'Перемотування голосового повідомлення');
    const menu = button('Швидкість і завантаження', 'voice-menu-toggle');
    menu.textContent = '⋮';
    menu.setAttribute('aria-expanded', 'false');
    const timer = document.createElement('span');
    timer.className = 'voice-timer';
    const options = document.createElement('div');
    options.className = 'voice-options';
    options.hidden = true;
    const speedLabel = document.createElement('label');
    speedLabel.textContent = 'Швидкість ';
    const speed = document.createElement('select');
    speed.setAttribute('aria-label', 'Швидкість відтворення');
    for (const rate of [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2]) {
      const option = document.createElement('option');
      option.value = String(rate); option.textContent = `${rate}×`;
      option.selected = rate === 1;
      speed.append(option);
    }
    speedLabel.append(speed);
    const download = document.createElement('a');
    download.textContent = 'Завантажити';
    download.href = audio.currentSrc || audio.src;
    download.download = '';
    options.append(speedLabel, download);
    player.append(play, seek, menu, timer, options);

    function refresh() {
      const total = duration();
      seek.disabled = total <= 0;
      seek.max = String(total || 1);
      seek.value = String(Math.min(audio.currentTime || 0, total || 1));
      seek.setAttribute('aria-valuetext', `${formatTime(audio.currentTime)} з ${formatTime(total)}`);
      timer.textContent = formatTime(started ? audio.currentTime : total);
      timer.title = started ? 'Поточний таймкод' : 'Тривалість аудіо';
    }

    play.addEventListener('click', async () => {
      if (!audio.paused) { audio.pause(); return; }
      try { await audio.play(); }
      catch { timer.textContent = 'Не вдалося відтворити'; }
    });
    audio.addEventListener('play', () => {
      for (const other of document.querySelectorAll('.chat-voice audio')) {
        if (other !== audio) other.pause();
      }
      started = true;
      play.innerHTML = icon(true);
      play.setAttribute('aria-label', 'Пауза'); play.title = 'Пауза';
      refresh();
    });
    function showPlay() {
      play.innerHTML = icon(false);
      play.setAttribute('aria-label', 'Відтворити'); play.title = 'Відтворити';
      refresh();
    }
    audio.addEventListener('pause', showPlay);
    audio.addEventListener('ended', showPlay);
    for (const event of ['loadedmetadata', 'durationchange', 'timeupdate', 'seeked']) {
      audio.addEventListener(event, refresh);
    }
    audio.addEventListener('error', () => { showPlay(); timer.textContent = 'Аудіо недоступне'; });
    seek.addEventListener('input', () => {
      if (duration() <= 0) return;
      try { audio.currentTime = Number(seek.value); refresh(); }
      catch { timer.textContent = 'Перемотування недоступне'; }
    });
    speed.addEventListener('change', () => { audio.playbackRate = Number(speed.value); });
    menu.addEventListener('click', () => {
      options.hidden = !options.hidden;
      menu.setAttribute('aria-expanded', String(!options.hidden));
    });
    // Keep native controls as a fallback until the custom controls are ready.
    wrap.append(player);
    audio.controls = false;
    audio.hidden = true;
    if (originalDuration) originalDuration.hidden = true;
    refresh();
  }

  function scan(node) {
    if (node.nodeType !== 1) return;
    if (node.matches('.chat-voice')) enhance(node);
    node.querySelectorAll('.chat-voice').forEach(enhance);
  }

  function initialize() {
    const messages = document.getElementById('chatMessages');
    if (!messages) return;
    scan(messages);
    new MutationObserver(records => {
      for (const record of records) for (const node of record.addedNodes) scan(node);
    }).observe(messages, {childList:true, subtree:true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, {once:true});
  else initialize();
})();
