from django.test import TestCase

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.games.models import (
    Game,
    GamePlayer,
    GamePhase,
)

from .models import (
    PhaseNotification,
)

from .services import (
    process_deadline_reminders,
    send_phase_started_notifications,
)


User = get_user_model()


class NotificationTestCase(TestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(
            username="notify1",
            email="notify1@test.cz",
            password="test12345",
        )

        self.user2 = User.objects.create_user(
            username="notify2",
            email="notify2@test.cz",
            password="test12345",
        )

        self.game = Game.objects.create(
            name="Notification test",
            creator=self.user1,
            status="active",
            turn_duration_minutes=1440,
            max_players=7,
        )

        GamePlayer.objects.create(
            game=self.game,
            user=self.user1,
            country="FRA",
        )

        GamePlayer.objects.create(
            game=self.game,
            user=self.user2,
            country="GER",
        )

    def create_phase(
        self,
        deadline,
    ):
        return GamePhase.objects.create(
            game=self.game,
            sequence=1,
            year=1901,
            season="spring",
            phase_type="movement",
            status="open",
            deadline=deadline,
        )

    def test_phase_started_email_is_sent_once(self):
        phase = self.create_phase(
            timezone.now()
            + timedelta(hours=24)
        )

        send_phase_started_notifications(
            phase
        )

        send_phase_started_notifications(
            phase
        )

        self.assertEqual(
            len(mail.outbox),
            2,
        )

        self.assertEqual(
            PhaseNotification.objects.filter(
                phase=phase,
                notification_type="phase_started",
            ).count(),
            2,
        )

    def test_deadline_reminder_is_sent_once(self):
        phase = self.create_phase(
            timezone.now()
            + timedelta(minutes=30)
        )

        process_deadline_reminders()

        process_deadline_reminders()

        self.assertEqual(
            len(mail.outbox),
            2,
        )

        self.assertEqual(
            PhaseNotification.objects.filter(
                phase=phase,
                notification_type="deadline_reminder",
            ).count(),
            2,
        )

