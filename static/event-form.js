// Форма встречи (макеты 04, 16, 22, 33). Без скрипта форма работает на обычных полях.
// initBookingForm вызывается и для страницы, и для окна поверх календаря на компьютере (макет 25).
window.initBookingForm = (root) => {
  if (!root || root.dataset.ready) return;
  root.dataset.ready = '1';
  const form = root.querySelector('#booking-form');
  const $ = (selector) => form.querySelector(selector);

  const WEEKDAYS = ['воскресенье', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота'];
  const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  const parseDate = (value) => { const [y, m, d] = (value || '').split('-').map(Number); return y ? new Date(y, m - 1, d) : null; };
  const longDate = (date) => { const w = WEEKDAYS[date.getDay()]; return `${w[0].toUpperCase()}${w.slice(1)}, ${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`; };
  const plural = (n, one, few, many) => { const a = n % 100, b = n % 10; return a > 10 && a < 20 ? many : b === 1 ? one : b >= 2 && b <= 4 ? few : many; };
  const toMinutes = (value) => { const [h, m] = (value || '').split(':').map(Number); return Number.isFinite(h) ? h * 60 + (m || 0) : null; };
  const toClock = (minutes) => `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
  const duration = (minutes) => { const h = Math.floor(minutes / 60), m = minutes % 60; return h && m === 30 ? `${h},5 ч` : h ? `${h} ч${m ? ` ${m} мин` : ''}` : `${m} мин`; };
  const LAST = 23 * 60;

  const date = $('[name=date]'), start = $('[name=start_time]'), end = $('[name=end_time]');
  const repeat = $('[name=repeat_weekly]'), until = $('[name=repeat_until]');
  const dateDisplay = $('[data-display=date]'), untilDisplay = $('[data-display=until]');
  const untilField = $('[data-repeat-until]');

  const refresh = () => {
    const day = parseDate(date.value);
    if (dateDisplay) dateDisplay.textContent = day ? longDate(day) : 'Выберите дату';
    form.querySelectorAll('[data-date]').forEach((chip) => chip.classList.toggle('is-selected', chip.dataset.date === date.value));
    const length = toMinutes(end.value) - toMinutes(start.value);
    form.querySelectorAll('[data-minutes]').forEach((chip) => chip.classList.toggle('is-selected', Number(chip.dataset.minutes) === length));
    if (repeat && until) {
      until.disabled = !repeat.checked;
      until.required = repeat.checked;
      untilField.hidden = !repeat.checked;
      const last = parseDate(until.value);
      if (untilDisplay) {
        if (day && last && last >= day) {
          const count = Math.floor((last - day) / 864e5 / 7) + 1;
          untilDisplay.textContent = `До ${last.getDate()} ${MONTHS[last.getMonth()]} ${last.getFullYear()} · ${count} ${plural(count, 'встреча', 'встречи', 'встреч')}`;
        } else {
          untilDisplay.textContent = 'До какого числа повторять';
        }
      }
    }
  };

  // Быстрые даты: «Сегодня», «Завтра», «Чт, 26»
  form.querySelectorAll('[data-date]').forEach((chip) => chip.addEventListener('click', () => { date.value = chip.dataset.date; refresh(); }));

  // Длительность: окончание = начало + 1…4 ч, но не позже 23:00
  form.querySelectorAll('[data-minutes]').forEach((chip) => chip.addEventListener('click', () => {
    const from = toMinutes(start.value);
    if (from === null) return;
    end.value = toClock(Math.min(LAST, from + Number(chip.dataset.minutes)));
    refresh();
  }));

  // Список времени окончания с длительностью (макет 33): шаг 30 минут до 23:00
  const list = root.querySelector('[data-time-list]');
  if (list) {
    end.readOnly = true;
    const close = () => { list.hidden = true; end.setAttribute('aria-expanded', 'false'); };
    const open = () => {
      const from = toMinutes(start.value);
      if (from === null) { start.focus(); return; }
      const current = toMinutes(end.value);
      const values = [];
      for (let m = Math.ceil((from + 1) / 30) * 30; m <= LAST; m += 30) values.push(m);
      if (current !== null && current > from && !values.includes(current)) values.push(current);
      values.sort((a, b) => a - b);
      list.replaceChildren(...values.map((m) => {
        const option = document.createElement('button');
        option.type = 'button';
        option.className = 'time-option' + (m === current ? ' is-selected' : '');
        option.setAttribute('role', 'option');
        option.setAttribute('aria-selected', String(m === current));
        option.innerHTML = `<b>${toClock(m)}</b><span>${duration(m - from)}</span>`;
        option.addEventListener('click', () => { end.value = toClock(m); close(); refresh(); end.focus(); });
        return option;
      }));
      list.hidden = false;
      end.setAttribute('aria-expanded', 'true');
      list.querySelector('.is-selected')?.scrollIntoView({ block: 'center' });
    };
    end.setAttribute('aria-haspopup', 'listbox');
    end.addEventListener('click', () => (list.hidden ? open() : close()));
    end.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') { e.preventDefault(); open(); list.querySelector('.is-selected, .time-option')?.focus(); } });
    document.addEventListener('click', (e) => { if (!list.hidden && !e.target.closest('.end-time')) close(); });
    list.addEventListener('keydown', (e) => { if (e.key === 'Escape') { close(); end.focus(); } });
  }

  // Количество людей: «−» и «+»
  form.querySelectorAll('[data-stepper] [data-step]').forEach((button) => button.addEventListener('click', () => {
    const input = button.parentElement.querySelector('input');
    input.value = Math.max(1, (Number(input.value) || 1) + Number(button.dataset.step));
  }));

  // Серия: при сохранении спрашиваем, какие встречи менять (макет 17)
  const scope = form.querySelector('[data-scope-dialog]');
  const save = form.querySelector('[data-open-scope]');
  if (scope && save && scope.showModal) {
    save.addEventListener('click', (e) => { e.preventDefault(); scope.showModal(); });
    scope.querySelector('[data-scope-cancel]').addEventListener('click', () => scope.close());
  }

  // Поле даты показывает «Вторник, 24 ноября 2026», а системный календарь открываем по нажатию на всё поле
  form.querySelectorAll('.has-overlay').forEach((field) => field.addEventListener('click', (e) => {
    const input = field.querySelector('input');
    if (e.target !== input && input.showPicker && !input.disabled) { try { input.showPicker(); } catch { input.focus(); } }
  }));

  [date, start, end, repeat, until].forEach((input) => input && input.addEventListener('change', refresh));
  start.addEventListener('input', refresh);
  window.addEventListener('pageshow', refresh);
  refresh();
};
window.initBookingForm(document.querySelector('[data-booking]'));
