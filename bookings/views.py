from datetime import date, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .forms import EventForm
from .layout import day_layout
from .month import month_grid, shift_month
from .models import Event, Room
from accounts import access, telegram
from .series import create_events, lock_event, update_events, set_status


def selected_day(value):
    try:
        day = date.fromisoformat(value) if value else timezone.localdate()
        # Leave room for previous/next navigation within HTML date input's range.
        if not date(1900, 1, 2) <= day <= date(9999, 12, 30):
            raise ValueError
        return day
    except (ValueError, TypeError):
        return timezone.localdate()

WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def _minute(value):
    return value.hour * 60 + value.minute


def _clock(minutes):
    return f"{minutes // 60:02}:{minutes % 60:02}"


def _time_left(minutes):
    hours, rest = divmod(minutes, 60)
    parts = ([f"{hours} ч"] if hours else []) + ([f"{rest} мин"] if rest or not hours else [])
    return "ещё " + " ".join(parts)


def _shift_days(day, days):
    try:
        value = day + timedelta(days=days)
    except OverflowError:
        return None
    return value if date(1900, 1, 2) <= value <= date(9999, 12, 30) else None


def _rooms_now(events, now_minute):
    """Статус каждого помещения на текущую минуту — блок «Помещения сейчас» на компьютере."""
    statuses = []
    for room in Room.objects.all():
        items = [event for event in events if any(r.pk == room.pk for r in event.rooms.all())]
        current = next((e for e in items if _minute(e.start_time) <= now_minute < _minute(e.end_time)), None)
        if current:
            until = _minute(current.end_time)
            for event in items:  # встречи подряд считаем одним занятым отрезком
                if _minute(event.start_time) <= until < _minute(event.end_time):
                    until = _minute(event.end_time)
            statuses.append({"room": room, "busy": True, "label": f"Занято до {_clock(until)}"})
            continue
        upcoming = next((e for e in items if _minute(e.start_time) > now_minute), None)
        if upcoming:
            label = f"Свободно до {upcoming.start_time:%H:%M}"
        else:
            label = "Свободно до конца дня" if items else "Свободно весь день"
        statuses.append({"room": room, "busy": False, "label": label})
    return statuses


@login_required
@require_http_methods(["GET"])
def calendar(request):
    day = selected_day(request.GET.get("date"))
    today = timezone.localdate()
    now = timezone.localtime()
    now_minute = now.hour * 60 + now.minute if day == today else None
    events = list(Event.objects.filter(date=day).exclude(status=Event.Status.CANCELLED).select_related("responsible").prefetch_related("rooms"))
    context = {"day": day, "previous": day - timedelta(days=1), "next": day + timedelta(days=1), "today": today, "event_count": len(events), **day_layout(events, request.user, now_minute)}
    mode_key = f'calendar_mode_{request.user.pk}'
    requested_mode = request.GET.get('view')
    if requested_mode in {'day', 'month'}:
        request.session[mode_key] = requested_mode
    context['calendar_mode'] = request.session.get(mode_key, 'day')

    # Полоса недели: понедельник — воскресенье выбранного дня, точка — есть встречи.
    monday = day - timedelta(days=day.weekday())
    week = [value for value in (_shift_days(monday, i) for i in range(7)) if value]
    busy = set(Event.objects.filter(date__range=(week[0], week[-1])).exclude(status=Event.Status.CANCELLED).values_list("date", flat=True))
    context["week_days"] = [{"date": value, "label": WEEKDAYS_SHORT[value.weekday()], "today": value == today, "selected": value == day, "busy": value in busy} for value in week]
    context["previous_week"], context["next_week"] = _shift_days(day, -7), _shift_days(day, 7)

    # «Сейчас идёт» и статус помещений — только для сегодняшнего дня.
    if now_minute is not None:
        context["now_label"] = _clock(now_minute)
        current = next((e for e in events if _minute(e.start_time) <= now_minute < _minute(e.end_time)), None)
        if current:
            context["now_event"] = {**current.visible_to(request.user), "left": _time_left(_minute(current.end_time) - now_minute)}
        context["rooms_now"] = _rooms_now(events, now_minute)

    # Месяц: в режиме «Месяц» — основная сетка, в режиме «День» — мини-календарь на компьютере.
    context['month_weeks'] = month_grid(day, today, request.user)
    context['month_previous'], context['month_next'] = shift_month(day, -1), shift_month(day, 1)
    context['agenda'] = [event.visible_to(request.user) for event in events]
    if context['calendar_mode'] == 'month':
        context['previous'] = context['month_previous']
        context['next'] = context['month_next']
    return render(request, "bookings/calendar.html", context)

@login_required
@require_http_methods(["GET"])
def detail(request, pk):
    event = get_object_or_404(Event.objects.select_related("author", "responsible").prefetch_related("rooms"), pk=pk)
    conflicts = event.conflicts().select_related("responsible", "author").prefetch_related("rooms")
    return render(request, "bookings/detail.html", {"event": event.visible_to(request.user, bool(conflicts)), "can_edit": event.can_edit(request.user), "conflicts": [item.visible_to(request.user) for item in conflicts], "series": _series_info(event), "minutes": _minute(event.end_time) - _minute(event.start_time), "administrators": access.administrators(exclude=request.user) if event.key_needed else []})

EVERY_WEEKDAY = ("каждый понедельник", "каждый вторник", "каждую среду", "каждый четверг", "каждую пятницу", "каждую субботу", "каждое воскресенье")


def _form_context(form, day, event=None):
    """Данные для формы встречи по макетам 04 и 16: помещения с цветами, быстрые даты, сведения о серии."""
    selected = {str(value) for value in (form["rooms"].value() or [])}
    context = {
        "form": form, "day": day, "event": event,
        "room_options": [{"room": room, "checked": str(room.pk) in selected} for room in Room.objects.all()],
    }
    today = timezone.localdate()
    context["date_chips"] = [(today, "Сегодня"), (today + timedelta(days=1), "Завтра"), (today + timedelta(days=2), None)]
    if event:
        context["series"] = _series_info(event)
    return context


def _series_info(event):
    """«Каждый вторник до 22 декабря», «1 из 5» — для формы и страницы встречи."""
    if not event.series_id:
        return None
    dates = list(Event.objects.filter(series_id=event.series_id).exclude(status=Event.Status.CANCELLED).order_by("sequence").values_list("date", flat=True))
    dates = dates or [event.date]
    return {
        "every": EVERY_WEEKDAY[event.date.weekday()], "until": dates[-1],
        "index": dates.index(event.date) + 1 if event.date in dates else 1, "total": len(dates),
        "from": event.date, "following": len([value for value in dates if value >= event.date]),
    }


@login_required
@require_http_methods(["GET", "POST"])
def create(request):
    day = selected_day(request.GET.get("date"))
    # Как в макете 04: начало — ближайшие полчаса (для другого дня — 10:00), длительность 1,5 ч.
    now = timezone.localtime()
    start = min(max(((now.hour * 60 + now.minute) // 30 + 1) * 30 if day == timezone.localdate() else 600, 360), 21 * 60 + 30)
    initial = {"date": day, "responsible": request.user, "people_count": 1, "start_time": f"{start // 60:02}:{start % 60:02}", "end_time": f"{(start + 90) // 60:02}:{(start + 90) % 60:02}"}
    form = EventForm(request.POST if request.method == "POST" else None, initial=initial, user=request.user)
    if request.method == "POST" and form.is_valid():
        events = create_events(form, request.user)
        today = timezone.localdate()
        nearest = next((item for item in events if item.date >= today), events[-1])
        if form.cleaned_data.get("key_needed"):
            # Макет 35: на странице встречи — что запрос на ключ ушёл и кто ответит.
            access.key_requested(nearest, request.user)
            messages.success(request, "Встреча забронирована. Запрос на ключ отправлен администраторам.")
            return redirect("event_detail", pk=nearest.pk)
        messages.success(request, "Серия встреч добавлена." if len(events) > 1 else "Мероприятие добавлено.")
        return redirect(f"{reverse('home')}?date={nearest.date.isoformat()}")
    return render(request, "bookings/form.html", {**_form_context(form, day), "title": "Новая встреча"})

@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def edit(request, pk):
    get_object_or_404(Event, pk=pk)
    event = lock_event(pk)
    original = {"date": event.date}
    if not event.can_edit(request.user):
        return HttpResponseForbidden("Изменить мероприятие могут только автор и администратор.")
    before = (event.date, event.start_time, event.end_time)
    key_before = event.key_needed
    form = EventForm(request.POST if request.method == "POST" else None, instance=event, user=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                update_events(event, form, request.user, original)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            event.refresh_from_db()
            telegram.notify_event(event, request.user, "moved" if (event.date, event.start_time, event.end_time) != before else "changed")
            if event.key_needed and not key_before:
                Event.objects.filter(pk=event.pk).update(key_handled=False)
                access.key_requested(event, request.user)
                messages.success(request, "Изменения сохранены. Запрос на ключ отправлен администраторам.")
                return redirect("event_detail", pk=event.pk)
            messages.success(request, "Изменения сохранены.")
            return redirect("event_detail", pk=event.pk)
    return render(request, "bookings/form.html", {**_form_context(form, event.date, event), "title": "Изменить встречу"})


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def change_status(request, pk, action):
    get_object_or_404(Event, pk=pk)
    event = lock_event(pk)
    scope = request.POST.get("scope", "one")
    if scope not in {"one", "future", "all"}:
        return JsonResponse({"error": "Некорректная область изменения."}, status=400)
    if action not in {"cancel", "restore"}:
        from django.http import Http404
        raise Http404
    if not event.can_edit(request.user):
        return HttpResponseForbidden("Доступ только автору и администратору.")
    if action == "restore" and event.status != Event.Status.CANCELLED:
        messages.error(request, "Восстановить можно только отменённое мероприятие.")
        return redirect("event_detail", pk=event.pk)
    set_status(event, action, scope, request.user)
    event.refresh_from_db()
    telegram.notify_event(event, request.user, "cancelled" if action == "cancel" else "restored")
    messages.success(request, "Мероприятие отменено." if action == "cancel" else "Мероприятие восстановлено.")
    return redirect("event_detail", pk=event.pk)

@login_required
@require_http_methods(["GET"])
def cancelled(request):
    from django.core.paginator import Paginator
    events = Event.objects.filter(status=Event.Status.CANCELLED).select_related("author", "responsible").prefetch_related("rooms").order_by(F("cancelled_at").desc(nulls_last=True), "-pk")
    mine = not request.user.is_administrator or request.GET.get("mine") == "1"
    if mine:
        events = events.filter(author=request.user)
    page = Paginator(events, 20).get_page(request.GET.get("page"))
    items = [{**event.visible_to(request.user), "cancelled_at": event.cancelled_at, "can_edit": event.can_edit(request.user)} for event in page]
    return render(request, "bookings/cancelled.html", {"events": items, "page": page, "mine": mine})

@login_required
@require_http_methods(["GET"])
def event_data(request, pk):
    event = get_object_or_404(Event.objects.select_related("author", "responsible").prefetch_related("rooms"), pk=pk)
    data = event.visible_to(request.user, event.conflicts().exists())
    data["rooms"] = [{"id": room.pk, "name": room.name} for room in data["rooms"]]
    data["responsible"] = {"id": event.responsible_id, "name": event.responsible.get_full_name()}
    data.pop("author")
    if not data["details_visible"]:
        data.pop("people_count")
    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def key_handled(request, pk):
    """«Ключ выдан» (макет 36): только администратор."""
    if not request.user.is_administrator:
        return HttpResponseForbidden("Только для администратора.")
    Event.objects.filter(pk=pk, key_needed=True).update(key_handled=True)
    messages.success(request, "Отмечено: ключ выдан.")
    from django.utils.http import url_has_allowed_host_and_scheme
    target = request.POST.get("next", "")
    return redirect(target if url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure()) else "users")
