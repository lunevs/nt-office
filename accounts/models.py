from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower

class User(AbstractUser):
    must_change_password = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("username"), name="unique_username_case_insensitive")]

    @property
    def is_administrator(self):
        return self.is_active and self.is_superuser


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()
