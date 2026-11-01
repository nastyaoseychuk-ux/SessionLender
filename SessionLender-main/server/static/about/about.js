/* This page is self-contained: demos never call the application API. */
(() => {
  const copy = {
    uk: {
      pageTitle:'Про проєкт — SessionLender',brandSub:'Приватна мережа',navExperience:'Можливості',navScreens:'Інтерфейс',navDownload:'Завантажити',openApp:'Відкрити ↗',
      heroEyebrow:'МЕНШЕ ШУМУ. БІЛЬШЕ СВОГО.',heroLine1:'Ваші люди.',heroLine2:'Ваш простір.',heroDescription:'Кімнати для близьких і команд. Дописи для свого кола. Розмови, у яких хочеться залишитися.',start:'Увійти у свій простір',tryFirst:'Спершу спробувати',heroFootnote:'Ваше коло визначаєте ви.',sceneRoom:'Місце для ваших ідей',sceneMessage:'Зустрінемося у нашій кімнаті?',sceneInvite:'Ви обираєте, до кого приєднатися',principle1:'Кімнати за інтересами',principle2:'Стрічка свого кола',principle3:'Особисті розмови',
      demoEyebrow:'НЕ ТІЛЬКИ ПОДИВИТИСЯ',demoTitle:'Відчуйте, як це працює.',demoDescription:'Невеликий інтерактивний простір. Спробуйте надіслати повідомлення, прийняти запрошення або змінити кімнату.',demoLabel:'ІНТЕРАКТИВНЕ ДЕМО',tabChat:'Повідомлення',tabInvite:'Запрошення',tabFeed:'Кімнати та стрічка',demoNote:'Демонстраційні дані. Нічого не надсилається на сервер.',online:'онлайн',privateChat:'Особиста розмова',initialMessage:'Привіт! Тут можна просто бути собою.',initialReply:'Саме такого простору й бракувало.',messageLabel:'Повідомлення',messagePlaceholder:'Напишіть щось…',send:'Надіслати',deliveryHint:'Спробуйте: ◷ надсилається → ✓ надіслано → ✓✓ прочитано.',sending:'Надсилається…',sent:'Надіслано',read:'Прочитано',
      invitationHeading:'Новий простір чекає на вас',byChoice:'Лише за вашою згодою',invitationText:'Вас запросив @session до кімнати Studio.',inviteExplanation:'Дописи залишаються прихованими, доки ви не приймете запрошення.',accept:'Прийняти',reject:'Відхилити',reset:'Спробувати ще раз ↺',accepted:'Ви у Studio. Тепер дописи доступні!',rejected:'Запрошення відхилено. Ви не приєдналися до кімнати.',acceptedPreview:'@session: Ласкаво просимо! Тут народжуються наші спільні ідеї.',
      feedHeading:'У кожного кола — свій ритм',membersOnly:'Для учасників кімнати',like:'Вподобати',studioPost:'Зберігаємо натхнення і перетворюємо маленькі ідеї на щось більше.',friendsPost:'Наші плани на вихідні: менше поспіху, більше часу разом.',workPost:'Одна команда, спільний контекст. Обговоримо наступний крок тут.',
      galleryEyebrow:'ЗНАЙОМИЙ. АЛЕ ВАШ.',galleryTitle:'Зазирніть усередину.',darkGalleryNote:'Справжні скриншоти проєкту. Натисніть на зображення, щоб роздивитися деталі.',lightGalleryNote:'Концепти світлої теми, створені за допомогою ШІ. Це прев’ю, а не готова тема застосунку.',slide1:'Вхід і реєстрація',slide2:'Стрічка ваших кімнат',slide3:'Особисті та групові розмови',slide4:'Повідомлення у своєму ритмі',concept:'Концепт світлої теми',screenshot:'Скриншот проєкту',previous:'Попередній',next:'Наступний',close:'Закрити',lightTheme:'Світла тема',darkTheme:'Темна тема',
      valuesEyebrow:'ПРОСТІР ІЗ СЕНСОМ',valuesTitle:'Залиште місце для важливого.',valuesDescription:'SessionLender поєднує спілкування й дописи в невеликих спільнотах. Не все має бути для всіх.',value1Title:'Власне коло',value1Text:'Кімнати об’єднують близьких, друзів і команди. Доступ до дописів мають їхні учасники.',value2Title:'Ваше рішення',value2Text:'Запрошення не додає вас автоматично. Приєднуйтеся, коли самі цього хочете.',value3Title:'Зручний контакт',value3Text:'Особисті й групові чати, файли, голосові повідомлення, реакції та сповіщення — в одному місці.',
      downloadEyebrow:'ПРОДОВЖУЙТЕ У СВОЄМУ ТЕМПІ',downloadTitle:'Ваш простір — поруч.',downloadDescription:'Відкрийте у браузері або встановіть Android-додаток.',androidDescription:'Завантажити APK',androidNote:'Тестова збірка · Android 8+',desktopTitle:'Для комп’ютера',desktopDescription:'Завантажити тестовий файл',desktopNote:'Тестовий EXE · ще не фінальний клієнт',driveNote:'Файли розміщені на Google Drive. Сервіс може попросити підтвердити завантаження.',github:'Проєкти автора на GitHub',footerText:'Ваші люди. Ваші кімнати. Ваш ритм.',footerLogin:'Увійти →',
    },
    en: {
      pageTitle:'About — SessionLender',brandSub:'Private network',navExperience:'Experience',navScreens:'Interface',navDownload:'Download',openApp:'Open app ↗',
      heroEyebrow:'LESS NOISE. MORE OF YOUR OWN.',heroLine1:'Your people.',heroLine2:'Your space.',heroDescription:'Rooms for friends and teams. Posts for your circle. Conversations you want to stay in.',start:'Step into your space',tryFirst:'Try it first',heroFootnote:'You decide who is in your circle.',sceneRoom:'A place for your ideas',sceneMessage:'Meet you in our room?',sceneInvite:'Choose the spaces you join',principle1:'Rooms around shared interests',principle2:'A feed for your circle',principle3:'Personal conversations',
      demoEyebrow:'MORE THAN A FIRST LOOK',demoTitle:'Get a feel for it.',demoDescription:'A little interactive space. Send a message, respond to an invitation, or switch between rooms.',demoLabel:'INTERACTIVE DEMO',tabChat:'Messages',tabInvite:'Invitations',tabFeed:'Rooms & feed',demoNote:'Illustrative demo data. Nothing is sent to the server.',online:'online',privateChat:'Personal conversation',initialMessage:'Hey! You can just be yourself here.',initialReply:'Exactly the kind of space I was missing.',messageLabel:'Message',messagePlaceholder:'Say something…',send:'Send',deliveryHint:'Try it: ◷ sending → ✓ sent → ✓✓ read.',sending:'Sending…',sent:'Sent',read:'Read',
      invitationHeading:'A new space is waiting',byChoice:'Only with your consent',invitationText:'@session invited you to the Studio room.',inviteExplanation:'Posts stay hidden until you accept the invitation.',accept:'Accept',reject:'Decline',reset:'Try again ↺',accepted:'You are in Studio. The posts are now available!',rejected:'Invitation declined. You have not joined the room.',acceptedPreview:'@session: Welcome! This is where our shared ideas begin.',
      feedHeading:'Every circle has its own rhythm',membersOnly:'For room members',like:'Like',studioPost:'Collecting inspiration and turning small ideas into something bigger.',friendsPost:'Our weekend plan: less rushing, more time together.',workPost:'One team, shared context. Let’s discuss our next step here.',
      galleryEyebrow:'FAMILIAR. BUT YOURS.',galleryTitle:'Take a look inside.',darkGalleryNote:'Real project screenshots. Select an image to explore the details.',lightGalleryNote:'AI-generated light theme concepts. These are previews, not an available app theme.',slide1:'Sign in & registration',slide2:'A feed for your rooms',slide3:'Personal & group conversations',slide4:'Messages at your own pace',concept:'Light theme concept',screenshot:'Project screenshot',previous:'Previous',next:'Next',close:'Close',lightTheme:'Light theme',darkTheme:'Dark theme',
      valuesEyebrow:'A SPACE WITH PURPOSE',valuesTitle:'Make room for what matters.',valuesDescription:'SessionLender brings conversations and posts together in small communities. Not everything needs to be for everyone.',value1Title:'Your own circle',value1Text:'Rooms bring friends, loved ones and teams together. Their posts are accessible to room members.',value2Title:'Your decision',value2Text:'An invitation does not add you automatically. Join when it feels right for you.',value3Title:'Stay connected',value3Text:'Personal and group chats, files, voice messages, reactions and notifications — in one place.',
      downloadEyebrow:'KEEP YOUR OWN PACE',downloadTitle:'Your space. Always close.',downloadDescription:'Open in your browser or install the Android app.',androidDescription:'Download APK',androidNote:'Test build · Android 8+',desktopTitle:'For your computer',desktopDescription:'Download test file',desktopNote:'Test EXE · not the final desktop client',driveNote:'Files are hosted on Google Drive. You may be asked to confirm your download.',github:'The author’s projects on GitHub',footerText:'Your people. Your rooms. Your rhythm.',footerLogin:'Sign in →',
    },
  };
  const $ = id => document.getElementById(id);
  function readPreference(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
  }
  function savePreference(key, value) {
    try { localStorage.setItem(key, value); } catch (_) { /* Private mode still works. */ }
  }
  let language = readPreference('sl-about-language', 'uk') === 'en' ? 'en' : 'uk';
  const requestedLanguage = new URLSearchParams(location.search).get('lang');
  if (['uk', 'en'].includes(requestedLanguage)) language = requestedLanguage;
  let theme = document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
  let activeSlide = 0;
  let inviteState = 'pending';
  let deliveryState = null;
  let activeRoom = 'studio';
  let liked = false;
  let messageSequence = 0;
  const text = key => copy[language][key] || key;
  const cards = Array.from(document.querySelectorAll('[data-slide]'));
  const dialog = $('galleryDialog');

  function translatePage() {
    document.documentElement.lang = language;
    document.title = text('pageTitle');
    document.querySelector('meta[name="description"]').content = text('heroDescription');
    document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = text(node.dataset.i18n); });
    document.querySelectorAll('[data-placeholder]').forEach(node => { node.placeholder = text(node.dataset.placeholder); });
    document.querySelectorAll('[data-label]').forEach(node => { node.setAttribute('aria-label', text(node.dataset.label)); });
    $('languageToggle').textContent = language === 'uk' ? 'EN' : 'UA';
    $('languageToggle').setAttribute('aria-label', language === 'uk' ? 'Switch to English' : 'Перемкнути на українську');
    updateThemeLabel();
    updateInvitation();
    updatePost();
    updateDelivery();
    updateGallery();
  }
  function updateThemeLabel() {
    $('themeToggle').setAttribute('aria-label', text(theme === 'dark' ? 'lightTheme' : 'darkTheme'));
    $('themeToggle').setAttribute('aria-pressed', String(theme === 'light'));
    $('themeIcon').textContent = theme === 'dark' ? '☀' : '☾';
    const note = $('galleryNote');
    note.textContent = text(theme === 'dark' ? 'darkGalleryNote' : 'lightGalleryNote');
  }
  function setTheme(nextTheme) {
    theme = nextTheme;
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#0a0d10' : '#f6f9fb';
    savePreference('sl-about-theme', theme);
    updateThemeLabel();
    updateGallery();
  }
  $('languageToggle').addEventListener('click', () => {
    language = language === 'uk' ? 'en' : 'uk';
    savePreference('sl-about-language', language);
    translatePage();
  });
  $('themeToggle').addEventListener('click', () => setTheme(theme === 'dark' ? 'light' : 'dark'));

  // Accessible tabs: mouse, keyboard arrows, Home and End.
  const tabs = Array.from(document.querySelectorAll('[data-demo]'));
  function selectDemo(name, focus = false) {
    tabs.forEach(tab => {
      const selected = tab.dataset.demo === name;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      $(tab.getAttribute('aria-controls')).hidden = !selected;
      if (selected && focus) tab.focus();
    });
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectDemo(tab.dataset.demo));
    tab.addEventListener('keydown', event => {
      let target;
      if (event.key === 'ArrowRight') target = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') target = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') target = 0;
      if (event.key === 'End') target = tabs.length - 1;
      if (target !== undefined) { event.preventDefault(); selectDemo(tabs[target].dataset.demo, true); }
    });
  });

  function updateDelivery() {
    $('demoDelivery').textContent = text(deliveryState || 'deliveryHint');
  }
  $('demoChatForm').addEventListener('submit', event => {
    event.preventDefault();
    const input = $('demoText');
    const value = input.value.trim();
    if (!value) return;
    const sequence = ++messageSequence;
    const bubble = document.createElement('div');
    bubble.className = 'demo-bubble mine';
    const body = document.createElement('span');
    body.textContent = value;
    const time = document.createElement('small');
    time.textContent = new Date().toLocaleTimeString(language === 'uk' ? 'uk-UA' : 'en-GB', {hour:'2-digit', minute:'2-digit'}) + ' ';
    const receipt = document.createElement('em');
    receipt.textContent = '◷';
    time.append(receipt); bubble.append(body, time);
    const messages = $('demoMessages');
    messages.append(bubble);
    while (messages.children.length > 24) messages.firstElementChild.remove();
    messages.scrollTop = messages.scrollHeight;
    input.value = ''; input.focus();
    deliveryState = 'sending'; updateDelivery();
    window.setTimeout(() => {
      receipt.textContent = '✓';
      if (sequence === messageSequence) { deliveryState = 'sent'; updateDelivery(); }
    }, 550);
    window.setTimeout(() => {
      receipt.textContent = '✓✓';
      if (sequence === messageSequence) { deliveryState = 'read'; updateDelivery(); }
    }, 1400);
  });

  function updateInvitation() {
    const accepted = inviteState === 'accepted';
    $('inviteExplanation').textContent = text(accepted ? 'acceptedPreview' : 'inviteExplanation');
    $('inviteResult').textContent = inviteState === 'pending' ? '' : text(accepted ? 'accepted' : 'rejected');
    $('acceptDemo').disabled = $('rejectDemo').disabled = inviteState !== 'pending';
  }
  $('acceptDemo').addEventListener('click', () => { inviteState = 'accepted'; updateInvitation(); });
  $('rejectDemo').addEventListener('click', () => { inviteState = 'rejected'; updateInvitation(); });
  $('resetInvite').addEventListener('click', () => { inviteState = 'pending'; updateInvitation(); });

  function updatePost() {
    const labels = {studio:'Studio', friends:'Friends', work:'Work'};
    $('postArt').dataset.room = activeRoom;
    $('postArt').querySelector('.post-art-label').textContent = labels[activeRoom];
    $('postArt').querySelector('span').textContent = {studio:'✦',friends:'✿',work:'↗'}[activeRoom];
    $('postAuthor').textContent = '@session · ' + labels[activeRoom];
    $('postText').textContent = text(activeRoom + 'Post');
    $('likeCount').textContent = String(12 + Number(liked));
    $('demoLike').setAttribute('aria-pressed', String(liked));
    $('demoLike').querySelector('[aria-hidden]').textContent = liked ? '♥' : '♡';
  }
  document.querySelectorAll('[data-room]').forEach(button => {
    button.addEventListener('click', () => {
      activeRoom = button.dataset.room; liked = false;
      document.querySelectorAll('.room-switch button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      updatePost();
    });
  });
  $('demoLike').addEventListener('click', () => { liked = !liked; updatePost(); });

  // Stacked gallery, keyboard navigation, swipe and full-size viewing.
  function updateGallery() {
    cards.forEach((card, index) => {
      let offset = (index - activeSlide + cards.length) % cards.length;
      if (offset > 2) offset -= cards.length;
      card.style.setProperty('--offset', offset);
      card.style.setProperty('--distance', Math.abs(offset));
      card.classList.toggle('active', index === activeSlide);
      card.tabIndex = index === activeSlide ? 0 : -1;
      card.setAttribute('aria-hidden', String(index !== activeSlide));
      const image = card.querySelector('img');
      image.src = theme === 'light' ? image.dataset.light : image.dataset.dark;
      image.alt = text('slide' + (index + 1)) + ' — ' + text(theme === 'light' ? 'concept' : 'screenshot');
      card.setAttribute('aria-label', image.alt);
    });
    document.querySelectorAll('[data-dot]').forEach((dot, index) => {
      if (index === activeSlide) dot.setAttribute('aria-current', 'true');
      else dot.removeAttribute('aria-current');
      dot.setAttribute('aria-label', text('slide' + (index + 1)));
    });
    $('slideNumber').textContent = '0' + (activeSlide + 1) + ' / 04';
    $('slideTitle').textContent = text('slide' + (activeSlide + 1));
    const image = cards[activeSlide].querySelector('img');
    $('expandedImage').src = image.src;
    $('expandedImage').alt = image.alt;
    $('expandedCaption').textContent = image.alt;
  }
  function moveGallery(direction) {
    activeSlide = (activeSlide + direction + cards.length) % cards.length;
    updateGallery();
  }
  $('galleryPrev').addEventListener('click', () => moveGallery(-1));
  $('galleryNext').addEventListener('click', () => moveGallery(1));
  $('dialogPrev').addEventListener('click', () => moveGallery(-1));
  $('dialogNext').addEventListener('click', () => moveGallery(1));
  $('closeGallery').addEventListener('click', () => dialog.close());
  document.querySelectorAll('[data-dot]').forEach(dot => dot.addEventListener('click', () => { activeSlide = Number(dot.dataset.dot); updateGallery(); }));
  let pointerX = null, suppressClickUntil = 0;
  const gallery = $('gallery');
  gallery.addEventListener('pointerdown', event => { pointerX = event.clientX; });
  gallery.addEventListener('pointerup', event => {
    if (pointerX !== null && Math.abs(event.clientX - pointerX) > 45) {
      moveGallery(event.clientX < pointerX ? 1 : -1);
      suppressClickUntil = Date.now() + 300;
    }
    pointerX = null;
  });
  gallery.addEventListener('pointercancel', () => { pointerX = null; });
  cards.forEach(card => card.addEventListener('click', () => {
    if (Date.now() < suppressClickUntil) return;
    updateGallery();
    if (typeof dialog.showModal === 'function') dialog.showModal();
  }));
  gallery.addEventListener('keydown', event => {
    if (['ArrowLeft','ArrowRight'].includes(event.key)) {
      event.preventDefault(); moveGallery(event.key === 'ArrowLeft' ? -1 : 1); cards[activeSlide].focus();
    }
  });
  dialog.addEventListener('keydown', event => {
    if (['ArrowLeft','ArrowRight'].includes(event.key)) { event.preventDefault(); moveGallery(event.key === 'ArrowLeft' ? -1 : 1); }
  });
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  if (!reducedMotion.matches) {
    window.setInterval(() => {
      if (!document.hidden && !dialog.open && !gallery.matches(':hover') && !gallery.contains(document.activeElement)) moveGallery(1);
    }, 6500);
  }

  function updateProgress() {
    const available = document.documentElement.scrollHeight - window.innerHeight;
    const progress = available > 0 ? window.scrollY / available : 0;
    document.querySelector('.scroll-progress').style.transform = `scaleX(${Math.min(1, Math.max(0, progress))})`;
  }
  window.addEventListener('scroll', updateProgress, {passive:true});
  window.addEventListener('resize', updateProgress);
  if ('IntersectionObserver' in window) {
    document.documentElement.classList.add('js-reveal');
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => { if (entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target); } });
    }, {threshold:0.08});
    document.querySelectorAll('.reveal').forEach(node => observer.observe(node));
  }
  translatePage();
  setTheme(theme);
  updateProgress();
})();
