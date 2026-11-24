// Общие сценарии интерфейса.
(() => {
  // Окно бронирования поверх календаря на компьютере (макет 25).
  // Ссылка на форму подгружает ту же страницу и показывает её в <dialog>; без скрипта и на телефоне — обычная страница.
  const desktop = window.matchMedia('(min-width: 1024px)');
  const isFormLink = (link) => /^\/events\/(new|\d+\/edit)\/$/.test(new URL(link.href, location.href).pathname);

  document.addEventListener('click', async (event) => {
    const link = event.target.closest('a[href]');
    if (!link || !desktop.matches || !window.HTMLDialogElement || event.defaultPrevented) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (link.origin !== location.origin || !isFormLink(link) || document.querySelector('.booking-dialog')) return;
    if (document.querySelector('[data-booking]')) return; // уже на странице формы
    event.preventDefault();
    try {
      const response = await fetch(link.href, { credentials: 'same-origin', headers: { 'X-Requested-With': 'dialog' } });
      if (!response.ok || response.redirected) throw new Error('form');
      const page = new DOMParser().parseFromString(await response.text(), 'text/html').querySelector('[data-booking]');
      if (!page) throw new Error('form');
      const dialog = document.createElement('dialog');
      dialog.className = 'booking-dialog';
      dialog.setAttribute('aria-label', page.querySelector('h1')?.textContent || 'Встреча');
      dialog.append(document.importNode(page, true));
      document.body.append(dialog);
      dialog.querySelectorAll('[data-dialog-close]').forEach((close) => close.addEventListener('click', (e) => { e.preventDefault(); dialog.close(); }));
      dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
      dialog.addEventListener('close', () => dialog.remove());
      dialog.showModal();
      window.initBookingForm?.(dialog.querySelector('[data-booking]'));
      dialog.querySelector('input[name=title]')?.focus();
    } catch {
      location.href = link.href;
    }
  });
})();

(() => {
  // Шторки поверх текущей страницы (макеты 28, 29, 31): ссылка с data-sheet подгружает форму в <dialog>.
  document.addEventListener('click', async (event) => {
    const link = event.target.closest('a[data-sheet]');
    if (!link || !window.HTMLDialogElement || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    try {
      const response = await fetch(link.href, { credentials: 'same-origin' });
      if (!response.ok || response.redirected) throw new Error('sheet');
      const page = new DOMParser().parseFromString(await response.text(), 'text/html').querySelector('[data-sheet-page]');
      if (!page) throw new Error('sheet');
      const dialog = document.createElement('dialog');
      dialog.className = 'sheet-dialog sheet-modal';
      dialog.append(document.importNode(page, true));
      document.body.append(dialog);
      dialog.querySelectorAll('[data-dialog-close]').forEach((close) => close.addEventListener('click', (e) => { e.preventDefault(); dialog.close(); }));
      dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
      dialog.addEventListener('close', () => dialog.remove());
      dialog.showModal();
      setupTemporaryPassword(dialog);
      dialog.querySelector('input:not([type=hidden])')?.focus();
    } catch {
      location.href = link.href;
    }
  });

  // Временный пароль (макет 31): повтор заполняется сам, кнопка придумывает другой.
  const WORDS = ['sad', 'les', 'most', 'reka', 'park', 'svet', 'dom', 'gora', 'pole', 'utro', 'zvezda', 'luna'];
  const pick = () => WORDS[crypto.getRandomValues(new Uint32Array(1))[0] % WORDS.length];
  function setupTemporaryPassword(root) {
    const first = root.querySelector('[name=new_password1]'), second = root.querySelector('input[type=hidden][name=new_password2]');
    if (!first || !second) return;
    const sync = () => { second.value = first.value; };
    first.addEventListener('input', sync);
    root.querySelector('[data-generate-password]')?.addEventListener('click', () => {
      first.value = `${pick()}-${pick()}-${1000 + (crypto.getRandomValues(new Uint32Array(1))[0] % 9000)}`;
      sync();
      first.focus();
    });
    sync();
  }
  setupTemporaryPassword(document);

  // «Пароль сброшен» (макет 32) открывается сразу; «Скопировать» кладёт пароль в буфер.
  document.querySelectorAll('dialog[data-open-on-load]').forEach((dialog) => dialog.showModal?.());
  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy]');
    if (!button) return;
    const source = button.closest('dialog, section')?.querySelector('[data-copy-source]');
    try { await navigator.clipboard.writeText(source.textContent.trim()); button.textContent = 'Скопировано'; } catch { window.getSelection().selectAllChildren(source); }
  });

  // Тема в профиле: как в системе, светлая, тёмная.
  const themeSelect = document.querySelector('[data-theme-select]');
  if (themeSelect) {
    try { themeSelect.value = localStorage.getItem('theme') || ''; } catch {}
    themeSelect.addEventListener('change', () => {
      const value = themeSelect.value;
      if (value) document.documentElement.dataset.theme = value; else delete document.documentElement.dataset.theme;
      try { if (value) localStorage.setItem('theme', value); else localStorage.removeItem('theme'); } catch {}
    });
  }

  // «На экране „Домой“»: установлено, предложить установку или скрыть строку.
  const install = document.querySelector('[data-install]');
  let deferredPrompt = null;
  const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone;
  if (install && standalone) { install.hidden = false; install.disabled = true; install.querySelector('[data-install-status]').textContent = 'Установлено'; }
  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    deferredPrompt = event;
    if (install && !standalone) install.hidden = false;
  });
  install?.addEventListener('click', async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    deferredPrompt = null;
    if (outcome === 'accepted') { install.disabled = true; install.querySelector('[data-install-status]').textContent = 'Установлено'; }
  });

  // Смена пароля (макеты 30 и 19): галочки правил загораются по мере ввода.
  const passwordForm = document.querySelector('[data-password-form]');
  if (passwordForm) {
    const minimum = Number(passwordForm.dataset.minimum) || 5;
    const old = passwordForm.querySelector('[name=old_password]');
    const first = passwordForm.querySelector('[name=new_password1]'), second = passwordForm.querySelector('[name=new_password2]');
    const rule = (name, ok) => passwordForm.querySelector(`[data-rule=${name}]`)?.classList.toggle('is-ok', ok);
    const check = () => {
      rule('length', first.value.length >= minimum);
      rule('different', first.value.length > 0 && (!old || first.value !== old.value));
      rule('match', second.value.length > 0 && first.value === second.value);
    };
    passwordForm.addEventListener('input', check);
    check();
  }
})();

(() => {
  // Переключатели уведомлений бота (T7) сохраняются сразу, без кнопки.
  document.querySelectorAll('form[data-autosave]').forEach((form) => form.addEventListener('change', async () => {
    try {
      const response = await fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      if (!response.ok) throw new Error('save');
    } catch {
      form.submit();
    }
  }));
})();

(() => {
  // «Запросить подтверждение» (макеты 34, 37) — без перехода, чтобы не потерять заполненную форму встречи.
  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-verify-request]');
    if (!button) return;
    const form = button.form || document.getElementById(button.getAttribute('form'));
    if (!form) return;
    event.preventDefault();
    button.disabled = true;
    try {
      const response = await fetch(form.action, { method: 'POST', body: new FormData(form), credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } });
      if (!response.ok) throw new Error('verify');
      const sent = document.createElement('span');
      sent.className = 'verify-sent';
      sent.textContent = 'Запрос отправлен — администратор подтвердит аккаунт';
      button.replaceWith(sent);
    } catch {
      button.disabled = false;
      form.submit();
    }
  });
})();

// Шкала дня 06:00–23:00 (макеты 01, 20, 23): при открытии прокручиваем к текущему часу,
// первой встрече или 09:00; на компьютере над этим часом видно ещё два.
(() => {
  const card = document.querySelector('[data-timeline-scroll]');
  const timeline = card?.querySelector('.timeline');
  if (!card || !timeline) return;
  const wide = getComputedStyle(card).getPropertyValue('--wide').trim() === '1';
  const unit = parseFloat(getComputedStyle(timeline).getPropertyValue('--u')) || 1;
  const top = parseFloat(wide ? card.dataset.timelineScrollWide : card.dataset.timelineScroll) || 0;
  // Телефон: карточка — от своего верха до низа экрана, прокручивается только она.
  const fit = () => {
    if (getComputedStyle(card).getPropertyValue('--wide').trim() === '1') return card.style.removeProperty('--timeline-max');
    const top = card.getBoundingClientRect().top + window.scrollY;
    card.style.setProperty('--timeline-max', `${Math.max(320, window.innerHeight - top)}px`);
  };
  fit();
  window.addEventListener('resize', fit);
  const hint = card.querySelector('.timeline-hint');
  const covered = hint ? hint.offsetHeight + 12 : 0; // подсказка «Свободно весь день» закреплена сверху
  const padding = parseFloat(getComputedStyle(card).paddingTop) || 0;
  card.scrollTop = Math.max(0, timeline.offsetTop + top * unit - padding - covered);
  const mark = () => card.classList.toggle('is-scrolled', card.scrollTop > 2);
  mark();
  card.addEventListener('scroll', mark, { passive: true });
})();
