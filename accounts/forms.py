from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, SetPasswordForm, PasswordChangeForm
from django.contrib.auth import get_user_model

User = get_user_model()

class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(label="Имя", max_length=150)
    last_name = forms.CharField(label="Фамилия", max_length=150)

    class Meta:
        model = User
        fields = ("username", "last_name", "first_name", "password1", "password2")
        labels = {"username": "Логин"}
        help_texts = {"username": "Логин: латиница, цифры, точка или _"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Макет 11: одно поле пароля. Повтор скрыт и берётся из основного, проверки надёжности не теряются.
        self.fields["password2"].required = False
        self.fields["password2"].widget = forms.HiddenInput()
        self.fields["password1"].widget.attrs["placeholder"] = "Пароль, минимум 5 символов"
        for name, placeholder in (("last_name", "Фамилия"), ("first_name", "Имя"), ("username", "Логин")):
            self.fields[name].widget.attrs["placeholder"] = placeholder
        self.fields["username"].widget.attrs.update({"autocapitalize": "none", "autocomplete": "username"})
        self.order_fields(["last_name", "first_name", "username", "password1", "password2"])

    def clean(self):
        if self.cleaned_data.get("password1") and not self.cleaned_data.get("password2"):
            self.cleaned_data["password2"] = self.cleaned_data["password1"]
        return super().clean()

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Этот логин уже занят.")
        return username

    def save(self, commit=True):
        # Доступ сразу; ограничения на бронирование снимает подтверждение аккаунта администратором.
        user = super().save(commit=False)
        user.is_active = True
        user.verified = False
        if commit:
            user.save()
        return user

class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "username", "autocapitalize": "none", "placeholder": "Логин"}))
    password = forms.CharField(label="Пароль", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Пароль"}))
    error_messages = {"invalid_login": "Неверный логин или пароль", "inactive": "Аккаунт заблокирован"}

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()

    def clean(self):
        try:
            return super().clean()
        except forms.ValidationError:
            # Макет 17: о блокировке говорим только тому, кто ввёл верный пароль.
            username, password = self.cleaned_data.get("username"), self.cleaned_data.get("password")
            blocked = User.objects.filter(username__iexact=username, is_active=False).first() if username and password else None
            if blocked and blocked.check_password(password):
                raise forms.ValidationError(self.error_messages["inactive"], code="inactive")
            raise

class TemporaryPasswordForm(SetPasswordForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["new_password1"].help_text = password_help(user)

    # Макет 31: пароль придуман за администратора и виден целиком; повтор заполняется сам.
    new_password1 = forms.CharField(label="Временный пароль", strip=False, widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "none", "spellcheck": "false"}), help_text="Передайте пароль пользователю лично.")
    new_password2 = forms.CharField(label="Повторите временный пароль", strip=False, widget=forms.HiddenInput())

class ProfileNameForm(forms.ModelForm):
    first_name = forms.CharField(label="Имя", max_length=150)
    last_name = forms.CharField(label="Фамилия", max_length=150)

    class Meta:
        model = User
        fields = ("last_name", "first_name")

class ProfileLoginForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username",)
        labels = {"username": "Логин"}
        help_texts = {"username": "Для следующего входа используйте новый логин. Регистр букв не учитывается."}
        widgets = {"username": forms.TextInput(attrs={"autocomplete": "username", "autocapitalize": "none"})}

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Этот логин уже занят — попробуйте другой")
        return username


def password_help(user):
    from django.contrib.auth.password_validation import password_validators_help_text_html
    help_text = password_validators_help_text_html()
    if user.is_superuser:
        help_text = help_text.replace("не менее 5 символов", "не менее 10 символов")
    from django.utils.safestring import mark_safe
    return mark_safe(help_text)

class AccountPasswordChangeForm(PasswordChangeForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["new_password1"].help_text = password_help(user)
        self.fields["old_password"].label = "Текущий пароль"
        self.fields["new_password1"].label = "Новый пароль"
        self.fields["new_password2"].label = "Повторите новый пароль"


class ForcedPasswordForm(SetPasswordForm):
    """Первый вход после сброса (макет 19): временный пароль уже введён при входе, повторно не спрашиваем."""
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["new_password1"].help_text = password_help(user)
        self.fields["new_password1"].label = "Новый пароль"
        self.fields["new_password2"].label = "Повторите пароль"

    def clean_new_password1(self):
        password = self.cleaned_data.get("new_password1")
        if password and self.user.check_password(password):
            raise forms.ValidationError("Новый пароль должен отличаться от временного.")
        return password


TEMPORARY_WORDS = ("sad", "les", "most", "reka", "park", "svet", "dom", "gora", "pole", "utro", "zvezda", "luna")


def generate_temporary_password():
    """Читаемый временный пароль вроде sad-4821 (латиницей, чтобы не путать раскладку); у админов — длиннее."""
    import secrets
    words = "-".join(secrets.choice(TEMPORARY_WORDS) for _ in range(2))
    return f"{words}-{secrets.randbelow(9000) + 1000}"



class TelegramJoinForm(forms.ModelForm):
    """T1: аккаунт из данных Telegram. Пароль не нужен — входить можно через Telegram, задать пароль позже."""
    last_name = forms.CharField(label="Фамилия", max_length=150)
    first_name = forms.CharField(label="Имя", max_length=150)

    class Meta:
        model = User
        fields = ("last_name", "first_name", "username")
        labels = {"username": "Логин"}
        widgets = {"username": forms.TextInput(attrs={"autocapitalize": "none", "autocomplete": "username"})}

    def __init__(self, *args, telegram, **kwargs):
        self.telegram = telegram
        suggested = (telegram.get("username") or "").lower()
        if suggested and User.objects.filter(username__iexact=suggested).exists():
            suggested = ""
        kwargs.setdefault("initial", {"last_name": telegram.get("last_name", ""), "first_name": telegram.get("first_name", ""), "username": suggested})
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Этот логин уже занят — попробуйте другой")
        return username

    def clean(self):
        data = super().clean()
        if User.objects.filter(telegram_id=self.telegram["id"]).exists():
            raise forms.ValidationError("Этот Telegram уже привязан к аккаунту.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_unusable_password()
        user.is_active = True
        user.verified = False
        user.telegram_id = self.telegram["id"]
        user.telegram_username = self.telegram.get("username", "")
        if commit:
            user.save()
        return user
