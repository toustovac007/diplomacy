from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.games.models import PhaseReadiness
from apps.orders.models import Order
from apps.orders.services.adjustments import get_adjustment_delta, get_remaining_adjustments


def required_player_ids(phase):
    if phase.phase_type == "movement":
        return set(phase.game.units.filter(is_dislodged=False).values_list("owner_id", flat=True))
    if phase.phase_type == "adjustment":
        return {p.pk for p in phase.game.players.all() if get_adjustment_delta(p) != 0}
    return set()


def readiness_status(game, phase, player):
    supported = bool(phase and game.status == "active" and phase.status == "open"
                     and phase.phase_type in ("movement", "adjustment"))
    required = required_player_ids(phase) if supported else set()
    ready = set(PhaseReadiness.objects.filter(phase=phase, player_id__in=required,
                                             is_ready=True).values_list("player_id", flat=True))
    data = {
        "game_status": game.status,
        "phase": {"id": phase.pk, "sequence": phase.sequence, "phase_type": phase.phase_type} if phase else None,
        "readiness_supported": supported, "is_required": player.pk in required,
        "is_ready": player.pk in ready, "ready_count": len(ready), "required_count": len(required),
        "missing_order_count": 0, "builds_remaining": 0, "disbands_remaining": 0,
        "phase_resolved": False, "next_phase_id": None,
    }
    if supported and phase.phase_type == "movement":
        ordered = Order.objects.filter(phase=phase).values_list("unit_id", flat=True)
        data["missing_order_count"] = player.units.filter(is_dislodged=False).exclude(pk__in=ordered).count()
    elif supported and phase.phase_type == "adjustment":
        data.update(get_remaining_adjustments(phase, player))
    return data


def ensure_player_orders_editable(phase, player):
    """Caller holds game/phase locks through validation AND the order write."""
    if phase.game.status != "active" or phase.status != "open":
        raise ValidationError({"detail": "Tato fáze již není otevřená."})
    if phase.phase_type != "retreat" and PhaseReadiness.objects.filter(
        phase=phase, player=player, is_ready=True,
    ).exists():
        raise ValidationError({"detail": "Nejdřív zruš připravenost, potom můžeš rozkazy změnit."})


def set_ready(game, phase, player, ready):
    """Caller holds the game/phase locks for the complete transaction."""
    data = readiness_status(game, phase, player)
    if not data["readiness_supported"] or not data["is_required"]:
        raise ValidationError({"detail": "V této fázi nemůžeš označit rozkazy jako hotové."})
    if phase.deadline <= timezone.now():
        raise ValidationError({"detail": "Lhůta pro tuto fázi již uplynula."})
    if ready and data["disbands_remaining"]:
        raise ValidationError({"detail": "Nejdřív zadej všechny povinné DISBAND rozkazy."})
    PhaseReadiness.objects.update_or_create(phase=phase, player=player, defaults={
        "is_ready": ready, "ready_at": timezone.now() if ready else None,
    })
    data = readiness_status(game, phase, player)
    if ready and data["required_count"] > 0 and data["ready_count"] == data["required_count"]:
        # Import lazily: these remain the same adjudicators used by deadlines.
        from apps.orders.services.adjudication import resolve_movement_phase
        from apps.orders.services.adjustments import resolve_adjustment_phase
        resolver = resolve_movement_phase if phase.phase_type == "movement" else resolve_adjustment_phase
        resolver(phase)
        game.refresh_from_db()
        next_phase = game.phases.filter(status="open").first()
        data.update(phase_resolved=True, resolved_phase_id=phase.pk,
                    next_phase_id=next_phase.pk if next_phase else None, game_status=game.status)
    return data
