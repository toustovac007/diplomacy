"""Authoritative solo detection and game completion for solo/shared results."""
from django.utils import timezone
from django.db import transaction
from apps.notifications.services import send_game_finished_notifications

from .supply_centers import get_supply_center_count

SOLO_VICTORY_SUPPLY_CENTERS = 18


def find_solo_winner(game):
    for player in game.players.order_by("pk"):
        if get_supply_center_count(player) >= SOLO_VICTORY_SUPPLY_CENTERS:
            return player
    return None


def finish_game(game, winner=None, *, draw_participants=None):
    """Caller holds the game lock inside an atomic transaction."""
    if game.status != "active":
        raise ValueError("Only an active game can finish.")
    participants = list(draw_participants or [])
    if winner is None and (len(participants) < 2 or any(p.game_id != game.pk for p in participants)):
        raise ValueError("A draw requires at least two players of this game.")
    game.status = "finished"
    game.result_type = "solo" if winner is not None else "draw"
    game.winner = winner
    game.finished_at = timezone.now()
    game.save(update_fields=["status", "result_type", "winner", "finished_at"])
    game.draw_participants.set([] if winner is not None else participants)
    if winner is None:
        # No adjudication and no snapshot: history continues to select only
        # genuinely resolved phases, never these interrupted private orders.
        game.phases.filter(status="open").update(status="cancelled", resolved_at=game.finished_at)
    game.draw_proposals.filter(status="open").update(status="cancelled", resolved_at=game.finished_at)
    transaction.on_commit(lambda game_id=game.pk: send_game_finished_notifications(game_id))
