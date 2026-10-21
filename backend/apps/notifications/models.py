from django.conf import settings
from django.db import models


class NotificationPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences")
    email_phase_started = models.BooleanField(default=True)
    email_deadline_reminder = models.BooleanField(default=True)
    email_chat_message = models.BooleanField(default=True)
    email_draw_events = models.BooleanField(default=True)
    email_game_finished = models.BooleanField(default=True)


class EmailNotification(models.Model):
    """Generalized PhaseNotification; one durable delivery attempt per event/user."""
    EVENT_TYPES = [(name, name) for name in (
        "phase_started", "deadline_reminder", "chat_message", "draw_created",
        "draw_rejected", "draw_cancelled", "game_finished",
    )]
    phase = models.ForeignKey("games.GamePhase", null=True, blank=True, on_delete=models.SET_NULL, related_name="email_notifications")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_notifications")
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    event_key = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, default="pending", choices=[
        ("pending", "Pending"), ("sending", "Sending"), ("sent", "Sent"), ("failed", "Failed")])
    error = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["recipient", "event_type", "event_key"], name="unique_email_event_recipient")]
