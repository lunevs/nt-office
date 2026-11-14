"""Compact month summaries without exposing event details."""
import calendar
from collections import defaultdict
from datetime import date
from .models import Event


def shift_month(day, offset):
    index = day.year * 12 + day.month - 1 + offset
    year, month_index = divmod(index, 12)
    if not 1900 <= year <= 9999:
        return None
    month = month_index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def month_grid(day, today):
    events = Event.objects.filter(date__year=day.year, date__month=day.month).exclude(status=Event.Status.CANCELLED).only('id', 'date', 'start_time', 'end_time').prefetch_related('rooms').order_by('date', 'start_time', 'pk')
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
    for week in calendar.Calendar(firstweekday=0).monthdayscalendar(day.year, day.month):
        cells = []
        for number in week:
            if not number:
                cells.append(None)
                continue
            value = date(day.year, day.month, number)
            count, conflict = summary.get(value, (0, False))
            cells.append({'date': value, 'number': number, 'count': count, 'conflict': conflict, 'today': value == today, 'selected': value == day})
        weeks.append(cells)
    return weeks
