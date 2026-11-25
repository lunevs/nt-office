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

// Листание дня (страница «Движение»): день, месяц и вид «День/Месяц» меняются без перезагрузки — шапка, меню
// и карточки стоят, содержимое въезжает на 24 px с той стороны, куда листаем, плашка дня в неделе переезжает.
// При ошибке — обычный переход на страницу (тогда движение даёт View Transition из app.css).
(() => {
  const current = () => document.querySelector('.calendar-page[data-day]');
  if (!current() || !window.fetch || !window.DOMParser) return;
  const path = location.pathname;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let pending = null;

  const motion = () => {
    const css = getComputedStyle(document.documentElement);
    return {
      shift: parseFloat(css.getPropertyValue('--motion-page')) || 24,
      duration: parseFloat(css.getPropertyValue('--motion-base')) || 240,
      easing: css.getPropertyValue('--ease-standard').trim() || 'ease-out',
    };
  };

  const fallback = (url, dir) => {
    try { sessionStorage.setItem('day-dir', JSON.stringify({ dir, t: Date.now() })); } catch { /* приватный режим */ }
    location.href = url;
  };

  const go = async (url, { push = true, focus = null } = {}) => {
    const page = current();
    const target = new URL(url, location.href);
    const date = target.searchParams.get('date') || '';
    const dir = page && date && date < page.dataset.day ? 'back' : 'forward';
    if (!page) return fallback(target.href, dir);
    if (pending) pending.abort();
    const controller = new AbortController();
    pending = controller;
    let next, book;
    try {
      const response = await fetch(target.href, { credentials: 'same-origin', signal: controller.signal, headers: { 'X-Requested-With': 'day' } });
      if (!response.ok || response.redirected) throw new Error('day');
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      next = doc.querySelector('.calendar-page[data-day]');
      if (!next) throw new Error('day');
      book = doc.querySelector('.tabbar-add, .sidebar-book');
      book = book && book.getAttribute('href');
    } catch (error) {
      if (error.name !== 'AbortError') fallback(target.href, dir);
      return;
    }
    if (pending !== controller) return;
    pending = null;

    const old = current();
    const fresh = document.importNode(next, true);
    const hadFocus = old.contains(document.activeElement);
    const isDay = (el) => el.classList.contains('is-day');
    const sameMode = isDay(old) === isDay(fresh);
    const firstHref = (el, selector) => el.querySelector(selector)?.getAttribute('href');
    const sameWeek = sameMode && firstHref(old, '.week-day') === firstHref(fresh, '.week-day');
    const sameMonth = sameMode && firstHref(old, '.month-grid .month-cell') === firstHref(fresh, '.month-grid .month-cell');
    const pillFrom = old.querySelector('.week-day.is-selected .week-day-num')?.getBoundingClientRect();
    old.getAnimations({ subtree: true }).forEach((a) => a.finish());
    old.replaceWith(fresh);
    if (book) document.querySelectorAll('.tabbar-add, .sidebar-book').forEach((a) => a.setAttribute('href', book));
    if (push) history.pushState({ day: fresh.dataset.day }, '', target.href);
    if (window.setupTimeline) window.setupTimeline();
    const selected = '.week-day.is-selected, .month-grid .month-cell.is-selected';
    if (hadFocus) ((focus && fresh.querySelector(focus)) || fresh.querySelector(selected))?.focus({ preventScroll: true });
    if (reduced.matches || !fresh.animate) return;

    const { shift, duration, easing } = motion();
    if (!sameMode) { // «День» ↔ «Месяц»: другая раскладка — просто проявляется, шапка стоит
      fresh.querySelectorAll(':scope > :not(.cal-greeting, .cal-actions, script)').forEach((el) => el.animate([{ opacity: 0 }, { opacity: 1 }], { duration, easing }));
      return;
    }
    const offset = dir === 'back' ? -shift : shift;
    const parts = isDay(fresh)
      ? ['.cal-title h1', '.now-card', '.timeline-card > .timeline', '.timeline-card > .timeline-hint']
      : ['.day-panel > *'];
    if (isDay(fresh) && !sameWeek) parts.push('.week-strip');
    if (!isDay(fresh) && !sameMonth) parts.push('.cal-title h1', '.month-card > table');
    // Пока содержимое сдвинуто на 24 px, оно не должно вылезать за край — иначе мигают полосы прокрутки.
    fresh.classList.add('is-sliding');
    const slides = [...fresh.querySelectorAll(parts.join(', '))].map((el) => el.animate(
      [{ opacity: 0, transform: `translateX(${offset}px)` }, { opacity: 1, transform: 'none' }],
      { duration, easing, fill: 'backwards' },
    ).finished.catch(() => {}));
    Promise.all(slides).then(() => fresh.classList.remove('is-sliding'));
    const pill = sameWeek && fresh.querySelector('.week-day.is-selected .week-day-num');
    const pillTo = pill && pill.getBoundingClientRect();
    if (pill && pillFrom && pillFrom.width && pillTo.width && pillFrom.left !== pillTo.left) {
      pill.style.position = 'relative';
      pill.style.zIndex = '1';
      pill.animate([{ transform: `translateX(${pillFrom.left - pillTo.left}px)` }, { transform: 'none' }], { duration, easing })
        .finished.catch(() => {}).finally(() => { pill.style.removeProperty('position'); pill.style.removeProperty('z-index'); });
    }
  };

  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[href]');
    const page = current();
    if (!link || !page || !page.contains(link) || event.defaultPrevented || link.target) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (link.origin !== location.origin || link.pathname !== path) return;
    const url = new URL(link.href);
    if (!url.searchParams.get('date') && !url.searchParams.get('view')) return;
    event.preventDefault();
    const label = !link.classList.contains('week-day') && link.getAttribute('aria-label');
    go(url.href, { focus: label ? `[aria-label="${CSS.escape(label)}"]` : null });
  });

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!form.matches('.calendar-page .date-jump')) return;
    event.preventDefault();
    const url = new URL(path, location.href);
    url.search = new URLSearchParams(new FormData(form)).toString();
    go(url.href);
  });

  window.addEventListener('popstate', () => { if (location.pathname === path && current()) go(location.href, { push: false }); });
})();
