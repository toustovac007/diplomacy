from apps.games.services.phase_lock import lock_phase
from django.db import transaction
from apps.orders.services.snapshots import order_snapshot, save_snapshot, capture_resolved_phase_state
from django.utils import timezone

from apps.games.models import GamePhase, Unit
from apps.games.services.phase_manager import (
    create_next_after_retreat,
)
from apps.maps.models import Province, Coast
from apps.maps.rules import can_unit_move

from apps.orders.models import Order


class RetreatError(Exception):
    pass


def get_standoff_province_ids(movement_phase):
    return set(
        Order.objects.filter(
            phase=movement_phase,
            order_type="move",
            result_reason="standoff",
        ).values_list(
            "target_province_id",
            flat=True,
        )
    )


def get_previous_movement_phase(retreat_phase):
    return (
        GamePhase.objects
        .filter(
            game=retreat_phase.game,
            sequence__lt=retreat_phase.sequence,
            phase_type="movement",
        )
        .order_by("-sequence")
        .first()
    )


def can_unit_retreat(
    unit,
    retreat_phase,
    target_province,
    target_coast=None,
):
    if not unit.is_dislodged:
        return False

    # Nemůže zpět do provincie,
    # odkud přišel útok.
    if (
        unit.dislodged_by_origin_id
        == target_province.id
    ):
        return False

    # Provincie nesmí být obsazena
    # aktivní jednotkou.
    if Unit.objects.filter(
        game=unit.game,
        province=target_province,
        is_dislodged=False,
    ).exists():
        return False

    movement_phase = get_previous_movement_phase(
        retreat_phase
    )

    if movement_phase is None:
        return False

    # Nelze ustoupit do provincie,
    # ve které vznikl standoff.
    standoff_ids = get_standoff_province_ids(
        movement_phase
    )

    if target_province.id in standoff_ids:
        return False

    # Použijeme stejnou geografickou
    # kontrolu jako u normálního pohybu.
    return can_unit_move(
        unit,
        target_province,
        target_coast,
    )


@transaction.atomic
def resolve_retreat_phase(phase):
    phase = lock_phase(phase)

    if phase.status != "open" or phase.game.status != "active":
        raise RetreatError(
            "Tato fáze už byla vyhodnocena."
        )

    if phase.phase_type != "retreat":
        raise RetreatError(
            "Tato fáze není Retreat."
        )

    game = phase.game

    dislodged_units = list(
        Unit.objects
        .select_for_update()
        .filter(
            game=game,
            is_dislodged=True,
        )
        .select_related(
            "province",
            "coast",
        )
    )

    orders = {
        order.unit_id: order
        for order in Order.objects.filter(
            phase=phase
        ).select_related(
            "target_province",
            "target_coast",
        )
    }

    # Jednotka bez rozkazu se automaticky
    # rozpustí.
    for unit in dislodged_units:
        if unit.id not in orders:
            orders[unit.id] = Order.objects.create(
                phase=phase,
                unit=unit,
                order_type="disband",
                origin_province=(
                    unit.dislodged_from
                    or unit.province
                ),
                origin_coast=unit.coast,
                result="pending",
                result_reason="",
                is_default=True,
            )

    retreat_orders = [
        order
        for order in orders.values()
        if order.order_type == "retreat"
    ]

    # Kolize dvou retreatů do stejné provincie.
    destinations = {}

    for order in retreat_orders:
        destinations.setdefault(
            order.target_province_id,
            [],
        ).append(order)

    successful_retreats = []

    for unit in dislodged_units:
        order = orders[unit.id]

        if order.order_type == "disband":
            order.result = "success"
            order.result_reason = "disband"
            continue

        if order.order_type != "retreat":
            order.result = "failed"
            order.result_reason = "invalid_retreat"
            continue

        if not can_unit_retreat(
            unit,
            phase,
            order.target_province,
            order.target_coast,
        ):
            order.result = "failed"
            order.result_reason = "illegal_retreat"
            continue

        same_destination = destinations.get(
            order.target_province_id,
            [],
        )

        if len(same_destination) > 1:
            order.result = "failed"
            order.result_reason = (
                "retreat_collision"
            )
            continue

        order.result = "success"
        order.result_reason = "retreat"

        successful_retreats.append(
            order
        )

    Order.objects.bulk_update(
        list(orders.values()),
        [
            "result",
            "result_reason",
        ],
    )

    save_snapshot(phase, [order_snapshot(order) for order in orders.values()])

    # Úspěšné retreaty.
    retreated_unit_ids = set()

    for order in successful_retreats:
        unit = order.unit

        unit.province = order.target_province
        unit.coast = order.target_coast

        unit.is_dislodged = False
        unit.dislodged_from = None
        unit.dislodged_by_origin = None

        Unit.objects.bulk_update(
            [unit],
            [
                "province",
                "coast",
                "is_dislodged",
                "dislodged_from",
                "dislodged_by_origin",
            ],
        )

        retreated_unit_ids.add(
            unit.id
        )

    # Všechny ostatní vytlačené jednotky
    # jsou rozpuštěny.
    units_to_delete = [
        unit.id
        for unit in dislodged_units
        if unit.id not in retreated_unit_ids
    ]

    if units_to_delete:
        Unit.objects.filter(
            id__in=units_to_delete
        ).delete()

    phase.status = "resolved"
    phase.resolved_at = timezone.now()

    phase.save(
        update_fields=[
            "status",
            "resolved_at",
        ]
    )

    create_next_after_retreat(
        phase
    )

    capture_resolved_phase_state(phase)

    return phase
