// PWA: service worker, режим без сети и новая версия — макеты PWA 14 «Офлайн» и 15 «Новая версия».
(() => {
  const root = document.documentElement;
  const signedIn = root.dataset.auth === 'in';
  const fromCache = root.hasAttribute('data-offline-copy');
  const host = document.querySelector('[data-toasts]');
  const toasts = { offline: document.querySelector('[data-toast=offline]'), update: document.querySelector('[data-toast=update]') };
  const bookLinks = document.querySelectorAll('.tabbar-add, .sidebar-book');
  const health = host?.dataset.health;

  // В установленном приложении вход через сайт Telegram завершается во встроенном браузере,
  // поэтому кнопки «Войти через Telegram» ведут на вход через бота (макет PWA 22).
  const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  if (standalone) document.querySelectorAll('[data-bot-login]').forEach((link) => { link.href = link.dataset.botLogin; });
  let offline = false;
  let waiting = null;
  let timer = null;

  const show = (toast, visible) => toast?.classList.toggle('is-visible', visible);
  const render = () => {
    show(toasts.offline, offline);
    show(toasts.update, !offline && Boolean(waiting));
  };

  // Без сети: тост «Нет сети · показываем сохранённое расписание», «+» неактивна, формы не отправляются.
  const setOffline = (value) => {
    if (offline === value) return;
    offline = value;
    root.classList.toggle('is-offline', value);
    bookLinks.forEach((link) => (value ? link.setAttribute('aria-disabled', 'true') : link.removeAttribute('aria-disabled')));
    render();
    clearTimeout(timer);
    if (value) timer = setTimeout(check, 10000);
  };

  // navigator.onLine не всегда честен (Wi-Fi без интернета) — проверяем, отвечает ли сервер.
  const check = async () => {
    if (!health) return;
    try {
      const response = await fetch(health, { cache: 'no-store', credentials: 'same-origin' });
      if (response.ok) return back();
    } catch { /* всё ещё без сети */ }
    clearTimeout(timer);
    timer = setTimeout(check, 10000);
  };

  const edited = () => [...document.querySelectorAll('textarea, input:not([type=hidden])')].some((field) => field.value !== field.defaultValue);
  const back = () => {
    setOffline(false);
    if (fromCache && !edited()) location.reload(); // была сохранённая копия — показываем свежую
  };

  // Повторное появление тоста, когда действие недоступно без сети.
  const nudge = () => {
    const toast = toasts.offline;
    if (!toast) return;
    toast.classList.remove('is-replay');
    void toast.offsetWidth;
    toast.classList.add('is-replay');
    try { window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('warning'); } catch { /* вне Telegram */ }
  };

  const saved = async (href) => {
    if (!('caches' in window)) return false;
    try { return Boolean(await caches.match(href.split('#')[0], { cacheName: 'pages', ignoreVary: true })); } catch { return false; }
  };

  document.addEventListener('click', (event) => {
    if (!offline || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.origin !== location.origin || link.target === '_blank' || link.hasAttribute('download')) return;
    if (link.pathname === location.pathname && link.search === location.search && link.hash) return;
    event.preventDefault();
    event.stopPropagation();
    if (link.getAttribute('aria-disabled') === 'true') return nudge();
    saved(link.href).then((ok) => (ok ? location.assign(link.href) : nudge()));
  }, true);

  document.addEventListener('submit', (event) => {
    if (!offline) return;
    event.preventDefault();
    event.stopPropagation();
    nudge();
  }, true);

  window.addEventListener('offline', () => setOffline(true));
  window.addEventListener('online', check);
  if (!navigator.onLine || fromCache) setOffline(true);
  if (fromCache && navigator.onLine) check();

  if (!('serviceWorker' in navigator) || !root.dataset.sw) return;
  const sw = navigator.serviceWorker;
  const firstVisit = !sw.controller;
  let reloadOnChange = false;

  sw.register(root.dataset.sw, { scope: '/' }).then((registration) => {
    const offer = (worker) => {
      if (!worker || !sw.controller) return; // первая установка — обновлять нечего
      waiting = worker;
      render();
    };
    offer(registration.waiting);
    registration.addEventListener('updatefound', () => {
      const worker = registration.installing;
      worker?.addEventListener('statechange', () => { if (worker.state === 'installed') offer(worker); });
    });
    // Приложение может быть открыто днями — проверяем обновление при возвращении к нему.
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && !offline) registration.update().catch(() => {});
    });
  }).catch(() => {});

  sw.ready.then((registration) => {
    const worker = registration.active;
    if (!worker) return;
    if (!signedIn) worker.postMessage({ type: 'clear-pages' });
    else if (!fromCache) worker.postMessage({ type: 'warm', urls: firstVisit ? [location.href, host?.dataset.home || '/'] : [host?.dataset.home || '/'] });
  });

  sw.addEventListener('controllerchange', () => {
    if (reloadOnChange) location.reload();
  });

  document.querySelector('[data-update-now]')?.addEventListener('click', () => {
    if (!waiting) return;
    reloadOnChange = true;
    waiting.postMessage({ type: 'skip-waiting' });
  });
})();
