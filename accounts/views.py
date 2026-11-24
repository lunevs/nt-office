import hashlib
from datetime import timedelta
from functools import wraps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from .forms import AccountPasswordChangeForm, ForcedPasswordForm, generate_temporary_password
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.views.decorators.debug import sensitive_post_parameters
from .forms import RegistrationForm, LoginForm, TemporaryPasswordForm
from .models import LoginAttempt
from . import access, telegram

User = get_user_model()

def administrator_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_administrator:
            return HttpResponseForbidden("Доступ только для администратора.")
        return view(request, *args, **kwargs)
    return wrapped

@login_required
def home(request):
    return render(request, "accounts/home.html")

@require_GET
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return JsonResponse({"status": "ok"})
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)

@sensitive_post_parameters()
def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
        except IntegrityError:
            form.add_error("username", "Этот логин уже занят — попробуйте другой")
        else:
            login(request, user)
            messages.success(request, "Аккаунт создан. Пока он не подтверждён, можно бронировать одну встречу в день до 2 часов.")
            return redirect("home")
    return render(request, "accounts/register.html", {"form": form})

@sensitive_post_parameters()
def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST":
        # Persistent per-login limit works across workers/restarts; do not trust forwarded IP headers.
        key = hashlib.sha256(request.POST.get("username", "").strip().lower().encode()).hexdigest()
        now = timezone.now()
        with transaction.atomic():
            attempt, _ = LoginAttempt.objects.select_for_update().get_or_create(key=key, defaults={"started_at": now})
            if attempt.started_at < now - timedelta(minutes=15):
                attempt.attempts = 0
                attempt.started_at = now
            if attempt.attempts >= 10:
                return render(request, "accounts/login.html", {"form": form, "login_error": "throttled"}, status=429)
            attempt.attempts += 1
            attempt.save()
        if form.is_valid():
            LoginAttempt.objects.filter(key=key).delete()
            login(request, form.get_user())
            if request.user.must_change_password:
                return redirect("password_change")
            from django.utils.http import url_has_allowed_host_and_scheme
            target = request.GET.get("next", "")
            return redirect(target if url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()) else "home")
    login_error = next((error.code for error in form.non_field_errors().as_data()), None) if form.is_bound else ("inactive" if request.GET.get("blocked") else None)
    # Экран приветствия (макет 09) — если подключён Telegram и человек ещё не выбрал вход по логину.
    if not form.is_bound and not login_error and telegram.enabled() and request.GET.get("method") != "password":
        return render(request, "accounts/welcome.html", {"bot_username": settings.TELEGRAM_BOT_USERNAME})
    return render(request, "accounts/login.html", {"form": form, "login_error": login_error})

@require_POST
@login_required
def logout_view(request):
    logout(request)
    return redirect("login")

@login_required
def profile(request):
    from bookings.models import Event
    now = timezone.localtime()
    upcoming = Event.objects.filter(responsible=request.user).exclude(status=Event.Status.CANCELLED).filter(
        Q(date__gt=now.date()) | Q(date=now.date(), end_time__gt=now.time())
    ).select_related("author", "responsible").prefetch_related("rooms").order_by("date", "start_time", "pk")[:3]
    cancelled_count = Event.objects.filter(author=request.user, status=Event.Status.CANCELLED).count()
    return render(request, "accounts/profile.html", {"upcoming_events": [event.visible_to(request.user) for event in upcoming], "cancelled_count": cancelled_count, "telegram_enabled": telegram.enabled()})

@login_required
@sensitive_post_parameters()
def password_change(request):
    forced = request.user.must_change_password
    form = (ForcedPasswordForm if forced else AccountPasswordChangeForm)(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save(commit=False)
            user.must_change_password = False
            user.save(update_fields=["password", "must_change_password"])
        update_session_auth_hash(request, user)
        messages.success(request, "Пароль изменён.")
        return redirect("profile")
    minimum = 10 if request.user.is_superuser else 5
    return render(request, "accounts/password.html", {"form": form, "forced": forced, "minimum": minimum})

@administrator_required
def users(request):
    reset = request.session.pop("password_reset", None)
    reset_user = User.objects.filter(pk=reset["pk"]).first() if reset else None
    from bookings.models import Event
    all_users = list(User.objects.all().order_by("last_name", "first_name", "username"))
    requests = sorted((u for u in all_users if u.is_active and not u.is_verified and u.verification_requested_at), key=lambda u: u.verification_requested_at, reverse=True)
    keys = Event.objects.filter(key_needed=True, key_handled=False, status=Event.Status.ACTIVE, date__gte=timezone.localdate()).select_related("author").prefetch_related("rooms").order_by("date", "start_time")
    return render(request, "accounts/users.html", {"all_users": all_users, "requests": requests, "keys": keys, "blocked_count": sum(not u.is_active for u in all_users), "reset_user": reset_user, "reset_password": reset["password"] if reset_user else None})

@require_POST
@administrator_required
@transaction.atomic
def user_access(request, pk, action):
    from django.http import Http404
    if action not in {"block", "unblock", "verify", "reject"}:
        raise Http404
    user = get_object_or_404(User.objects.select_for_update(), pk=pk)
    if action in {"verify", "reject"}:
        name = user.get_full_name() or user.username
        done = access.verify(user) if action == "verify" else access.reject(user)
        if done:
            messages.success(request, f"Аккаунт подтверждён: {name}." if action == "verify" else f"Запрос отклонён: {name}.")
        return redirect("users")
    if user.pk == request.user.pk or user.is_superuser:
        return HttpResponseForbidden("Учётную запись администратора заблокировать нельзя.")
    if action == "block":
        if user.is_active:
            user.is_active = False
            user.session_version += 1
            user.save(update_fields=["is_active", "session_version"])
        messages.success(request, "Пользователь заблокирован.")
    else:
        user.is_active = True
        user.save(update_fields=["is_active"])
        LoginAttempt.objects.filter(key=hashlib.sha256(user.username.lower().encode()).hexdigest()).delete()
        messages.success(request, "Пользователь разблокирован. Он может войти с прежним паролем.")
    return redirect("users")

@administrator_required
@sensitive_post_parameters()
def reset_password(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        return redirect("password_change")
    form = TemporaryPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save(commit=False)
            user.must_change_password = True
            user.save(update_fields=["password", "must_change_password"])
            LoginAttempt.objects.filter(key=hashlib.sha256(user.username.lower().encode()).hexdigest()).delete()
        # Временный пароль показываем один раз на экране «Пароль сброшен» и сразу убираем из сессии.
        request.session["password_reset"] = {"pk": user.pk, "password": form.cleaned_data["new_password1"]}
        return redirect("users")
    if request.method == "GET":
        suggestion = generate_temporary_password()
        form = TemporaryPasswordForm(user, initial={"new_password1": suggestion, "new_password2": suggestion})
    name = user.first_name or user.username
    return render(request, "accounts/sheet_form.html", {"form": form, "title": "Сбросить пароль?", "subtitle": f"{user.get_full_name() or user.username} · @{user.username}. Старый пароль перестанет работать, а при следующем входе {name} задаст свой.", "submit": "Сбросить пароль", "submit_style": "danger", "cancel_url": reverse("users"), "temporary_password": True, "minimum": 10 if user.is_superuser else 5})

@login_required
@require_http_methods(["GET", "POST"])
def profile_edit(request, field):
    from .forms import ProfileNameForm, ProfileLoginForm
    from django.http import Http404
    if field not in {"name", "login"}:
        raise Http404
    form_class = ProfileNameForm if field == "name" else ProfileLoginForm
    form = form_class(request.POST if request.method == "POST" else None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save(commit=False)
                user.save(update_fields=list(form_class.Meta.fields))
        except IntegrityError:
            form.add_error("username", "Этот логин уже занят — попробуйте другой")
        else:
            messages.success(request, "Имя обновлено." if field == "name" else "Логин обновлён. Для следующего входа используйте новый логин.")
            return redirect("profile")
    if field == "name":
        context = {"title": "Имя", "subtitle": "Так вас видят в календаре и в сообщениях"}
    else:
        context = {"title": "Логин", "subtitle": "По нему вы входите. Латиница, цифры, точка и подчёркивание", "login_field": True}
    return render(request, "accounts/sheet_form.html", {**context, "form": form, "submit": "Сохранить", "submit_style": "primary", "cancel_url": reverse("profile")})
