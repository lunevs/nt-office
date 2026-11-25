// Мини-приложение Telegram (макеты T1–T7). Скрипт подключается только внутри Telegram.
(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  const safe = (fn) => { try { fn(); } catch (e) { /* старая версия Telegram — пропускаем */ } };

  // Вход: /tg/ отправляет подпись Telegram на сервер и переходит туда, куда скажет сервер.
  const entry = document.querySelector('[data-telegram-entry]');
  if (entry) {
    const status = entry.querySelector('[data-status]');
    if (!tg || !tg.initData) { location.replace(entry.dataset.fallback); return; }
    safe(() => { tg.ready(); tg.expand(); });
    fetch(entry.dataset.auth, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'X-CSRFToken': entry.querySelector('[name=csrfmiddlewaretoken]').value },
      body: new URLSearchParams({ init_data: tg.initData }),
    }).then((r) => r.json().then((data) => ({ ok: r.ok, data })))
      .then(({ ok, data }) => { if (ok && data.redirect) location.replace(data.redirect); else status.textContent = data.error || 'Не удалось войти.'; })
      .catch(() => { status.textContent = 'Нет связи. Закройте и откройте приложение ещё раз.'; });
    return;
  }
  if (!tg || !tg.initData) return;

  const root = document.documentElement;
  root.classList.add('tg');
  safe(() => { tg.ready(); tg.expand(); });
  const css = (name) => getComputedStyle(root).getPropertyValue(name).trim();

  // Тема — из Telegram, а не из системы. Шапку и низ Telegram красим в цвет фона приложения.
  const applyTheme = () => {
    root.dataset.theme = tg.colorScheme === 'dark' ? 'dark' : 'light';
    const canvas = css('--bg-canvas');
    safe(() => tg.setHeaderColor(canvas));
    safe(() => tg.setBackgroundColor(canvas));
    safe(() => tg.setBottomBarColor && tg.setBottomBarColor(canvas));
  };
  applyTheme();
  safe(() => tg.onEvent('themeChanged', applyTheme));

  // «Назад» Telegram вместо наших кнопок назад; на главных вкладках — «Закрыть».
  const top = ['/', '/messages/', '/profile/', '/login/', '/access/pending/', '/telegram/join/'];
  if (top.includes(location.pathname)) safe(() => tg.BackButton.hide());
  else {
    const back = document.querySelector('[data-tg-back], .page-back, .page-nav .icon-button:first-child, .sheet-close, .thread-back');
    safe(() => { tg.BackButton.show(); tg.BackButton.onClick(() => { if (back && back.href) location.href = back.href; else history.back(); }); });
  }

  // Главное действие формы — нижняя кнопка Telegram (бронирование, заявка, вход).
  const main = document.querySelector('[data-tg-main], .booking-form .sheet-actions .button.primary');
  if (main && tg.MainButton) {
    root.classList.add('tg-main');
    // Неактивная кнопка (ошибка времени, макет 22) — как кнопка сайта с прозрачностью 40% на фоне приложения.
    const rgb = (value) => {
      const hex = value.match(/^#([0-9a-f]{6})$/i);
      if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16));
      const parts = value.match(/\d+(\.\d+)?/g);
      return parts && parts.length >= 3 ? parts.slice(0, 3).map(Number) : null;
    };
    const fade = (color) => {
      const a = rgb(color), b = rgb(css('--bg-canvas'));
      if (!a || !b) return color;
      return '#' + a.map((v, i) => Math.round(v * 0.4 + b[i] * 0.6).toString(16).padStart(2, '0')).join('');
    };
    const sync = () => safe(() => {
      const off = main.disabled;
      tg.MainButton.setParams({
        text: main.textContent.trim(), is_visible: true, is_active: !off,
        color: off ? fade(css('--accent')) : css('--accent'),
        text_color: off ? fade('#ffffff') : '#ffffff',
      });
    });
    sync();
    safe(() => tg.MainButton.onClick(() => { if (!main.disabled) main.click(); }));
    new MutationObserver(sync).observe(main, { attributes: true, attributeFilter: ['disabled'] });
    safe(() => tg.onEvent('themeChanged', sync));
  }

  // Отклик: лёгкий на нажатия, успех после действия, ошибка при ошибке формы.
  const haptic = tg.HapticFeedback;
  document.addEventListener('click', (e) => {
    if (e.target.closest('.button, .chip, .room-chip, .tabbar a, .tabbar-add, .segmented a, .week-day, .icon-button, .switch-row')) safe(() => haptic.impactOccurred('light'));
  });
  if (document.querySelector('.notice')) safe(() => haptic.notificationOccurred('success'));
  if (document.querySelector('.field-error:not([hidden]), .inline-alert[role=alert], .is-error')) safe(() => haptic.notificationOccurred('error'));

  // Пока открыта шторка, свайп вниз закрывает шторку, а не приложение.
  const swipes = () => safe(() => (document.querySelector('dialog[open]') ? tg.disableVerticalSwipes() : tg.enableVerticalSwipes()));
  new MutationObserver(swipes).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['open'] });
})();
