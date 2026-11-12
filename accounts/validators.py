from django.core.exceptions import ValidationError

class RoleMinimumLengthValidator:
    def validate(self, password, user=None):
        minimum = 10 if user is not None and user.is_superuser else 5
        if len(password) < minimum:
            raise ValidationError(f"Пароль должен содержать не менее {minimum} символов.", code="password_too_short")

    def get_help_text(self):
        return "Пароль должен содержать не менее 5 символов."
