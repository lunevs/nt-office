(() => {
  const thread = document.getElementById('message-thread');
  if (!thread) return;
  const stream = document.getElementById('message-stream');
  const composer = document.getElementById('message-composer');
  const status = document.getElementById('chat-status');
  const csrf = composer.querySelector('[name=csrfmiddlewaretoken]').value;
  let cursor = Number(thread.dataset.cursor);
  let busy = false;
  let readThrough = 0;
  const history = thread.dataset.history === 'true';
  const markRead = async () => {
    if (document.hidden || !cursor || cursor <= readThrough) return;
    const response = await fetch(thread.dataset.read, {
      method: 'POST', credentials: 'same-origin',
      headers: {'X-CSRFToken': csrf, 'Content-Type': 'application/x-www-form-urlencoded'},
      body: new URLSearchParams({through: String(cursor)})
    });
    if (!response.ok) throw new Error('read');
    const data = await response.json();
    readThrough = cursor;
    document.querySelectorAll('[data-unread-count]').forEach(badge => {
      badge.textContent = data.unread;
      badge.hidden = data.unread === 0;
    });
  };
  // «Отправлено» — одна галочка, «Прочитано» — две (макеты 06 и 26)
  const icons = thread.dataset.icons;
  const tick = (read) => {
    const mark = document.createElement('span');
    mark.className = 'message-tick';
    mark.innerHTML = `<svg class="icon" aria-hidden="true"><use href="${icons}#check"/></svg><span class="visually-hidden">Отправлено</span>`;
    if (read) setRead(mark);
    else mark.title = 'Отправлено';
    return mark;
  };
  const setRead = (mark) => {
    mark.classList.add('is-read');
    mark.title = 'Прочитано';
    mark.querySelector('use').setAttribute('href', `${icons}#check-double`);
    mark.querySelector('.visually-hidden').textContent = 'Прочитано';
  };
  const markOwnRead = (through) => {
    if (!through) return;
    stream.querySelectorAll('.own-message .message-tick:not(.is-read)').forEach((mark) => {
      if (Number(mark.closest('[data-message-id]').dataset.messageId) <= through) setRead(mark);
    });
  };
  const scrollToLatest = () => {
    const last = stream.lastElementChild;
    if (last) last.scrollIntoView({block: 'nearest'});
  };
  const update = async () => {
    if (busy || document.hidden) return;
    busy = true;
    try {
      if (!history) {
        const response = await fetch(`${thread.dataset.updates}?after=${cursor}`, {credentials: 'same-origin'});
        if (!response.ok) throw new Error('updates');
        const data = await response.json();
        const nearBottom = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 260;
        for (const item of data.messages) {
          if (item.id <= cursor) continue;
          document.getElementById('empty-thread')?.remove();
          const bubble = document.createElement('article');
          bubble.className = `message-bubble ${item.own ? 'own-message' : 'incoming-message'}`;
          const text = document.createElement('p');
          text.textContent = item.text;
          bubble.dataset.messageId = item.id;
          const meta = document.createElement('span');
          meta.className = 'message-meta';
          const time = document.createElement('time');
          time.textContent = item.time;
          meta.append(time);
          if (item.own) meta.append(tick(item.read));
          bubble.append(text, meta);
          stream.append(bubble);
          cursor = item.id;
        }
        if (nearBottom && data.messages.length) scrollToLatest();
        markOwnRead(data.read_through);
      }
      await markRead();
      status.textContent = '';
    } catch {
      status.textContent = 'Не удалось обновить переписку. Проверьте соединение или обновите страницу.';
    } finally {
      busy = false;
    }
  };
  // Поле ввода растёт вместе с текстом (в макете — однострочная пилюля)
  const text = composer.querySelector('textarea');
  const grow = () => { text.style.height = 'auto'; text.style.height = `${Math.min(text.scrollHeight, 160)}px`; };
  text.addEventListener('input', grow);
  grow();
  if (!history) scrollToLatest();
  update();
  const timer = setInterval(update, 5000);
  document.addEventListener('visibilitychange', update);
  window.addEventListener('pagehide', () => clearInterval(timer));
})();
