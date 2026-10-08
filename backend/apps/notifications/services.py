from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.games.models import GamePhase
from .models import PhaseNotification


def get_phase_name(phase):
    season_names = {
        "spring": "Jaro",
        "fall": "Podzim",
        "winter": "Zima",
    }

    phase_names = {
        "movement": "Pohyby",
        "retreat": "Ústupy",
        "adjustment": "Úpravy jednotek",
    }

    season = season_names.get(
        phase.season,
        phase.season,
    )

    phase_type = phase_names.get(
        phase.phase_type,
        phase.phase_type,
    )

    return (
        f"{season} {phase.year} - "
        f"{phase_type}"
    )


def send_notification_once(
    phase,
    user,
    notification_type,
    subject,
    message,
):
    if not user.email:
        return False

    notification, created = (
        PhaseNotification.objects.get_or_create(
            phase=phase,
            user=user,
            notification_type=notification_type,
        )
    )

    if not created:
        return False

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[
                user.email,
            ],
            fail_silently=False,
        )

    except Exception:
        # Pokud odeslání selže, záznam smažeme,
        # aby mohl scheduler pokus zopakovat.
        notification.delete()
        raise

    return True


def send_phase_started_notifications(
    phase,
):
    phase_name = get_phase_name(
        phase
    )

    players = (
        phase.game.players
        .select_related("user")
        .all()
    )

    sent = 0

    for player in players:
        if send_notification_once(
            phase=phase,
            user=player.user,
            notification_type="phase_started",
            subject=(
                f"{phase.game.name}: "
                f"nová fáze {phase_name}"
            ),
            message=(
                f"Ve hře {phase.game.name} "
                f"začala nová fáze:\n\n"
                f"{phase_name}\n\n"
                f"Deadline: "
                f"{phase.deadline.strftime('%d.%m.%Y %H:%M')}"
            ),
        ):
            sent += 1

    return sent



def process_deadline_reminders(
    now=None,
):
    if now is None:
        now = timezone.now()

    reminder_until = (
        now + timedelta(hours=1)
    )

    phases = (
        GamePhase.objects
        .filter(
            status="open",
            deadline__gt=now,
            deadline__lte=reminder_until,
        )
        .select_related("game")
    )

    sent = 0

    for phase in phases:
        phase_name = get_phase_name(
            phase
        )

        players = (
            phase.game.players
            .select_related("user")
            .all()
        )

        for player in players:
            if send_notification_once(
                phase=phase,
                user=player.user,
                notification_type="deadline_reminder",
                subject=(
                    f"{phase.game.name}: "
                    "blíží se deadline"
                ),
                message=(
                    f"Ve hře {phase.game.name} "
                    f"se blíží deadline fáze:\n\n"
                    f"{phase_name}\n\n"
                    f"Deadline: "
                    f"{phase.deadline.strftime('%d.%m.%Y %H:%M')}"
                ),
            ):
                sent += 1

    return sent



