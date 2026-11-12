from datetime import time
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

class Room(models.Model):
    name = models.CharField("Название", max_length=80, unique=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return self.name

class Event(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "На подтверждении"
        CONFIRMED = "confirmed", "Подтверждено"
        CANCELLED = "cancelled", "Отменено"

    status = models.CharField("Статус", max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    hide_details = models.BooleanField("Скрыть детали", default=False)

    title = models.CharField("Название", max_length=160)
    date = models.DateField("Дата", db_index=True)
    start_time = models.TimeField("Начало")
    end_time = models.TimeField("Окончание")
    rooms = models.ManyToManyField(Room, verbose_name="Помещения")
    people_count = models.PositiveIntegerField("Количество людей")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_events")
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="responsible_events", verbose_name="Ответственный")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date", "start_time", "pk"]
        constraints = [
            models.CheckConstraint(condition=models.Q(end_time__gt=models.F("start_time")), name="event_positive_duration"),
            models.CheckConstraint(condition=models.Q(start_time__gte=time(6), end_time__lte=time(23)), name="event_office_hours"),
            models.CheckConstraint(condition=models.Q(people_count__gte=1), name="event_positive_people"),
        ]

    def clean(self):
        errors = {}
        if self.start_time and self.start_time < time(6):
            errors["start_time"] = "Офис доступен с 06:00."
        if self.end_time and self.end_time > time(23):
            errors["end_time"] = "Мероприятие должно закончиться до 23:00 включительно."
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors["end_time"] = "Окончание должно быть позже начала в тот же день."
        for field in ("start_time", "end_time"):
            value = getattr(self, field)
            if value and (value.second or value.microsecond):
                errors[field] = "Укажите время с точностью до минуты."
        if errors:
            raise ValidationError(errors)

    def can_edit(self, user):
        return user.is_authenticated and (user.pk == self.author_id or user.is_administrator)

    def conflicts(self):
        if self.status == self.Status.CANCELLED:
            return Event.objects.none()
        return Event.objects.filter(date=self.date, start_time__lt=self.end_time, end_time__gt=self.start_time, rooms__in=self.rooms.all()).exclude(pk=self.pk).exclude(status=self.Status.CANCELLED).distinct()

    def visible_to(self, user, has_conflict=False):
        visible = not self.hide_details or self.can_edit(user)
        return {
            "pk": self.pk, "title": self.title if visible else "Занято",
            "date": self.date, "start_time": self.start_time, "end_time": self.end_time,
            "rooms": self.rooms.all(), "responsible": self.responsible,
            "people_count": self.people_count if visible else None,
            "author": self.author if visible else None,
            "status": self.status, "status_label": self.get_status_display(),
            "details_visible": visible, "hide_details": self.hide_details,
            "has_conflict": has_conflict,
        }
