from functools import wraps
from time import sleep

from django.db import connection, OperationalError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from apps.games.models import Game
from .models import ChatConversation, ChatMembership, ChatMessage
from apps.notifications.services import send_chat_message_notifications


class ChatBusy(APIException):
    status_code = 503
    default_detail = "Chat je právě zaneprázdněný. Zkus to prosím znovu."


def lock_active_game(game_id):
    # Use the same game lock as phase transitions and game completion.
    game = Game.objects.select_for_update().get(pk=game_id)
    if game.status != "active":
        raise ValidationError({"detail": "Diplomacie je dostupná pouze během aktivní hry."})
    return game


def retry_sqlite_write(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        # SQLite has no row locks. Retry the whole rolled-back transaction when
        # simultaneous chat writes contend; other databases use the game lock.
        for attempt in range(5):
            try:
                return function(*args, **kwargs)
            except OperationalError as error:
                if connection.vendor != "sqlite" or "locked" not in str(error).lower():
                    raise
                if attempt == 4:
                    raise ChatBusy() from error
                sleep(0.05 * (attempt + 1))
    return wrapped


@retry_sqlite_write
@transaction.atomic
def create_conversation(player, conversation_type, participant_ids, title=""):
    game = lock_active_game(player.game_id)
    ids = sorted([player.pk, *participant_ids])
    if conversation_type == "direct":
        # get_or_create handles a concurrent insert through the unique DB key.
        conversation, created = ChatConversation.objects.get_or_create(
            game=game, direct_key=":".join(map(str, ids)),
            defaults={"conversation_type": "direct", "created_by": player},
        )
    else:
        conversation = ChatConversation.objects.create(game=game, conversation_type="group", title=title, created_by=player)
        created = True
    if created:
        ChatMembership.objects.bulk_create([ChatMembership(conversation=conversation, player_id=pk) for pk in ids])
    return conversation, created


@retry_sqlite_write
@transaction.atomic
def send_message(conversation, player, text):
    game = lock_active_game(conversation.game_id)
    # A single creation service leaves room for a future on-commit hook.
    message = ChatMessage.objects.create(
        conversation=conversation, sender=player, text=text,
        phase=game.phases.filter(status="open").order_by("-sequence").first(),
        sender_username=player.user.username, sender_country=player.country or "",
        sender_country_name=player.get_country_display() or "",
    )
    ChatConversation.objects.filter(pk=conversation.pk).update(updated_at=message.created_at)
    transaction.on_commit(lambda message_id=message.pk: send_chat_message_notifications(message_id))
    return message


def mark_read(conversation, player):
    ChatMembership.objects.filter(conversation=conversation, player=player).update(last_read_at=timezone.now())
