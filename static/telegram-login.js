// Вход через бота из установленного приложения (макет PWA 22): ждём подтверждения в Telegram и входим.
(() => {
  const page = document.querySelector('[data-bot-login-page]');
  if (!page) return;
  const state = page.querySelector('[data-state]');
  const hint = page.querySelector('[data-hint]');
  const open = page.querySelector('[data-open-bot]');
  let timer = null;
  let finished = false;

  const expired = () => {
    finished = true;
    state.textContent = 'Время вышло';
    state.classList.remove('is-accent');
    hint.textContent = 'Ссылка для входа действует 10 минут. Начните заново — откроется новая.';
    open.textContent = 'Начать заново';
    open.href = location.href;
    open.removeAttribute('target');
  };

  const check = async () => {
    if (finished || document.hidden) return;
    try {
      const response = await fetch(page.dataset.status, { credentials: 'same-origin', cache: 'no-store' });
      const data = await response.json();
      if (data.state === 'done') {
        finished = true;
        state.textContent = 'Вход подтверждён';
        location.replace(data.redirect);
      } else if (data.state === 'expired') {
        expired();
      }
    } catch { /* нет сети — проверим позже */ }
  };

  timer = setInterval(check, 2000);
  // Вернулись из Telegram — проверяем сразу, не дожидаясь таймера.
  document.addEventListener('visibilitychange', check);
  window.addEventListener('focus', check);
  window.addEventListener('pagehide', () => clearInterval(timer));
})();
