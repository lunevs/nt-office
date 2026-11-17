"""Operations on explicit weekly occurrences, preserving identity across moves."""
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Event, EventSeries

FIELDS = ('title', 'date', 'start_time', 'end_time', 'people_count', 'responsible', 'hide_details')


def lock_event(pk):
    # All series mutations lock parent first, then occurrence rows in primary-key order.
    initial = Event.objects.only('series_id').get(pk=pk)
    if initial.series_id:
        EventSeries.objects.select_for_update().get(pk=initial.series_id)
    return Event.objects.select_for_update().get(pk=pk)


def targets(event, scope):
    if scope == 'all' and event.series_id:
        return list(Event.objects.select_for_update().filter(series_id=event.series_id).order_by('pk'))
    if scope == 'future' and event.series_id:
        return list(Event.objects.select_for_update().filter(series_id=event.series_id, sequence__gte=event.sequence).order_by('pk'))
    return [event]


@transaction.atomic
def create_events(form, user):
    data = form.cleaned_data
    dates = [data['date']]
    if data.get('repeat_weekly'):
        count = (data['repeat_until'] - data['date']).days // 7 + 1
        dates = [data['date'] + timedelta(weeks=index) for index in range(count)]
    series = EventSeries.objects.create() if data.get('repeat_weekly') else None
    result = []
    for index, day in enumerate(dates):
        event = Event(**{key: data[key] for key in FIELDS if key != 'date'}, date=day, author=user, series=series, sequence=index if series else None, status=Event.Status.ACTIVE)
        event.full_clean()
        event.save()
        event.rooms.set(data['rooms'])
        result.append(event)
    return result


def update_events(event, form, user, original):
    data = form.cleaned_data
    batch = targets(event, data.get('scope', 'one'))
    shift = data['date'] - original['date']
    rooms = list(data['rooms'])
    prepared = []
    for item in batch:
        if not item.can_edit(user):
            raise ValidationError('Нет прав на изменение одной из встреч серии.')
        # ModelForm has already mutated selected occurrence: use the captured original.
        old_date = original['date'] if item.pk == event.pk else item.date
        try:
            new_date = old_date + shift
        except OverflowError:
            raise ValidationError('Перенос выходит за допустимый диапазон дат.') from None
        for key in FIELDS:
            setattr(item, key, new_date if key == 'date' else data[key])
        item.full_clean()
        prepared.append(item)
    for item in prepared:
        item.save()
        item.rooms.set(rooms)
    return len(prepared)


def set_status(event, action, scope, user):
    batch = targets(event, scope)
    stamp = timezone.now()
    count = 0
    for item in batch:
        if not item.can_edit(user):
            raise ValidationError('Нет прав на изменение одной из встреч серии.')
        if action == 'cancel':
            if item.status == Event.Status.CANCELLED:
                continue
            item.status, item.cancelled_at = Event.Status.CANCELLED, stamp
        elif action == 'restore':
            if item.status != Event.Status.CANCELLED:
                continue
            item.status, item.cancelled_at = Event.Status.ACTIVE, None
        else:
            raise ValidationError('Неизвестное действие.')
        item.save(update_fields=['status', 'cancelled_at', 'updated_at'])
        count += 1
    return count
