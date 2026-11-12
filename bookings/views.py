from datetime import date, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .forms import EventForm
from .layout import day_layout
from .models import Event


def selected_day(value):
    try:
        day = date.fromisoformat(value) if value else timezone.localdate()
        # Leave room for previous/next navigation within HTML date input's range.
        if not date(1900, 1, 2) <= day <= date(9999, 12, 30):
            raise ValueError
        return day
    except (ValueError, TypeError):
        return timezone.localdate()

@login_required
@require_http_methods(["GET"])
def calendar(request):
    day = selected_day(request.GET.get("date"))
    events = list(Event.objects.filter(date=day).exclude(status=Event.Status.CANCELLED).select_related("responsible").prefetch_related("rooms"))
    context = {"day": day, "previous": day - timedelta(days=1), "next": day + timedelta(days=1), "today": timezone.localdate(), "event_count": len(events), **day_layout(events, request.user)}
    return render(request, "bookings/calendar.html", context)

@login_required
@require_http_methods(["GET"])
def detail(request, pk):
    event = get_object_or_404(Event.objects.select_related("author", "responsible").prefetch_related("rooms"), pk=pk)
    conflicts = event.conflicts().select_related("responsible", "author").prefetch_related("rooms")
    return render(request, "bookings/detail.html", {"event": event.visible_to(request.user, bool(conflicts)), "can_edit": event.can_edit(request.user), "conflicts": [item.visible_to(request.user) for item in conflicts]})

@login_required
@require_http_methods(["GET", "POST"])
def create(request):
    day = selected_day(request.GET.get("date"))
    form = EventForm(request.POST if request.method == "POST" else None, initial={"date": day, "responsible": request.user, "people_count": 1})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            event = form.save(commit=False)
            event.author = request.user
            event.save()
            form.save_m2m()
        messages.success(request, "Мероприятие добавлено.")
        return redirect(f"{reverse('home')}?date={event.date.isoformat()}")
    return render(request, "bookings/form.html", {"form": form, "title": "Новая встреча", "day": day})

@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def edit(request, pk):
    event = get_object_or_404(Event.objects.select_for_update(), pk=pk)
    original = (event.date, event.start_time, event.end_time, set(event.rooms.values_list("pk", flat=True)))
    if not event.can_edit(request.user):
        return HttpResponseForbidden("Изменить мероприятие могут только автор и администратор.")
    form = EventForm(request.POST if request.method == "POST" else None, instance=event)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            changed = form.save(commit=False)
            current = (changed.date, changed.start_time, changed.end_time, {room.pk for room in form.cleaned_data["rooms"]})
            if changed.status == Event.Status.CONFIRMED and not request.user.is_administrator and current != original:
                changed.status = Event.Status.PENDING
            changed.save()
            form.save_m2m()
        messages.success(request, "Изменения сохранены.")
        return redirect("event_detail", pk=event.pk)
    return render(request, "bookings/form.html", {"form": form, "title": "Изменить встречу", "event": event, "day": event.date})


@login_required
@require_http_methods(["POST"])
@transaction.atomic
def change_status(request, pk, action):
    event = get_object_or_404(Event.objects.select_for_update(), pk=pk)
    if action == "confirm":
        if not request.user.is_administrator:
            return HttpResponseForbidden("Подтверждение доступно только администратору.")
        if event.status != Event.Status.PENDING:
            messages.error(request, "Подтвердить можно только мероприятие на подтверждении.")
            return redirect("event_detail", pk=event.pk)
        event.status = Event.Status.CONFIRMED
    elif action in {"cancel", "resubmit"}:
        if not event.can_edit(request.user):
            return HttpResponseForbidden("Доступ только автору и администратору.")
        if action == "resubmit" and event.status != Event.Status.CANCELLED:
            messages.error(request, "Повторно отправить можно только отменённое мероприятие.")
            return redirect("event_detail", pk=event.pk)
        event.status = Event.Status.CANCELLED if action == "cancel" else Event.Status.PENDING
    else:
        from django.http import Http404
        raise Http404
    event.save(update_fields=["status", "updated_at"])
    messages.success(request, {"confirm": "Мероприятие подтверждено.", "cancel": "Мероприятие отменено.", "resubmit": "Мероприятие отправлено на подтверждение."}[action])
    return redirect("event_detail", pk=event.pk)

@login_required
@require_http_methods(["GET"])
def cancelled(request):
    from django.core.paginator import Paginator
    events = Event.objects.filter(status=Event.Status.CANCELLED).select_related("author", "responsible").prefetch_related("rooms").order_by("-date", "-start_time", "-pk")
    page = Paginator(events, 20).get_page(request.GET.get("page"))
    return render(request, "bookings/cancelled.html", {"events": [event.visible_to(request.user) for event in page], "page": page})

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
