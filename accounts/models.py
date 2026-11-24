import hashlib

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

class User(AbstractUser):
    must_change_password = models.BooleanField(default=False)
    session_version = models.PositiveIntegerField(default=0, editable=False)
    # Подтверждённый аккаунт: без ограничений на бронирование. Неподтверждённый — одна встреча в день,
    # до 2 часов, без повтора. Подтверждение запрашивают у администратора.
    verified = models.BooleanField("Аккаунт подтверждён", default=False)
    verification_requested_at = models.DateTimeField("Запрошено подтверждение", null=True, blank=True, db_index=True)
    # Telegram: вход без пароля на сайте и в мини-приложении, уведомления от бота.
    telegram_id = models.BigIntegerField("Telegram ID", null=True, blank=True, unique=True)
    telegram_username = models.CharField("Имя в Telegram", max_length=64, blank=True)
    notify_messages = models.BooleanField("Уведомлять о сообщениях", default=True)
    notify_events = models.BooleanField("Уведомлять об изменениях моих встреч", default=True)
    notify_requests = models.BooleanField("Уведомлять о заявках на доступ", default=True)
    notify_digest = models.BooleanField("Утренняя сводка в Telegram", default=True)

    def _versioned_session_hash(self, value):
        if not self.session_version:
            return value
        return hashlib.sha256(f"{value}:{self.session_version}".encode()).hexdigest()

    def get_session_auth_hash(self):
        return self._versioned_session_hash(super().get_session_auth_hash())

    def get_session_auth_fallback_hash(self):
        for value in super().get_session_auth_fallback_hash():
            yield self._versioned_session_hash(value)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("username"), name="unique_username_case_insensitive")]

    @property
    def short_name(self):
        """«Смирнова О.» — как в карточках встреч."""
        initial = f" {self.first_name[:1]}." if self.first_name else ""
        return f"{self.last_name}{initial}".strip() or self.username

    @property
    def is_verified(self):
        return self.verified or self.is_superuser

    @property
    def is_administrator(self):
        return self.is_active and self.is_superuser


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()



class DailyDigest(models.Model):
    """Отметка, что утренняя сводка за день разослана: из нескольких процессов отправит только один."""
    day = models.DateField("День", unique=True)
    sent_at = models.DateTimeField("Разослано", auto_now_add=True)
    recipients = models.PositiveIntegerField("Получателей", default=0)

    class Meta:
        verbose_name = "утренняя сводка"
        verbose_name_plural = "утренние сводки"


class TelegramLoginRequest(models.Model):
    """Вход через бота из установленного приложения (макет PWA 22): приложение ждёт, пока человек подтвердит вход в Telegram."""
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    telegram = models.JSONField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
