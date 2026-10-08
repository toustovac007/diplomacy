from django.db import models

from django.conf import settings
from django.db import models

from apps.games.models import GamePhase


class PhaseNotification(models.Model):
    TYPE_CHOICES = [
        ("phase_started", "Nová fáze"),
        ("deadline_reminder", "Připomenutí deadlinu"),
    ]

    phase = models.ForeignKey(
        GamePhase,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="phase_notifications",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
    )

    sent_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "phase",
                    "user",
                    "notification_type",
                ],
                name="unique_phase_notification",
            )
        ]

    def __str__(self):
        return (
            f"{self.user} - "
            f"{self.phase} - "
            f"{self.notification_type}"
        )