"""Подтверждение аккаунтов (снимает ограничения на бронирование) и запросы на ключ."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from . import telegram

User = get_user_model()

# Ограничения неподтверждённого аккаунта (макеты 34, 37).
MAX_MINUTES = 120


def request_verification(user):
    if user.is_verified or user.verification_requested_at:
        return False
    user.verification_requested_at = timezone.now()
    user.save(update_fields=["verification_requested_at"])
    telegram.notify_verification_request(user)
    return True


@transaction.atomic
def verify(user):
    if user.verified:
        return False
    user.verified = True
    user.verification_requested_at = None
    user.save(update_fields=["verified", "verification_requested_at"])
    telegram.notify_verified(user)
    return True


def reject(user):
    """Запрос отклонён: ограничения остаются, запросить можно снова."""
    if not user.verification_requested_at:
        return False
    user.verification_requested_at = None
    user.save(update_fields=["verification_requested_at"])
    return True


def administrators(exclude=None):
    """Контакты администраторов для человека, запросившего ключ (макет 35)."""
    people = User.objects.filter(is_superuser=True, is_active=True).order_by("last_name", "first_name")
    return [person for person in people if not exclude or person.pk != exclude.pk]


def key_requested(event, actor):
    """«Нужен ключ»: админам — встреча и чат с человеком, человеку — что запрос ушёл и кто ответит."""
    admins = administrators(exclude=actor)
    telegram.notify_key_request(event, actor, admins)
    telegram.notify_key_sent(event, actor, admins)
