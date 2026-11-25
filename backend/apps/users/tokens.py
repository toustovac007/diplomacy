"""Integer token balances. All writers lock the owning User row first.

Frozen balances are derived from locked reservations, never a second mutable
counter. Game operations lock the game, then users in ascending primary-key order.
The initial grant is the User field default, applied once by the schema migration.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.games.models import GameStake
from .models import TokenEntry

TOKEN_MINIMUM = 300
REFILL_COOLDOWN = timedelta(days=2)


class InsufficientTokens(APIException):
    status_code = 409
    default_code = "insufficient_tokens"
    default_detail = "Na tuto sázku nemáš dostatek dostupných tokenů."


def account_balances():
    return get_user_model().objects.annotate(tokens_frozen=Coalesce(
        Sum("game_memberships__token_reservation__amount",
            filter=Q(game_memberships__token_reservation__status="locked")),
        Value(0), output_field=models.BigIntegerField(),
    )).annotate(tokens_total=F("tokens_available") + F("tokens_frozen"))


def wallet_snapshot(user_id):
    user = account_balances().get(pk=user_id)
    return {"available": user.tokens_available, "frozen": user.tokens_frozen,
            "total": user.tokens_total, "minimum": TOKEN_MINIMUM,
            "refill_due_at": user.token_refill_due_at,
            "last_refill_at": user.last_token_refill_at}


def lock_users(user_ids):
    return {user.pk: user for user in get_user_model().objects.select_for_update()
            .filter(pk__in=user_ids).order_by("pk")}


def frozen_tokens(user_id):
    return GameStake.objects.filter(player__user_id=user_id, status="locked").aggregate(
        total=Coalesce(Sum("amount"), 0))['total']


def reserve_stake(game, player, *, locked_user=None):
    """Caller holds the game lock (or just created it) inside atomic()."""
    user = locked_user or lock_users([player.user_id])[player.user_id]
    if user.tokens_available < game.token_stake:
        raise InsufficientTokens()
    # One-to-one prevents a second debit for the same membership.
    GameStake.objects.create(player=player, amount=game.token_stake)
    user.tokens_available -= game.token_stake
    user.save(update_fields=["tokens_available"])
    game.token_pot += game.token_stake
    game.save(update_fields=["token_pot"])
    TokenEntry.objects.create(user=user, game=game, kind="stake",
                              available_delta=-game.token_stake, frozen_delta=game.token_stake)


def refill_or_schedule(user, now):
    """User is locked; called after settlement or for a previously queued refill."""
    missing = TOKEN_MINIMUM - user.tokens_available - frozen_tokens(user.pk)
    due = user.last_token_refill_at + REFILL_COOLDOWN if user.last_token_refill_at else now
    if missing <= 0:
        user.token_refill_due_at = None
    elif due > now:
        user.token_refill_due_at = due
    else:
        user.tokens_available += missing
        user.last_token_refill_at = now
        user.token_refill_due_at = None
        TokenEntry.objects.create(user=user, kind="refill", available_delta=missing)
    user.save(update_fields=["tokens_available", "last_token_refill_at", "token_refill_due_at"])


def process_token_refills(*, now=None):
    now = now or timezone.now()
    candidates = get_user_model().objects.filter(token_refill_due_at__lte=now).values_list("pk", flat=True)
    count = 0
    for user_id in candidates.iterator():
        with transaction.atomic():
            user = lock_users([user_id])[user_id]
            if user.token_refill_due_at is None or user.token_refill_due_at > now:
                continue
            before = user.tokens_available
            refill_or_schedule(user, now)
            count += user.tokens_available > before
    return count
