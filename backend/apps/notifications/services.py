import logging
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailNotification, NotificationPreference

logger = logging.getLogger(__name__)
PREFERENCES = {
    "phase_started": "email_phase_started", "deadline_reminder": "email_deadline_reminder",
    "chat_message": "email_chat_message", "draw_created": "email_draw_events",
    "draw_rejected": "email_draw_events", "draw_cancelled": "email_draw_events",
    "game_finished": "email_game_finished",
}


def safe_notification(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as error:
            # No exception messages/tracebacks: SMTP errors can contain secrets.
            logger.error("Notification %s failed (%s)", function.__name__, type(error).__name__)
            return 0
    return wrapped


def local_time(value):
    return timezone.localtime(value).strftime("%d. %m. %Y %H:%M %Z")


def get_phase_name(phase):
    return f"{phase.get_season_display()} {phase.year} — {phase.get_phase_type_display()}"


@safe_notification
def send_notification_once(user, event_type, event_key, game, subject, lines, *, phase_id=None):
    address = (user.email or "").strip()
    try:
        validate_email(address)
    except ValidationError:
        return False
    preference, _ = NotificationPreference.objects.get_or_create(user=user)
    if not getattr(preference, PREFERENCES[event_type]):
        return False
    notification, _ = EmailNotification.objects.get_or_create(
        recipient=user, event_type=event_type, event_key=event_key, defaults={"phase_id": phase_id})
    # Atomic compare-and-set prevents simultaneous callbacks from duplicating mail.
    if not EmailNotification.objects.filter(pk=notification.pk, status="pending").update(status="sending"):
        return False
    try:
        base = settings.FRONTEND_BASE_URL.rstrip("/")
        context = {"heading": subject, "game_name": game.name, "lines": lines,
                   "game_url": f"{base}/games/{game.pk}" if base else ""}
        email = EmailMultiAlternatives(
            subject=" ".join(f"[Diplomacy] {subject}".splitlines()),
            body=render_to_string("notifications/email/event.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL, to=[address],
        )
        email.attach_alternative(render_to_string("notifications/email/event.html", context), "text/html")
        if email.send(fail_silently=False) != 1:
            raise RuntimeError("Email backend did not accept delivery")
        EmailNotification.objects.filter(pk=notification.pk).update(status="sent", sent_at=timezone.now())
        return True
    except Exception as error:
        EmailNotification.objects.filter(pk=notification.pk).update(status="failed", error=type(error).__name__)
        logger.error("Email delivery %s failed (%s)", notification.pk, type(error).__name__)
        # No automatic retry: SMTP may have accepted mail before the error.
        return False


@safe_notification
def send_phase_started_notifications(phase_id):
    from apps.games.models import GamePhase
    phase = GamePhase.objects.select_related("game").filter(pk=phase_id, status="open", game__status="active").first()
    if not phase:
        return 0
    return sum(send_notification_once(player.user, "phase_started", f"phase:{phase.pk}:started", phase.game,
        f"Nová fáze — {phase.get_season_display()} {phase.year}",
        [f"Stát: {player.get_country_display()}", f"Nová fáze: {get_phase_name(phase)}", f"Deadline: {local_time(phase.deadline)}"],
        phase_id=phase.pk) for player in phase.game.players.select_related("user"))


def deadline_reminder_minutes(game, phase_type):
    from apps.games.services.phase_manager import get_phase_duration_minutes
    return 15 if get_phase_duration_minutes(game, phase_type) <= 60 else 60


@safe_notification
def process_deadline_reminders(now=None):
    from apps.games.models import GamePhase
    now = now or timezone.now()
    phases = GamePhase.objects.filter(game__status="active", status="open", deadline__gt=now,
                                     deadline__lte=now + timedelta(minutes=60)).select_related("game")
    sent = 0
    for phase in phases:
        if phase.deadline > now + timedelta(minutes=deadline_reminder_minutes(phase.game, phase.phase_type)):
            continue
        for player in phase.game.players.select_related("user"):
            # Recheck after prior deliveries in case the phase ended meanwhile.
            if not GamePhase.objects.filter(pk=phase.pk, status="open", game__status="active", deadline__gt=max(now, timezone.now())).exists():
                break
            sent += bool(send_notification_once(player.user, "deadline_reminder", f"phase:{phase.pk}:deadline", phase.game,
                "Blíží se deadline", [f"Stát: {player.get_country_display()}", f"Fáze: {get_phase_name(phase)}",
                f"Deadline: {local_time(phase.deadline)}"], phase_id=phase.pk))
    return sent


@safe_notification
def send_chat_message_notifications(message_id):
    from apps.chats.models import ChatMessage
    message = ChatMessage.objects.select_related("conversation__game").filter(pk=message_id).first()
    if not message:
        return 0
    conversation = message.conversation
    title = conversation.title or ", ".join(p.get_country_display() or p.user.username for p in conversation.participants.select_related("user"))
    memberships = conversation.memberships.exclude(player_id=message.sender_id).select_related("player__user")
    return sum(send_notification_once(m.player.user, "chat_message", f"chat-message:{message.pk}", conversation.game,
        f"Nová zpráva — {message.sender_country_name}",
        [f"Konverzace: {title}", f"Od: {message.sender_country_name} — {message.sender_username}",
         f"Čas: {local_time(message.created_at)}", message.text]) for m in memberships)


@safe_notification
def send_draw_notifications(proposal_id, event_type):
    from apps.games.models import DrawProposal
    proposal = DrawProposal.objects.select_related("game", "proposer__user").filter(pk=proposal_id).first()
    if not proposal:
        return 0
    subjects = {"draw_created": "Nový návrh sdíleného vítězství", "draw_rejected": "Návrh dohody byl zamítnut",
                "draw_cancelled": "Návrh dohody byl zrušen"}
    expected = {"draw_created": "open", "draw_rejected": "rejected", "draw_cancelled": "cancelled"}
    if proposal.status != expected[event_type]:
        return 0
    voters = proposal.voters.select_related("user")
    if event_type == "draw_created":
        voters = voters.exclude(pk=proposal.proposer_id)
    winners = ", ".join(f"{p.get_country_display()} — {p.user.username}" for p in proposal.participants.select_related("user"))
    lines = [f"Navrhl: {proposal.proposer.get_country_display()} — {proposal.proposer.user.username}", f"Navržení vítězové: {winners}"]
    lines.append("Je nutný jednomyslný souhlas všech hlasujících přeživších hráčů." if event_type == "draw_created" else "Hra pokračuje.")
    return sum(send_notification_once(p.user, event_type, f"draw:{proposal.pk}:{event_type}", proposal.game,
                                      subjects[event_type], lines) for p in voters)


@safe_notification
def send_game_finished_notifications(game_id):
    from apps.games.models import Game
    from apps.games.services.supply_centers import get_supply_center_count
    game = Game.objects.select_related("winner__user").filter(pk=game_id, status="finished").first()
    if not game:
        return 0
    if game.result_type == "draw":
        subject = "Hra skončila dohodou"
        winners = ", ".join(f"{p.get_country_display()} — {p.user.username}" for p in game.draw_participants.select_related("user"))
        lines = [f"Sdílené vítězství: {winners}"]
    elif game.winner:
        subject = f"Hra skončila — vítěz {game.winner.get_country_display()}"
        lines = [f"Vítěz: {game.winner.get_country_display()} — {game.winner.user.username}", f"Supply centra: {get_supply_center_count(game.winner)}"]
    else:
        subject, lines = "Hra skončila", []
    if game.finished_at:
        lines.append(f"Ukončeno: {local_time(game.finished_at)}")
    return sum(send_notification_once(p.user, "game_finished", f"game:{game.pk}:finished", game, subject, lines)
               for p in game.players.select_related("user"))
