import hashlib

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

class User(AbstractUser):
    must_change_password = models.BooleanField(default=False)
    session_version = models.PositiveIntegerField(default=0, editable=False)

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
    def is_administrator(self):
        return self.is_active and self.is_superuser


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()
