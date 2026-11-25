"""Creator quotas are reserved in the same transaction as game + membership."""
from datetime import timedelta
from math import ceil

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, OperationalError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import APIException, Throttled

from apps.games.models import Game, GamePlayer
from apps.users.tokens import reserve_stake


class CreatorGameLimit(APIException):
    status_code = 409
    default_code = "creator_game_limit"


class GameCreationBusy(APIException):
    status_code = 503
    default_detail = "Zakládání hry právě probíhá. Zkuste to prosím znovu."
    default_code = "game_creation_busy"
    wait = 1


def create_game(creator, validated_data):
    try:
        with transaction.atomic():
            users = get_user_model().objects
            if connection.vendor == "sqlite":
                # Acquire SQLite's write lock before reading the quota.
                users.filter(pk=creator.pk).update(last_game_created_at=F("last_game_created_at"))
            user = users.select_for_update().get(pk=creator.pk)
            owned = Game.objects.filter(creator=user)
            if owned.filter(status__in=["waiting", "active"]).count() >= settings.GAME_MAX_OPEN_CREATED:
                raise CreatorGameLimit(
                    f"Můžete mít nejvýše {settings.GAME_MAX_OPEN_CREATED} vlastních čekajících nebo probíhajících her. "
                    "Před založením další hry nejdříve dokončete některou ze stávajících."
                )
            now = timezone.now()
            last = user.last_game_created_at
            # Also respect recent games created before this field existed.
            latest = owned.order_by("-created_at").values_list("created_at", flat=True).first()
            if latest is not None and (last is None or latest > last):
                last = latest
            if last is not None:
                remaining = (last + timedelta(seconds=settings.GAME_CREATE_COOLDOWN_SECONDS) - now).total_seconds()
                if remaining > 0:
                    raise Throttled(wait=ceil(remaining), detail="Další hru zatím nelze vytvořit.", code="game_create_cooldown")
            game = Game.objects.create(creator=user, **validated_data)
            player = GamePlayer.objects.create(game=game, user=user)
            reserve_stake(game, player, locked_user=user)
            # Durable even after a game is finished/deleted; failed inserts roll back.
            user.last_game_created_at = game.created_at
            user.save(update_fields=["last_game_created_at"])
            return game
    except OperationalError as error:
        if connection.vendor == "sqlite" and "locked" in str(error).lower():
            raise GameCreationBusy() from error
        raise
