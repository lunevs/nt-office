from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models

class Message(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_messages")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_messages")
    text = models.TextField(validators=[MaxLengthValidator(5000)])
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["pk"]
        indexes = [models.Index(fields=["recipient", "read_at"]), models.Index(fields=["sender", "recipient", "id"])]
        constraints = [models.CheckConstraint(condition=~models.Q(sender=models.F("recipient")), name="message_distinct_participants")]
