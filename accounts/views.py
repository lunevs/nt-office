import hashlib
from datetime import timedelta
from functools import wraps
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from .forms import AccountPasswordChangeForm
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django.views.decorators.debug import sensitive_post_parameters
from .forms import RegistrationForm, LoginForm, TemporaryPasswordForm
from .models import LoginAttempt

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
                form.save()
            return redirect("pending")
        except IntegrityError:
            form.add_error("username", "Этот логин уже занят.")
    return render(request, "accounts/form.html", {"form": form, "title": "Создать аккаунт", "subtitle": "После регистрации администратор откроет вам доступ.", "submit": "Зарегистрироваться", "registration": True})

def pending(request):
    return render(request, "accounts/pending.html")

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
                return render(request, "accounts/form.html", {"form": form, "title": "С возвращением", "subtitle": "Слишком много попыток. Попробуйте через 15 минут.", "submit": "Войти", "login_page": True}, status=429)
            attempt.attempts += 1
            attempt.save()
        if form.is_valid():
            LoginAttempt.objects.filter(key=key).delete()
            login(request, form.get_user())
            return redirect("password_change" if request.user.must_change_password else "home")
    return render(request, "accounts/form.html", {"form": form, "title": "С возвращением", "subtitle": "Войдите, чтобы пользоваться пространством вместе.", "submit": "Войти", "login_page": True})

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
    return render(request, "accounts/profile.html", {"upcoming_events": [event.visible_to(request.user) for event in upcoming]})

@login_required
@sensitive_post_parameters()
def password_change(request):
    form = AccountPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = form.save(commit=False)
            user.must_change_password = False
            user.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Пароль изменён.")
        return redirect("profile")
    return render(request, "accounts/form.html", {"form": form, "title": "Новый пароль", "subtitle": "Замените временный пароль своим." if request.user.must_change_password else "Введите текущий пароль и выберите новый.", "submit": "Сохранить пароль"})

@administrator_required
def users(request):
    from bookings.series import pending_review_cards
    pending_events = pending_review_cards(request.user)
    return render(request, "accounts/users.html", {"pending_events": pending_events, "pending_users": User.objects.filter(is_active=False).order_by("date_joined"), "active_users": User.objects.filter(is_active=True).order_by("last_name", "first_name")})

@require_POST
@administrator_required
def activate(request, pk):
    user = get_object_or_404(User, pk=pk)
    user.is_active = True
    user.save(update_fields=["is_active"])
    messages.success(request, "Учётная запись активирована.")
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
            user.save()
            LoginAttempt.objects.filter(key=hashlib.sha256(user.username.lower().encode()).hexdigest()).delete()
        messages.success(request, "Пароль сброшен. Передайте временный пароль пользователю лично. При входе он должен будет его сменить.")
        return redirect("users")
    return render(request, "accounts/form.html", {"form": form, "title": "Сбросить пароль", "subtitle": user.get_full_name() + " · @" + user.username, "submit": "Установить временный пароль", "back": True})

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
                form.save()
        except IntegrityError:
            form.add_error("username", "Этот логин уже занят.")
        else:
            messages.success(request, "Имя обновлено." if field == "name" else "Логин обновлён. Для следующего входа используйте новый логин.")
            return redirect("profile")
    return render(request, "accounts/form.html", {"form": form, "title": "Изменить имя" if field == "name" else "Изменить логин", "submit": "Сохранить", "profile_back": True})
