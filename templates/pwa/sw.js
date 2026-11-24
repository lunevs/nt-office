const CONFIG = {{ config }};
{% verbatim %}
// Service worker «Нашего офиса» — макеты PWA 14 «Офлайн» и 15 «Новая версия».
// Статика берётся из кэша (у файлов с хэшем адрес меняется вместе с содержимым),
// страницы — из сети, а без сети показывается последняя сохранённая копия.
const STATIC_CACHE = `static-${CONFIG.version}`;
const PAGES_CACHE = 'pages';
const PAGE_LIMIT = 60;
const PAGES = CONFIG.pages.map((source) => new RegExp(source));
const HASHED = /\.[0-9a-f]{12}(\.[^./]+)$/;

const isPage = (url) => PAGES.some((pattern) => pattern.test(url.pathname));
const isHtml = (response) => response.ok && response.type === 'basic' && (response.headers.get('Content-Type') || '').startsWith('text/html');
const unhashed = (pathname) => pathname.replace(HASHED, '$1');

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.addAll(CONFIG.precache)));
  // Новая версия ждёт, пока человек нажмёт «Обновить» (сообщение skip-waiting).
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith('static-') && name !== STATIC_CACHE).map((name) => caches.delete(name)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  const data = event.data || {};
  if (data.type === 'skip-waiting') self.skipWaiting();
  if (data.type === 'clear-pages') event.waitUntil(caches.delete(PAGES_CACHE));
  if (data.type === 'warm') event.waitUntil(warm(data.urls || []));
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.method !== 'GET') {
    // Выход из аккаунта: сохранённые страницы принадлежат этому человеку — удаляем.
    if (url.pathname === CONFIG.logout) event.waitUntil(caches.delete(PAGES_CACHE));
    return;
  }
  if (url.pathname.startsWith(CONFIG.static)) event.respondWith(staticAsset(request));
  else if (request.mode === 'navigate') event.respondWith(page(event, url));
});

async function staticAsset(request) {
  const cache = await caches.open(STATIC_CACHE);
  if (CONFIG.immutable) {
    const hit = await cache.match(request);
    if (hit) return hit;
  }
  try {
    const response = await fetch(request);
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (error) {
    const hit = (await cache.match(request)) || (await similar(cache, request));
    if (hit) return hit;
    throw error;
  }
}

// Сохранённая страница ссылается на файлы прошлой версии — отдаём тот же файл новой версии.
async function similar(cache, request) {
  const wanted = unhashed(new URL(request.url).pathname);
  for (const key of await cache.keys()) {
    if (unhashed(new URL(key.url).pathname) === wanted) return cache.match(key);
  }
  return undefined;
}

async function page(event, url) {
  try {
    const response = await fetch(event.request);
    if (isPage(url) && isHtml(response)) event.waitUntil(remember(url.href, response.clone()));
    return response;
  } catch (error) {
    return offline(url);
  }
}

async function remember(href, response) {
  const cache = await caches.open(PAGES_CACHE);
  await cache.put(href, response);
  const keys = await cache.keys();
  await Promise.all(keys.slice(0, Math.max(0, keys.length - PAGE_LIMIT)).map((key) => cache.delete(key)));
}

// Первое открытие: страница загрузилась до того, как service worker начал работать, — сохраняем её отдельно.
async function warm(urls) {
  const cache = await caches.open(PAGES_CACHE);
  await Promise.all(urls.map(async (href) => {
    const url = new URL(href, self.location.origin);
    url.hash = '';
    if (url.origin !== self.location.origin || !isPage(url)) return;
    if (await cache.match(url.href, { ignoreVary: true })) return;
    try {
      const response = await fetch(url.href, { credentials: 'same-origin', redirect: 'manual' });
      if (isHtml(response)) await remember(url.href, response);
    } catch (error) { /* без сети — сохраним в следующий раз */ }
  }));
}

async function offline(url) {
  const cache = await caches.open(PAGES_CACHE);
  const saved = await cache.match(url.href, { ignoreVary: true });
  if (saved) {
    // Отметка для страницы: показать тост «Нет сети», не повторять старые уведомления.
    const html = (await saved.text()).replace('<html', '<html data-offline-copy');
    return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
  }
  const home = new URL(CONFIG.home, self.location.origin).href;
  if (url.href !== home && (await cache.match(home, { ignoreVary: true }))) return Response.redirect(home, 302);
  return new Response(offlinePage(), { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
}

// Ничего не сохранено (приложение ещё не открывали с интернетом после входа).
function offlinePage() {
  return `<!doctype html><html lang="ru" class="js"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><meta name="color-scheme" content="light dark">
<title>Нет сети · Наш офис</title>
<script>try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}</script>
<link rel="stylesheet" href="${CONFIG.css}"></head><body><div class="app"><div class="app-main"><main id="main">
<section class="password-page auth-page"><img class="auth-logo" src="${CONFIG.logo}" alt="" width="56" height="56">
<div class="auth-head"><h1>Нет сети</h1><p>Подключитесь к интернету и откройте приложение ещё раз. После этого расписание будет доступно и без сети.</p></div>
<div class="auth-actions"><button class="button primary" type="button" onclick="location.reload()">Повторить</button></div>
</section></main></div></div></body></html>`;
}
{% endverbatim %}
