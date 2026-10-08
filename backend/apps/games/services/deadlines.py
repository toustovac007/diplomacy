from django.utils import timezone

from apps.games.models import GamePhase

from apps.orders.services.adjudication import (
    AdjudicationError,
    resolve_movement_phase,
)

from apps.orders.services.retreat import (
    RetreatError,
    resolve_retreat_phase,
)

from apps.orders.services.adjustments import (
    AdjustmentError,
    resolve_adjustment_phase,
)


def process_expired_phases(now=None):
    if now is None:
        now = timezone.now()

    phases = list(
        GamePhase.objects
        .filter(
            status="open",
            deadline__lte=now,
        )
        .select_related("game")
        .order_by("deadline", "id")
    )

    results = []

    for phase in phases:
        try:
            if phase.phase_type == "movement":
                resolve_movement_phase(
                    phase
                )

            elif phase.phase_type == "retreat":
                resolve_retreat_phase(
                    phase
                )


            elif phase.phase_type == "adjustment":

                resolve_adjustment_phase(

                    phase,

                    allow_automatic_disbands=True,

                )

            else:
                results.append(
                    {
                        "phase_id": phase.id,
                        "status": "error",
                        "detail":
                            f"Neznámý typ fáze: "
                            f"{phase.phase_type}",
                    }
                )

                continue

            results.append(
                {
                    "phase_id": phase.id,
                    "game_id": phase.game_id,
                    "phase_type": phase.phase_type,
                    "status": "resolved",
                }
            )

        except (
            AdjudicationError,
            RetreatError,
            AdjustmentError,
        ) as error:
            results.append(
                {
                    "phase_id": phase.id,
                    "game_id": phase.game_id,
                    "phase_type": phase.phase_type,
                    "status": "error",
                    "detail": str(error),
                }
            )

    return results