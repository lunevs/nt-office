"""Утренняя сводка «Сегодня в офисе» от бота в личные чаты (макет T8, переключатель в профиле — T7)."""
import logging
import threading
import time as clock
from datetime import time
from html import escape

from django.db import IntegrityError, close_old_connections, transaction
from django.utils import timezone
from django.utils.formats import date_format

from . import telegram

logger = logging.getLogger(__name__)

DIGEST_TIME = time(8, 0)
LATEST_TIME = time(11, 0)  # после перезапуска сервера сводка ещё уходит до 11:00, позже — уже не нужна


def _events(day):
    from bookings.models import Event
    return list(Event.objects.filter(date=day, status=Event.Status.ACTIVE).prefetch_related("rooms").order_by("start_time", "end_time", "pk"))


def digest_message(day, user, events=None):
    """Заголовок и строки сводки. Закрытые встречи — «Занято», если человек не видит их детали, как в календаре."""
    events = _events(day) if events is None else events
    title = f"Сегодня в офисе · {date_format(day, 'l, j E').lower()}"
    lines = []
    for event in events:
        name = "Занято" if event.hide_details and not event.can_edit(user) else event.title
        rooms = ", ".join(room.name for room in event.rooms.all())
        lines.append(f"{event.start_time:%H:%M}–{event.end_time:%H:%M} · {name}\n{rooms}".rstrip())
    return title, "\n\n".join(lines)


def send_digest(user, day, events=None, skip_empty=False):
    title, body = digest_message(day, user, events)
    if not body:
        if skip_empty:
            return False
        body = "Встреч нет — офис свободен."
    payload = {"chat_id": user.telegram_id, "text": f"<b>{escape(title)}</b>\n{escape(body)}", "parse_mode": "HTML", "disable_web_page_preview": True}
    url = telegram.app_url("/tg/")
    if url:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": "Открыть расписание", "web_app": {"url": url}}]]}
    result = telegram.call("sendMessage", payload)
    return bool(result and result.get("ok"))


def send_today(chat_id):
    """Команда /today: сводка по запросу, даже если встреч нет."""
    from .models import User
    user = User.objects.filter(telegram_id=chat_id, is_active=True).first()
    if not user:
        telegram.call("sendMessage", {"chat_id": chat_id, "text": "Сначала откройте приложение кнопкой «Календарь» и войдите — тогда бот покажет встречи на сегодня."})
        return False
    return send_digest(user, timezone.localdate())


def run_due(now=None):
    """Разослать сегодняшнюю сводку, если пора и её ещё не рассылали. Возвращает число получателей."""
    from .models import DailyDigest, User
    now = timezone.localtime(now)
    if not telegram.enabled() or not (DIGEST_TIME <= now.time() < LATEST_TIME):
        return 0
    today = now.date()
    if DailyDigest.objects.filter(day=today).exists():
        return 0
    try:
        with transaction.atomic():
            record = DailyDigest.objects.create(day=today)
    except IntegrityError:  # другой процесс успел первым
        return 0
    events = _events(today)
    if not events:
        return 0  # в дни без встреч сводку не присылаем
    sent = 0
    for user in User.objects.filter(is_active=True, notify_digest=True, telegram_id__isnull=False):
        if send_digest(user, today, events, skip_empty=True):
            sent += 1
    record.recipients = sent
    record.save(update_fields=["recipients"])
    return sent


_started = False


def start_scheduler():
    global _started
    if _started or not telegram.enabled():
        return
    _started = True
    threading.Thread(target=_loop, name="telegram-digest", daemon=True).start()


def _loop():
    clock.sleep(20)
    while True:
        try:
            close_old_connections()
            run_due()
        except Exception:  # сводка не должна ронять сайт
            logger.exception("Telegram digest failed")
        finally:
            close_old_connections()
        clock.sleep(60)
