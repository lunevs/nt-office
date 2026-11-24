from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from accounts import telegram


class Command(BaseCommand):
    help = "Настроить бота: вебхук, кнопку меню «Календарь» (мини-приложение) и команду /start. Нужны TELEGRAM_BOT_TOKEN и публичный SITE_URL."

    def add_arguments(self, parser):
        parser.add_argument("--if-configured", action="store_true", help="При запуске сервера: без токена или публичного адреса просто пропустить.")

    def handle(self, *args, **options):
        configured = telegram.enabled() and settings.SITE_URL.startswith("https://")
        if options["if_configured"] and not configured:
            self.stdout.write("Telegram не настроен — пропускаю.")
            return
        if not telegram.enabled():
            raise CommandError("Не задан TELEGRAM_BOT_TOKEN.")
        if not settings.SITE_URL.startswith("https://"):
            raise CommandError("Нужен публичный HTTPS-адрес: задайте SITE_URL (на Railway берётся из RAILWAY_PUBLIC_DOMAIN).")
        steps = [
            ("setWebhook", {"url": settings.SITE_URL + reverse("telegram_webhook"), "secret_token": settings.TELEGRAM_WEBHOOK_SECRET, "allowed_updates": ["message", "callback_query"], "drop_pending_updates": False}),
            ("setChatMenuButton", {"menu_button": {"type": "web_app", "text": "Календарь", "web_app": {"url": settings.SITE_URL + reverse("telegram_entry")}}}),
            ("setMyCommands", {"commands": [{"command": "start", "description": "Открыть календарь офиса"}]}),
        ]
        for method, payload in steps:
            result = telegram.call(method, payload, timeout=10)
            ok = bool(result and result.get("ok"))
            self.stdout.write(f"{method}: {'готово' if ok else 'ошибка — ' + str((result or {}).get('description', 'нет ответа'))}")
        self.stdout.write("Дальше в @BotFather: /setdomain — домен сайта (для кнопки «Войти через Telegram»), /newapp или «Configure Mini App» — адрес " + settings.SITE_URL + reverse("telegram_entry"))
