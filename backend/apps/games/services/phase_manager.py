from datetime import timedelta

from django.utils import timezone

from apps.games.models import Game, GamePhase
from apps.games.services.victory import find_solo_winner, finish_game

from apps.games.services.supply_centers import (
    update_supply_center_ownership,
    get_adjustment_delta,
)

from django.db import transaction

from apps.notifications.services import (
    send_phase_started_notifications,
)


def create_phase(
    game,
    sequence,
    year,
    season,
    phase_type,
):
    return GamePhase.objects.create(
        game=game,
        sequence=sequence,
        year=year,
        season=season,
        phase_type=phase_type,
        status="open",
        deadline=(
            timezone.now()
            + timedelta(
                minutes=game.turn_duration_minutes
            )
        ),
    )
    transaction.on_commit(
        lambda: send_phase_started_notifications(
            phase
        )
    )


def create_next_after_movement(
    movement_phase,
    has_dislodged_units,
):
    game = movement_phase.game
    next_sequence = movement_phase.sequence + 1

    if has_dislodged_units:
        return create_phase(
            game=game,
            sequence=next_sequence,
            year=movement_phase.year,
            season=movement_phase.season,
            phase_type="retreat",
        )

    return create_next_after_retreat(
        movement_phase
    )


@transaction.atomic
def create_next_after_retreat(phase):
    game = Game.objects.select_for_update().get(pk=phase.game_id)
    if game.status == "finished":
        return None
    next_sequence = phase.sequence + 1

    if phase.season == "spring":
        return create_phase(
            game=game,
            sequence=next_sequence,
            year=phase.year,
            season="fall",
            phase_type="movement",
        )

    if phase.season == "fall":
        update_supply_center_ownership(
            game
        )

        winner = find_solo_winner(game)
        if winner is not None:
            finish_game(game, winner)
            return None

        if all(get_adjustment_delta(player) == 0 for player in game.players.all()):
            return create_phase(
                game=game,
                sequence=next_sequence,
                year=phase.year + 1,
                season="spring",
                phase_type="movement",
            )

        return create_phase(
            game=game,
            sequence=next_sequence,
            year=phase.year,
            season="winter",
            phase_type="adjustment",
        )

    raise ValueError(
        f"Neplatná sezóna pro přechod fáze: {phase.season}"
    )
def create_next_after_adjustment(phase):
    if phase.phase_type != "adjustment":
        raise ValueError(
            "Fáze není Adjustment."
        )

    if phase.season != "winter":
        raise ValueError(
            "Adjustment musí být Winter fáze."
        )

    return create_phase(
        game=phase.game,
        sequence=phase.sequence + 1,
        year=phase.year + 1,
        season="spring",
        phase_type="movement",
    )
