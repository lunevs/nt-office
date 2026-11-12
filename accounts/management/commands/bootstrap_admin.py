import os
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

class Command(BaseCommand):
    help = "Create the initial administrator from BOOTSTRAP_ADMIN_* variables; never overwrite existing users."

    def handle(self, *args, **options):
        User = get_user_model()
        with transaction.atomic():
            if User.objects.filter(is_superuser=True).exists():
                self.stdout.write("Administrator already exists; no changes.")
                return
            username = os.getenv("BOOTSTRAP_ADMIN_LOGIN", "").strip().lower()
            password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
            if not username or not password:
                self.stdout.write("Bootstrap skipped; set BOOTSTRAP_ADMIN_LOGIN and BOOTSTRAP_ADMIN_PASSWORD.")
                return
            user = User(username=username, first_name=os.getenv("BOOTSTRAP_ADMIN_FIRST_NAME", "Администратор"), last_name=os.getenv("BOOTSTRAP_ADMIN_LAST_NAME", ""), is_active=True, is_staff=True, is_superuser=True, must_change_password=True)
            try:
                user.full_clean(exclude=["password"])
                validate_password(password, user)
            except ValidationError:
                raise CommandError("Invalid bootstrap login or password; use a unique valid login and a strong password of at least 10 characters.") from None
            user.set_password(password)
            user.save()
        self.stdout.write(self.style.SUCCESS("Initial administrator created. Change the password on first login and remove bootstrap variables."))
