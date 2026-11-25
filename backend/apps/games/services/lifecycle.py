"""Waiting-game expiry/refunds and consecutive resolved-phase inactivity."""
from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from apps.games.models import Game, GamePhase, GamePlayer, GameStake
from apps.users.tokens import lock_users
from .phase_lock import lock_game
from .tokens import refund_stake

LOBBY_IDLE_LIMIT = timedelta(days=2)
INACTIVE_PHASE_LIMIT = 10


class GameAlreadyStarted(APIException):
    status_code = 409
    default_detail = "Smazat lze pouze hru, která ještě nebyla spuštěna."


def lobby_expires_at(game):
    last_join = max((player.joined_at for player in game.players.all()), default=game.created_at)
    return max(game.created_at, last_join) + LOBBY_IDLE_LIMIT


@transaction.atomic
def cancel_waiting_game(game_id, *, actor=None, expired_before=None):
    game = lock_game(game_id)
    if actor is not None and game.creator_id != actor.pk:
        raise PermissionDenied("Hru může smazat pouze její zakladatel.")
    if game.status != "waiting":
        if expired_before is not None:
            return False
        raise GameAlreadyStarted()
    # Recheck under the same lock used by joins and start; a new member rescues it.
    if expired_before is not None and lobby_expires_at(game) > expired_before:
        return False
    stakes = list(GameStake.objects.filter(player__game=game).select_related("player"))
    if sum(stake.amount for stake in stakes) != game.token_pot or any(stake.status != "locked" for stake in stakes):
        raise ValueError("Waiting-game escrow is inconsistent; preserve it for inspection.")
    users = lock_users([stake.player.user_id for stake in stakes])
    for stake in stakes:
        refund_stake(game, stake, users[stake.player.user_id])
    game.delete()
    return True


def cleanup_waiting_games(*, now=None):
    now = now or timezone.now()
    cutoff = now - LOBBY_IDLE_LIMIT
    candidates = Game.objects.filter(status="waiting", created_at__lte=cutoff).annotate(
        recent_join=Exists(GamePlayer.objects.filter(game_id=OuterRef("pk"), joined_at__gt=cutoff))
    ).filter(recent_join=False).values_list("pk", flat=True)
    count = 0
    for game_id in candidates.iterator():
        try:
            count += cancel_waiting_game(game_id, expired_before=now)
        except Http404:
            # Another cleanup worker/creator already removed it.
            continue
    return count


def finish_if_inactive(game, phase):
    """Caller holds game/phase locks, after adjudication and SC updates.

    Only successful resolutions count. The persisted marker survives deletion of
    submitted orders/units. Default orders, chat and readiness are not activity.
    """
    if phase.status != "resolved":
        return False
    state = GamePhase.objects.values("has_submitted_orders", "inactivity_checked").get(pk=phase.pk)
    if not state["inactivity_checked"]:
        submitted = (state["has_submitted_orders"] or phase.orders.filter(is_default=False).exists()
                     or phase.adjustment_orders.filter(is_default=False).exists())
        game.inactive_phase_count = 0 if submitted else game.inactive_phase_count + 1
        game.save(update_fields=["inactive_phase_count"])
        GamePhase.objects.filter(pk=phase.pk).update(inactivity_checked=True)
    if game.status != "active" or game.inactive_phase_count < INACTIVE_PHASE_LIMIT:
        return False
    from .draws import surviving_players
    from .victory import finish_game
    finish_game(game, draw_participants=list(surviving_players(game)), termination_reason="inactivity")
    return True
