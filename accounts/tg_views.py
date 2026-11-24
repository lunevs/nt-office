"""Вход через Telegram, мини-приложение, привязка, запрос подтверждения и вебхук бота (макеты 09, T1, T2, T6, T7, 37)."""
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from . import access, digest, telegram
from .forms import LoginForm, TelegramJoinForm

User = get_user_model()
SESSION_PROFILE = "telegram_profile"


def _login(request, user, in_telegram=False):
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    if in_telegram:
        request.session["in_telegram"] = True


def _route(request, tg, in_telegram):
    """Куда вести человека с подтверждённым Telegram: войти, ждать заявку, увидеть блокировку или подать заявку."""
    user = User.objects.filter(telegram_id=tg["id"]).first()
    if user and user.is_active:
        if user.telegram_username != tg.get("username", user.telegram_username):
            user.telegram_username = tg.get("username", "")
            user.save(update_fields=["telegram_username"])
        _login(request, user, in_telegram)
        return reverse("password_change") if user.must_change_password else reverse("home")
    if in_telegram:
        request.session["in_telegram"] = True
    if user:
        return reverse("login") + "?blocked=1"
    request.session[SESSION_PROFILE] = telegram.profile(tg)
    return reverse("telegram_join")


@require_GET
def entry(request):
    """Адрес мини-приложения в боте: забирает подпись Telegram и входит (или ведёт к заявке)."""
    return render(request, "accounts/telegram_entry.html")


@require_POST
def webapp_auth(request):
    tg = telegram.verify_webapp(request.POST.get("init_data", ""))
    if not tg:
        return JsonResponse({"error": "Не удалось подтвердить вход через Telegram. Откройте приложение из бота ещё раз."}, status=403)
    return JsonResponse({"redirect": _route(request, tg, in_telegram=True)})


@require_GET
def callback(request):
    """Telegram возвращает данные входа в адресе после «#tgAuthResult=…»; страница передаёт их на /telegram/login/."""
    return render(request, "accounts/telegram_callback.html")


@require_GET
def widget_login(request):
    """Ответ виджета «Войти через Telegram» на сайте. Если человек уже вошёл — привязываем Telegram к нему."""
    tg = telegram.verify_login(request.GET.dict())
    if not tg:
        messages.error(request, "Не удалось войти через Telegram. Попробуйте ещё раз.")
        return redirect("login")
    if request.user.is_authenticated:
        return _link_current(request, tg)
    return redirect(_route(request, tg, in_telegram=False))


def _link_current(request, tg):
    owner = User.objects.filter(telegram_id=tg["id"]).exclude(pk=request.user.pk).first()
    if owner:
        messages.error(request, "Этот Telegram уже привязан к другому аккаунту.")
        return redirect("profile")
    request.user.telegram_id = tg["id"]
    request.user.telegram_username = tg.get("username", "")
    request.user.save(update_fields=["telegram_id", "telegram_username"])
    messages.success(request, "Telegram привязан. Теперь можно входить без пароля.")
    return redirect("profile")


@require_http_methods(["GET", "POST"])
def join(request):
    """T1: Telegram ещё не привязан — аккаунт создаётся сразу из данных Telegram (неподтверждённый)."""
    tg = request.session.get(SESSION_PROFILE)
    if not tg:
        return redirect("login")
    form = TelegramJoinForm(request.POST or None, telegram=tg)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
        except IntegrityError:
            form.add_error("username", "Этот логин уже занят — попробуйте другой")
        else:
            request.session.pop(SESSION_PROFILE, None)
            _login(request, user, request.session.get("in_telegram", False))
            messages.success(request, "Аккаунт создан. Можно бронировать — одну встречу в день до 2 часов, пока аккаунт не подтверждён.")
            return redirect("home")
    return render(request, "accounts/telegram_join.html", {"form": form, "tg": tg})


@sensitive_post_parameters()
@require_http_methods(["GET", "POST"])
def link(request):
    """T2: аккаунт уже есть — один вход по логину и паролю, и Telegram привязывается."""
    tg = request.session.get(SESSION_PROFILE)
    if not tg:
        return redirect("login")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if User.objects.filter(telegram_id=tg["id"]).exclude(pk=user.pk).exists():
            form.add_error(None, "Этот Telegram уже привязан к другому аккаунту.")
        else:
            user.telegram_id = tg["id"]
            user.telegram_username = tg.get("username", "")
            user.save(update_fields=["telegram_id", "telegram_username"])
            request.session.pop(SESSION_PROFILE, None)
            _login(request, user, request.session.get("in_telegram", False))
            return redirect("password_change" if user.must_change_password else "home")
    login_error = next((error.code for error in form.non_field_errors().as_data()), None) if form.is_bound else None
    return render(request, "accounts/telegram_link.html", {"form": form, "login_error": login_error})


@login_required
@require_POST
def unlink(request):
    request.user.telegram_id = None
    request.user.telegram_username = ""
    request.user.save(update_fields=["telegram_id", "telegram_username"])
    messages.success(request, "Telegram отвязан.")
    return redirect("profile")


@login_required
@require_POST
def notifications(request):
    """T7: переключатели уведомлений бота."""
    fields = ["notify_messages", "notify_events", "notify_digest"] + (["notify_requests"] if request.user.is_administrator else [])
    for field in fields:
        setattr(request.user, field, request.POST.get(field) == "on")
    request.user.save(update_fields=fields)
    if request.headers.get("X-Requested-With") == "fetch":
        return JsonResponse({"ok": True})
    messages.success(request, "Настройки уведомлений сохранены.")
    return redirect("profile")


@csrf_exempt
@require_POST
def webhook(request):
    """Обновления от Telegram: /start и кнопки «Подтвердить» под запросами на подтверждение аккаунта."""
    if not telegram.enabled() or not constant_time_compare(request.headers.get("X-Telegram-Bot-Api-Secret-Token", ""), settings.TELEGRAM_WEBHOOK_SECRET):
        return HttpResponseForbidden()
    try:
        update = json.loads(request.body.decode())
    except ValueError:
        return HttpResponse(status=400)
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    command = (message.get("text", "").split() or [""])[0]
    if chat.get("type") != "private":
        command = ""  # бот работает только в личных чатах
    if command == "/start":
        payload = {"chat_id": chat["id"], "text": "Здравствуйте! Это бот офиса New Territory: календарь помещений, бронирование и сообщения. Откройте приложение кнопкой ниже."}
        url = telegram.app_url("/tg/")
        if url:
            payload["reply_markup"] = {"inline_keyboard": [[{"text": "Открыть календарь", "web_app": {"url": url}}]]}
        telegram.call("sendMessage", payload)
    elif command == "/today":
        digest.send_today(chat["id"])
    callback = update.get("callback_query")
    if callback:
        _handle_callback(callback)
    return HttpResponse("ok")


def _handle_callback(callback):
    admin = User.objects.filter(telegram_id=(callback.get("from") or {}).get("id"), is_superuser=True, is_active=True).first()
    action, _, pk = (callback.get("data") or "").partition(":")
    answer = "Нет доступа"
    if admin and action == "verify" and pk.isdigit():
        target = User.objects.filter(pk=int(pk)).first()
        if target and access.verify(target):
            answer = "Аккаунт подтверждён"
            source = callback.get("message") or {}
            if source.get("chat"):
                telegram.call("editMessageText", {"chat_id": source["chat"]["id"], "message_id": source["message_id"], "text": f"✓ Аккаунт подтверждён: {target.last_name} {target.first_name} · @{target.username}"})
        else:
            answer = "Уже подтверждён"
    telegram.call("answerCallbackQuery", {"callback_query_id": callback.get("id"), "text": answer})


@login_required
@require_POST
def request_verification(request):
    """«Запросить подтверждение» (макеты 34, 37): администраторы получают запрос в «Управлении» и в боте."""
    sent = access.request_verification(request.user)
    if request.headers.get("X-Requested-With") == "fetch":
        return JsonResponse({"sent": sent or bool(request.user.verification_requested_at)})
    if sent:
        messages.success(request, "Запрос отправлен администраторам. Когда аккаунт подтвердят, ограничения снимутся.")
    from django.utils.http import url_has_allowed_host_and_scheme
    target = request.POST.get("next", "")
    return redirect(target if url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()) else "profile")
