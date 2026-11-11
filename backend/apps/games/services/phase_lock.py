"""Shared lock order: game, then phase, then orders/units. Call inside atomic()."""
from functools import wraps
from django.db import connection, OperationalError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException

from apps.games.models import Game, GamePhase


def lock_game(game_id):
    # SQLite has no SELECT FOR UPDATE. Obtain its write lock before any reads
    # in this transaction; a contending writer must wait or fail, never bypass.
    if connection.vendor == "sqlite":
        Game.objects.filter(pk=game_id).update(status=F("status"))
    return get_object_or_404(Game.objects.select_for_update(), pk=game_id)


def lock_phase(phase):
    game = lock_game(phase.game_id)
    locked = GamePhase.objects.select_for_update().get(pk=phase.pk)
    locked.game = game
    return locked


class PhaseBusy(APIException):
    status_code = 503
    default_detail = "Hra se právě aktualizuje. Zkus to prosím znovu."


def phase_transaction(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            with transaction.atomic():
                return function(*args, **kwargs)
        except OperationalError as error:
            if connection.vendor == "sqlite" and "locked" in str(error).lower():
                raise PhaseBusy() from error
            raise
    return wrapped
