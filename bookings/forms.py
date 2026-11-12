from django import forms
from django.contrib.auth import get_user_model
from .models import Event

class PersonChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return f"{user.last_name} {user.first_name} (@{user.username})".strip()

class EventForm(forms.ModelForm):
    responsible = PersonChoiceField(label="Ответственный", queryset=get_user_model().objects.none(), empty_label=None)

    class Meta:
        model = Event
        fields = ["title", "date", "start_time", "end_time", "rooms", "people_count", "responsible", "hide_details"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Например, встреча домашней группы"}),
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "start_time": forms.TimeInput(format="%H:%M", attrs={"type": "time", "min": "06:00", "max": "22:59", "step": "60"}),
            "end_time": forms.TimeInput(format="%H:%M", attrs={"type": "time", "min": "06:01", "max": "23:00", "step": "60"}),
            "rooms": forms.CheckboxSelectMultiple(),
            "people_count": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["repeat_weekly"] = forms.BooleanField(label="Повторять раз в неделю", required=False)
            self.fields["repeat_until"] = forms.DateField(label="Повторять до", required=False, widget=forms.DateInput(attrs={"type": "date"}), help_text="Включительно. Заполните для еженедельной серии.")
        elif self.instance.series_id:
            self.fields["scope"] = forms.ChoiceField(label="Применить изменения", choices=[("one", "Только эта встреча"), ("future", "Эта и все последующие встречи")], initial="one")
        self.fields["responsible"].queryset = get_user_model().objects.filter(is_active=True).order_by("last_name", "first_name", "username")
        self.fields["people_count"].min_value = 1


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
        return data
