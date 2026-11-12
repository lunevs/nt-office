from django import forms

class MessageForm(forms.Form):
    text = forms.CharField(label="Сообщение", max_length=5000, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Напишите сообщение…", "maxlength": 5000, "aria-label": "Текст сообщения"}))
