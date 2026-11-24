"""Сетка месяца: полные недели с днями соседних месяцев, точки и короткие подписи встреч.

Подписи учитывают скрытые детали: чужая Private-встреча подписана «Занято».
"""
import calendar
from collections import defaultdict
from datetime import date, timedelta
from .models import Event

CHIPS_PER_DAY = 3


def shift_month(day, offset):
    index = day.year * 12 + day.month - 1 + offset
    year, month_index = divmod(index, 12)
    if not 1900 <= year <= 9999:
        return None
    month = month_index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _grid_dates(day):
    """Даты полных недель месяца (с понедельника). За границей допустимых дат — None."""
    first = day.replace(day=1)
    last = first.replace(day=calendar.monthrange(day.year, day.month)[1])
    cells = []
    for offset in range(-first.weekday(), (last - first).days + 7 - last.weekday()):
        try:
            cells.append(first + timedelta(days=offset))
        except OverflowError:
            cells.append(None)
    return [cells[i:i + 7] for i in range(0, len(cells), 7)]


def month_grid(day, today, user=None):
    weeks_dates = _grid_dates(day)
    dates = [value for week in weeks_dates for value in week if value]
    events = (Event.objects.filter(date__range=(dates[0], dates[-1])).exclude(status=Event.Status.CANCELLED)
              .only('id', 'date', 'start_time', 'end_time', 'title', 'hide_details', 'author_id')
              .prefetch_related('rooms').order_by('date', 'start_time', 'pk'))
    days = defaultdict(list)
    for event in events:
        days[event.date].append(event)
    summary = {}
    for event_date, items in days.items():
        room_ends = {}
        conflict = False
        for event in items:
            for room in event.rooms.all():
                if room.pk in room_ends and event.start_time < room_ends[room.pk]:
                    conflict = True
                room_ends[room.pk] = max(room_ends.get(room.pk, event.end_time), event.end_time)
        summary[event_date] = (len(items), conflict)
    weeks = []
    for week in weeks_dates:
        cells = []
        for value in week:
            if value is None:
                cells.append(None)
                continue
            outside = value.month != day.month
            count, conflict = summary.get(value, (0, False))
            items = []
            for event in days.get(value, [])[:CHIPS_PER_DAY]:
                visible = not event.hide_details or (user is not None and event.can_edit(user))
                first_room = next(iter(event.rooms.all()), None)
                items.append({'time': event.start_time, 'title': event.title if visible else 'Занято', 'private': not visible, 'color': first_room.color if first_room else 'hall'})
            cells.append({'date': value, 'number': value.day, 'outside': outside, 'count': count, 'conflict': conflict,
                          'items': items, 'more': max(0, count - CHIPS_PER_DAY),
                          'today': value == today, 'selected': value == day})
        weeks.append(cells)
    return weeks
