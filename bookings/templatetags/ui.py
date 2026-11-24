from datetime import timedelta

from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def ru_plural(value, forms):
    """{{ 6|ru_plural:"встреча,встречи,встреч" }} → «6 встреч»."""
    one, few, many = forms.split(",")
    number = abs(int(value))
    if 10 < number % 100 < 20:
        form = many
    elif number % 10 == 1:
        form = one
    elif 2 <= number % 10 <= 4:
        form = few
    else:
        form = many
    return f"{value} {form}"


@register.filter
def duration_words(minutes):
    """120 → «2 часа», 90 → «1,5 часа», 45 → «45 минут», 75 → «1 ч 15 мин»."""
    minutes = int(minutes)
    hours, rest = divmod(minutes, 60)
    if not hours:
        return ru_plural(rest, "минута,минуты,минут")
    if rest == 30:
        return f"{hours},5 часа"
    if rest:
        return f"{hours} ч {rest} мин"
    return ru_plural(hours, "час,часа,часов")


WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
MONTHS_SHORT = ("янв.", "февр.", "марта", "апр.", "мая", "июня", "июля", "авг.", "сент.", "окт.", "нояб.", "дек.")


@register.filter
def chat_time(value):
    """Время в списке переписок: «10:24», «Вчера», «Пн», «18 нояб.»."""
    moment = timezone.localtime(value)
    today = timezone.localdate()
    day = moment.date()
    if day == today:
        return moment.strftime("%H:%M")
    if day == today - timedelta(days=1):
        return "Вчера"
    if today - day < timedelta(days=7):
        return WEEKDAYS_SHORT[day.weekday()]
    return f"{day.day} {MONTHS_SHORT[day.month - 1]}"


@register.filter
def chat_day(value):
    """Подпись дня в переписке: «Сегодня», «Вчера», «18 ноября»."""
    day = timezone.localtime(value).date()
    today = timezone.localdate()
    if day == today:
        return "Сегодня"
    if day == today - timedelta(days=1):
        return "Вчера"
    from django.utils.formats import date_format
    return date_format(day, "j E" if day.year == today.year else "j E Y")


@register.filter
def month_short(value):
    """«нояб.», «дек.» — как в макете профиля."""
    return MONTHS_SHORT[value.month - 1]
