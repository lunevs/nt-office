from django import forms
from django.contrib.auth import get_user_model
from .models import Event

class PersonChoiceField(forms.ModelChoiceField):
    current_user_pk = None

    def label_from_instance(self, user):
        name = f"{user.last_name} {user.first_name}".strip() or user.username
        return f"{name} (вы)" if user.pk == self.current_user_pk else name

class EventForm(forms.ModelForm):
    responsible = PersonChoiceField(label="Ответственный", queryset=get_user_model().objects.none(), empty_label=None)

    class Meta:
        model = Event
        fields = ["title", "date", "start_time", "end_time", "rooms", "people_count", "responsible", "hide_details", "key_needed"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Например, встреча домашней группы"}),
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "start_time": forms.TimeInput(format="%H:%M", attrs={"type": "time", "min": "06:00", "max": "22:59", "step": "60"}),
            "end_time": forms.TimeInput(format="%H:%M", attrs={"type": "time", "min": "06:01", "max": "23:00", "step": "60"}),
            "rooms": forms.CheckboxSelectMultiple(),
            "people_count": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.needs_verification = False
        if not self.instance.pk:
            self.fields["repeat_weekly"] = forms.BooleanField(label="Повторять раз в неделю", required=False)
            self.fields["repeat_until"] = forms.DateField(label="Повторять до", required=False, widget=forms.DateInput(attrs={"type": "date"}), help_text="Включительно. Заполните для еженедельной серии.")
        elif self.instance.series_id:
            self.fields["scope"] = forms.ChoiceField(label="Применить изменения", choices=[("one", "Только эта встреча"), ("future", "Эта и все следующие")], initial="one", widget=forms.RadioSelect)
        self.fields["responsible"].queryset = get_user_model().objects.filter(is_active=True).order_by("last_name", "first_name", "username")
        self.fields["people_count"].min_value = 1
        self.fields["responsible"].current_user_pk = user.pk if user else None


    def clean(self):
        data = super().clean()
        if data.get("repeat_weekly"):
            start, end = data.get("date"), data.get("repeat_until")
            if not end:
                self.add_error("repeat_until", "Укажите дату окончания серии.")
            elif start and end < start:
                self.add_error("repeat_until", "Окончание серии не может быть раньше первой встречи.")
            elif start and (end - start).days // 7 >= 520:
                self.add_error("repeat_until", "В одной серии может быть не более 520 встреч.")
        self._check_verification_limits(data)
        return data

    def _limit(self, field, message):
        self.needs_verification = True
        self.add_error(field, forms.ValidationError(message, code="needs_verification"))

    def _check_verification_limits(self, data):
        """Неподтверждённый аккаунт (макет 34): одна своя встреча в день, до 2 часов, без повтора."""
        from accounts.access import MAX_MINUTES
        user = self.user
        if user is None or user.is_verified or (self.instance.pk and self.instance.author_id != user.pk):
            return
        start, end = data.get("start_time"), data.get("end_time")
        if start and end and (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute) > MAX_MINUTES:
            self._limit("end_time", "Дольше 2 часов — после подтверждения аккаунта")
        if data.get("repeat_weekly"):
            self._limit("repeat_weekly", "Повтор каждую неделю — после подтверждения аккаунта")
        day = data.get("date")
        if day and Event.objects.filter(author=user, date=day).exclude(status=Event.Status.CANCELLED).exclude(pk=self.instance.pk).exists():
            self._limit("date", "Вторая встреча в этот день — после подтверждения аккаунта")
