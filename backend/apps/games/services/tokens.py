"""Game escrow, elimination, and idempotent integer-only pot settlement."""
from django.db import transaction
from django.db.models import Count, Exists, OuterRef
from django.utils import timezone

from apps.games.models import GameStake, SupplyCenterOwnership, Unit
from apps.users.models import TokenEntry
from apps.users.tokens import lock_users, refill_or_schedule
from .phase_lock import lock_game


def refund_stake(game, stake, user):
    """Caller holds the game and user locks. A refund is irreversible/idempotent."""
    if stake.status == "refunded":
        return
    if stake.status != "locked":
        raise ValueError("Only a frozen stake can be refunded.")
    user.tokens_available += stake.amount
    user.save(update_fields=["tokens_available"])
    stake.status, stake.payout = "refunded", stake.amount
    stake.save(update_fields=["status", "payout"])
    TokenEntry.objects.create(user=user, game=game, kind="refund",
        available_delta=stake.amount, frozen_delta=-stake.amount)


@transaction.atomic
def release_eliminated_stakes(game):
    """Called after a stable phase transition, inside the game's transaction.

    Dislodged units still count. Unranked stakes are returned immediately.
    Forfeited stakes stop counting toward personal wealth but stay in the pot.
    """
    game = lock_game(game.pk)
    if game.status != "active":
        return
    stakes = list(GameStake.objects.filter(player__game=game, status="locked").annotate(
        has_centers=Exists(SupplyCenterOwnership.objects.filter(owner_id=OuterRef("player_id"), game=game)),
        has_units=Exists(Unit.objects.filter(owner_id=OuterRef("player_id"), game=game)),
    ).filter(has_centers=False, has_units=False).select_related("player"))
    users = lock_users([stake.player.user_id for stake in stakes])
    for stake in stakes:
        if game.scoring == "unranked":
            refund_stake(game, stake, users[stake.player.user_id])
            continue
        stake.status = "forfeited"
        stake.save(update_fields=["status"])
        TokenEntry.objects.create(user_id=stake.player.user_id, game=game,
                                  kind="forfeit", frozen_delta=-stake.amount)


def allocate_pot(game, stakes):
    """Solo wins all; selected draw winners share; unranked refunds everyone."""
    pot = sum(stake.amount for stake in stakes)
    if pot != game.token_pot:
        raise ValueError("Token pot does not match reservations.")
    if not stakes:
        return {}
    if game.scoring == "unranked":
        return {stake.player_id: stake.amount for stake in stakes if stake.status != "refunded"}
    if game.termination_reason == "inactivity" and not game.draw_participants.exists():
        # No power survives: nobody can receive a ranked victory, so return stakes.
        return {stake.player_id: stake.amount for stake in stakes}
    if game.result_type == "solo":
        if game.winner_id not in {stake.player_id for stake in stakes}:
            raise ValueError("The winner has no stake in this game.")
        return {game.winner_id: pot}
    centers = dict(game.players.annotate(center_count=Count("owned_supply_centers"))
                   .values_list("pk", "center_count"))
    winners = set(game.draw_participants.values_list("pk", flat=True))
    eligible = [stake for stake in stakes if stake.player_id in winners and stake.status != "forfeited"]
    if not eligible:
        raise ValueError("The draw has no eligible stake holders.")
    weights = {stake.player_id: centers[stake.player_id] ** 2 if game.scoring == "sos" else 1
               for stake in eligible}
    total_weight = sum(weights.values())
    # A power can survive on units alone; an all-zero-center draw is equal.
    if total_weight == 0:
        weights = dict.fromkeys(weights, 1)
        total_weight = len(weights)
    payouts = {player_id: pot * weight // total_weight for player_id, weight in weights.items()}
    strongest = min(weights, key=lambda player_id: (-centers[player_id], player_id))
    payouts[strongest] += pot - sum(payouts.values())
    return payouts


@transaction.atomic
def settle_game(game_id):
    game = lock_game(game_id)
    if game.tokens_settled_at is not None:
        return game
    if game.status != "finished" or game.result_type not in ("solo", "draw"):
        raise ValueError("Only a finished game with a result can settle.")
    stakes = list(GameStake.objects.filter(player__game=game).select_related("player").order_by("pk"))
    users = lock_users([stake.player.user_id for stake in stakes])
    payouts = allocate_pot(game, stakes)
    for stake in stakes:
        if stake.status == "refunded":
            continue
        user = users[stake.player.user_id]
        payout = payouts.get(stake.player_id, 0)
        frozen_delta = -stake.amount if stake.status == "locked" else 0
        user.tokens_available += payout
        user.save(update_fields=["tokens_available"])
        TokenEntry.objects.create(user=user, game=game, kind="settlement",
                                  available_delta=payout, frozen_delta=frozen_delta)
        stake.status, stake.payout = "settled", payout
        stake.save(update_fields=["status", "payout"])
    now = timezone.now()
    for user in users.values():
        refill_or_schedule(user, now)
    game.tokens_settled_at = now
    game.save(update_fields=["tokens_settled_at"])
    return game
