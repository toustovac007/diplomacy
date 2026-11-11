from functools import wraps

from django.db import connection, IntegrityError, OperationalError, transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.games.models import Game, GamePlayer, Unit, SupplyCenterOwnership, DrawProposal, DrawVote
from .victory import finish_game
from .phase_lock import lock_game
from apps.notifications.services import send_draw_notifications


def surviving_players(game):
    """Owns at least one SC OR has any unit, including a dislodged unit."""
    return game.players.annotate(
        has_centers=Exists(SupplyCenterOwnership.objects.filter(game=game, owner_id=OuterRef("pk"))),
        has_units=Exists(Unit.objects.filter(game=game, owner_id=OuterRef("pk"))),
    ).filter(Q(has_centers=True) | Q(has_units=True)).select_related("user").order_by("pk")


class DrawBusy(APIException):
    status_code = 503
    default_detail = "Hra se právě aktualizuje. Zkus to prosím znovu."


def draw_transaction(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            with transaction.atomic():
                return function(*args, **kwargs)
        except IntegrityError as error:
            if not any(key in str(error) for key in ("one_open_draw_per_game", "games_drawproposal.game_id")):
                raise
            raise ValidationError({"detail": "Pro tuto hru již existuje otevřený návrh."}) from error
        except OperationalError as error:
            if connection.vendor == "sqlite" and "locked" in str(error).lower():
                raise DrawBusy() from error
            raise
    return wrapped


def active_game(game_id, user):
    game = lock_game(game_id)
    player = get_object_or_404(GamePlayer, game=game, user=user)
    if game.status != "active":
        raise ValidationError({"detail": "Hra již není aktivní."})
    return game, player


@draw_transaction
def propose(game_id, user, participant_ids):
    game, player = active_game(game_id, user)
    survivors = list(surviving_players(game))
    survivor_ids = {p.pk for p in survivors}
    ids = set(participant_ids)
    if player.pk not in survivor_ids:
        raise PermissionDenied("Vyřazený hráč nemůže navrhovat dohodu.")
    if len(ids) != len(participant_ids) or len(ids) < 2 or player.pk not in ids or not ids <= survivor_ids:
        raise ValidationError({"detail": "Vyber alespoň dva přeživší hráče této hry včetně sebe, bez duplicit."})
    if game.draw_proposals.filter(status="open").exists():
        raise ValidationError({"detail": "Pro tuto hru již existuje otevřený návrh."})
    proposal = DrawProposal.objects.create(game=game, proposer=player)
    proposal.participants.set(ids)
    now = timezone.now()
    DrawVote.objects.bulk_create([DrawVote(proposal=proposal, player=p,
        vote="accept" if p.pk == player.pk else None, voted_at=now if p.pk == player.pk else None) for p in survivors])
    transaction.on_commit(lambda proposal_id=proposal.pk: send_draw_notifications(proposal_id, "draw_created"))
    return proposal, game


@draw_transaction
def vote(game_id, proposal_id, user, choice):
    game, player = active_game(game_id, user)
    proposal = get_object_or_404(DrawProposal.objects.select_for_update(), pk=proposal_id, game=game)
    if proposal.status != "open":
        raise ValidationError({"detail": "Tento návrh je již uzavřen."})
    ballot = proposal.votes.filter(player=player).first()
    if ballot is None:
        raise PermissionDenied("Nejsi mezi hlasujícími tohoto návrhu.")
    ballot.vote = choice
    ballot.voted_at = timezone.now()
    ballot.save(update_fields=["vote", "voted_at"])
    if choice == "reject":
        proposal.status = "rejected"
    elif not proposal.votes.filter(Q(vote__isnull=True) | ~Q(vote="accept")).exists():
        proposal.status = "accepted"
    if proposal.status != "open":
        proposal.resolved_at = timezone.now()
        proposal.save(update_fields=["status", "resolved_at"])
        if proposal.status == "accepted":
            finish_game(game, draw_participants=proposal.participants.all())
        else:
            transaction.on_commit(lambda proposal_id=proposal.pk: send_draw_notifications(proposal_id, "draw_rejected"))
    return proposal, game


@draw_transaction
def cancel(game_id, proposal_id, user):
    game, player = active_game(game_id, user)
    proposal = get_object_or_404(DrawProposal.objects.select_for_update(), pk=proposal_id, game=game)
    if proposal.proposer_id != player.pk:
        raise PermissionDenied("Návrh může zrušit pouze navrhovatel.")
    if proposal.status != "open":
        raise ValidationError({"detail": "Tento návrh je již uzavřen."})
    proposal.status = "cancelled"
    proposal.resolved_at = timezone.now()
    proposal.save(update_fields=["status", "resolved_at"])
    transaction.on_commit(lambda proposal_id=proposal.pk: send_draw_notifications(proposal_id, "draw_cancelled"))
    return proposal, game
