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
        self.fields["responsible"].queryset = get_user_model().objects.filter(is_active=True).order_by("last_name", "first_name", "username")
        self.fields["people_count"].min_value = 1
