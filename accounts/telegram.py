"""Telegram: проверка подписи (мини-приложение и виджет входа), бот и уведомления.

Бот пишет только тем, кто привязал Telegram и не отключил нужный тип уведомлений в профиле.
Отправка идёт после фиксации транзакции в отдельном потоке и не задерживает ответ пользователю.
"""
import functools
import hashlib
import hmac
import json
import logging
import threading
import time
import urllib.request
from html import escape
from urllib.parse import parse_qsl

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"
MAX_AGE = 24 * 60 * 60


def enabled():
    return bool(settings.TELEGRAM_BOT_TOKEN)


def _token():
    return settings.TELEGRAM_BOT_TOKEN.encode()


def _check_string(pairs):
    return "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))


def _fresh(auth_date, max_age):
    try:
        return 0 <= time.time() - int(auth_date) <= max_age
    except (TypeError, ValueError):
        return False


def verify_webapp(init_data, max_age=MAX_AGE):
    """Данные мини-приложения (Telegram.WebApp.initData). Возвращает словарь пользователя Telegram или None."""
    if not enabled() or not init_data:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", "")
    secret = hmac.new(b"WebAppData", _token(), hashlib.sha256).digest()
    expected = hmac.new(secret, _check_string(pairs).encode(), hashlib.sha256).hexdigest()
    if not received or not hmac.compare_digest(expected, received) or not _fresh(pairs.get("auth_date"), max_age):
        return None
    try:
        user = json.loads(pairs.get("user", ""))
    except ValueError:
        return None
    return user if isinstance(user, dict) and user.get("id") else None


def verify_login(params, max_age=MAX_AGE):
    """Данные виджета «Войти через Telegram» на сайте. Возвращает словарь пользователя Telegram или None."""
    if not enabled():
        return None
    fields = {key: value for key, value in params.items() if key in {"id", "first_name", "last_name", "username", "photo_url", "auth_date"}}
    received = params.get("hash", "")
    secret = hashlib.sha256(_token()).digest()
    expected = hmac.new(secret, _check_string(fields).encode(), hashlib.sha256).hexdigest()
    if not received or not hmac.compare_digest(expected, received) or not _fresh(fields.get("auth_date"), max_age):
        return None
    try:
        fields["id"] = int(fields["id"])
    except (KeyError, ValueError):
        return None
    return fields


def profile(tg_user):
    """То, что храним в сессии до привязки: id, имя, фамилия, имя пользователя Telegram."""
    return {"id": int(tg_user["id"]), "first_name": tg_user.get("first_name", "")[:150], "last_name": tg_user.get("last_name", "")[:150], "username": (tg_user.get("username") or "")[:64]}


def oauth_url(request):
    """Своя кнопка «Войти через Telegram» (макет 09): страница авторизации Telegram, ответ придёт на /telegram/callback/.
    Работает, когда в @BotFather указан домен сайта (/setdomain)."""
    if not enabled():
        return None
    from urllib.parse import urlencode
    from django.urls import reverse
    origin = f"{request.scheme}://{request.get_host()}"
    query = urlencode({"bot_id": settings.TELEGRAM_BOT_TOKEN.split(":")[0], "origin": origin, "request_access": "write", "return_to": origin + reverse("telegram_callback")})
    return f"https://oauth.telegram.org/auth?{query}"


@functools.lru_cache(maxsize=1)
def _username_from_api():
    return ((call("getMe", {}) or {}).get("result") or {}).get("username", "")


def bot_username():
    return settings.TELEGRAM_BOT_USERNAME or _username_from_api()


def app_url(path):
    return f"{settings.SITE_URL}{path}" if settings.SITE_URL else None


def call(method, payload, timeout=5):
    """Вызов Bot API. Ошибки только пишем в лог: уведомление не должно ломать основное действие."""
    request = urllib.request.Request(API.format(token=settings.TELEGRAM_BOT_TOKEN, method=method), data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except Exception:  # сеть, блокировка бота пользователем и т. п.
        logger.warning("Telegram %s failed", method, exc_info=True)
        return None


def _button(text, path=None, callback=None):
    if callback:
        return {"text": text, "callback_data": callback}
    url = app_url(path)
    return {"text": text, "web_app": {"url": url}} if url else None


def send(chat_id, title, body, buttons=()):
    """Сообщение от бота: жирный заголовок, текст и кнопки, открывающие нужный экран мини-приложения."""
    if not enabled() or not chat_id:
        return
    keyboard = [button for button in buttons if button]
    payload = {"chat_id": chat_id, "text": f"<b>{escape(title)}</b>\n{escape(body)}", "parse_mode": "HTML", "disable_web_page_preview": True}
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": [keyboard]}
    transaction.on_commit(lambda: threading.Thread(target=call, args=("sendMessage", payload), daemon=True).start())


def _name(user):
    return f"{user.last_name} {user.first_name}".strip() or user.username


# --- Уведомления (макет T6) ---------------------------------------------------

def notify_message(message):
    recipient = message.recipient
    if recipient.telegram_id and recipient.notify_messages and recipient.is_active:
        preview = message.text if len(message.text) <= 300 else message.text[:299] + "…"
        send(recipient.telegram_id, f"Сообщение · {_name(message.sender)}", f"«{preview}»", [_button("Ответить", f"/messages/{message.sender_id}/")])


def notify_event(event, actor, kind):
    """kind: changed / moved / cancelled / restored. Пишем ответственному, если менял не он сам."""
    person = event.responsible
    if not person.telegram_id or not person.notify_events or not person.is_active or person.pk == actor.pk:
        return
    titles = {"changed": "Встреча изменена", "moved": "Встреча перенесена", "cancelled": "Встреча отменена", "restored": "Встреча восстановлена"}
    from django.utils.formats import date_format
    rooms = ", ".join(room.name for room in event.rooms.all())
    when = f"{date_format(event.date, 'l, j E')}, {event.start_time:%H:%M}–{event.end_time:%H:%M}"
    body = f"{event.title} — {when} · {rooms}\n{'Отмена' if kind == 'cancelled' else 'Изменения'}: {_name(actor)}"
    send(person.telegram_id, titles.get(kind, "Встреча изменена"), body, [_button("Открыть в календаре", f"/events/{event.pk}/")])


def notify_verification_request(user):
    from .models import User
    for admin in User.objects.filter(is_superuser=True, is_active=True, notify_requests=True, telegram_id__isnull=False):
        send(admin.telegram_id, "Запрос на подтверждение аккаунта", f"{_name(user)} · @{user.username}. После подтверждения ограничения на бронирование снимутся.", [_button("Подтвердить", callback=f"verify:{user.pk}"), _button("Открыть", "/management/")])


def notify_verified(user):
    if user.telegram_id and user.is_active:
        send(user.telegram_id, "Аккаунт подтверждён", "Теперь можно бронировать без ограничений: несколько встреч в день, дольше 2 часов и с повтором.", [_button("Открыть календарь", "/")])


def _event_line(event):
    from django.utils.formats import date_format
    rooms = ", ".join(room.name for room in event.rooms.all())
    return f"{event.title} — {date_format(event.date, 'l, j E')}, {event.start_time:%H:%M}–{event.end_time:%H:%M} · {rooms}"


def notify_key_request(event, person, admins):
    for admin in admins:
        if admin.telegram_id and admin.notify_requests:
            send(admin.telegram_id, "Нужен ключ", f"{_event_line(event)}\nКто: {_name(person)} · @{person.username}", [_button("Открыть чат", f"/messages/{person.pk}/"), _button("Встреча", f"/events/{event.pk}/")])


def notify_key_sent(event, person, admins):
    if not person.telegram_id:
        return
    contacts = "; ".join(f"{_name(admin)}" + (f" (@{admin.telegram_username})" if admin.telegram_username else "") for admin in admins) or "администратор офиса"
    send(person.telegram_id, "Запрос на ключ отправлен", f"{_event_line(event)}\nАдминистраторы напишут вам в «Сообщения», как и когда получить ключ. Контакты: {contacts}.", [_button("Открыть сообщения", "/messages/")])


def notify_role(user):
    """Назначили администратором или сняли права."""
    if not (user.telegram_id and user.is_active):
        return
    if user.is_superuser:
        body = "Теперь вам доступно «Управление»: подтверждение аккаунтов, ключи, пользователи и любые встречи."
        if user.must_change_password:
            body += " При следующем входе задайте новый пароль — не короче 10 символов."
        send(user.telegram_id, "Вы администратор", body, [_button("Открыть управление", "/management/")])
    else:
        send(user.telegram_id, "Права администратора сняты", "Вы остаётесь участником и можете бронировать без ограничений.", [_button("Открыть календарь", "/")])
