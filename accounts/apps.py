import os

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"

    def ready(self):
        # Утренняя сводка в Telegram: фоновый поток в каждом процессе Gunicorn.
        # Включается из start.sh; повторную рассылку исключает отметка DailyDigest в базе.
        if os.getenv("TELEGRAM_DIGEST_SCHEDULER") == "1":
            from . import digest
            digest.start_scheduler()
