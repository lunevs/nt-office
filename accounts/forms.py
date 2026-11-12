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
        help_texts = {"username": "Буквы, цифры и символы @ . + - _. Логин не зависит от регистра."}

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Этот логин уже занят.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False
        if commit:
            user.save()
        return user

class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "username", "autocapitalize": "none"}))
    password = forms.CharField(label="Пароль", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    error_messages = {"invalid_login": "Проверьте логин и пароль. Если вы только зарегистрировались, дождитесь активации администратором.", "inactive": "Учётная запись ещё не активирована."}

    def clean_username(self):
        return self.cleaned_data["username"].strip().lower()

class TemporaryPasswordForm(SetPasswordForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["new_password1"].help_text = password_help(user)

    new_password1 = forms.CharField(label="Временный пароль", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), help_text="Передайте пароль пользователю лично.")
    new_password2 = forms.CharField(label="Повторите временный пароль", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

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
            raise forms.ValidationError("Этот логин уже занят.")
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
