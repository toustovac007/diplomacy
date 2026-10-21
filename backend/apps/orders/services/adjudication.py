from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from apps.games.models import GamePhase, Unit
from apps.orders.models import Order
from apps.orders.services.snapshots import order_snapshot, save_snapshot, capture_resolved_phase_state
from apps.orders.services.convoys import ConvoyRoutes

from apps.games.services.phase_manager import (
    create_next_after_movement,
)
class AdjudicationError(Exception):
    pass


def _evaluate_battles(units, orders, active_convoys):
    """Evaluate in memory; only the final convoy-consistent result is persisted."""
    orders = sorted(orders, key=lambda order: order.origin_province.code)
    for order in orders:
        order.result = "pending"
        order.result_reason = ""
    orders_by_unit = {
        order.unit_id: order
        for order in orders
    }

    units_by_province = {
        unit.province_id: unit
        for unit in units
    }

    move_orders = [
        order
        for order in orders
        if order.order_type == "move"
        and (not order.via_convoy or order.id in active_convoys)
    ]

    support_orders = [
        order
        for order in orders
        if order.order_type == "support"
    ]

    # =========================================
    # 2. KONTROLA SUPPORT ORDERŮ
    # =========================================

    valid_supports = []

    for support in support_orders:
        supported_order = orders_by_unit.get(
            support.supported_unit_id
        )

        if supported_order is None:
            support.result = "failed"
            support.result_reason = "void_support"
            continue

        is_support_hold = (
            support.supported_origin_province_id
            == support.support_target_province_id
        )

        if is_support_hold:
            # HOLD, SUPPORT and CONVOY are stationary movement-phase orders.
            if supported_order.order_type == "move":
                support.result = "failed"
                support.result_reason = "void_support"
                continue

        else:
            if supported_order.order_type != "move":
                support.result = "failed"
                support.result_reason = "void_support"
                continue

            if (
                supported_order.target_province_id
                != support.support_target_province_id
            ):
                support.result = "failed"
                support.result_reason = "void_support"
                continue

        valid_supports.append(support)

    # =========================================
    # 3. SUPPORT CUT
    # =========================================

    uncut_supports = []

    for support in valid_supports:
        support_cut = False

        for attack in move_orders:
            if (
                attack.target_province_id
                != support.origin_province_id
            ):
                continue

            # Vlastní stát si svou podporu necutne.
            if (
                attack.unit.owner.country
                == support.unit.owner.country
            ):
                continue

            # Útok z provincie, do které je podpora
            # směřována, podporu běžně nepřeruší.
            if (
                attack.origin_province_id
                == support.support_target_province_id
            ):
                continue

            support_cut = True
            break

        if support_cut:
            support.result = "failed"
            support.result_reason = "support_cut"
        else:
            support.result = "success"
            support.result_reason = "support"
            uncut_supports.append(support)

    # =========================================
    # 4. SÍLA ÚTOKŮ
    # =========================================

    attack_strength = {}

    for move in move_orders:
        strength = 1

        for support in uncut_supports:
            if (
                support.supported_unit_id
                == move.unit_id
                and
                support.support_target_province_id
                == move.target_province_id
                and
                support.supported_origin_province_id
                != support.support_target_province_id
            ):
                strength += 1

        attack_strength[move.id] = strength

    # =========================================
    # 5. SÍLA OBRANY
    # =========================================

    defense_strength = {}

    for unit in units:
        strength = 1

        unit_order = orders_by_unit.get(
            unit.id
        )

        if (
            unit_order
            and unit_order.order_type != "move"
        ):
            for support in uncut_supports:
                if (
                    support.supported_unit_id
                    == unit.id
                    and
                    support.supported_origin_province_id
                    == support.support_target_province_id
                ):
                    strength += 1

        defense_strength[unit.id] = strength

    # =========================================
    # 6. NEJLEPŠÍ ÚTOK NA KAŽDOU PROVINCII
    # =========================================

    attacks_by_destination = defaultdict(list)

    for move in move_orders:
        attacks_by_destination[
            move.target_province_id
        ].append(move)

    destination_winner = {}

    for province_id, attacks in (
        attacks_by_destination.items()
    ):
        max_strength = max(
            attack_strength[attack.id]
            for attack in attacks
        )

        strongest = [
            attack
            for attack in attacks
            if attack_strength[attack.id]
            == max_strength
        ]

        if len(strongest) == 1:
            destination_winner[
                province_id
            ] = strongest[0]

        else:
            destination_winner[
                province_id
            ] = None

    # =========================================
    # 7. VYHODNOCENÍ MOVE
    # =========================================

    states = {}
    reasons = {}
    dislodged_by = {}

    def resolve_move(order):
        if order.id in states:
            if states[order.id] == "visiting":
                # Kruhový pohyb 3+ jednotek.
                return True

            return states[order.id]

        # Není nejsilnějším unikátním útokem
        # na cílovou provincii.
        winner = destination_winner.get(
            order.target_province_id
        )

        if winner is None:
            states[order.id] = False
            reasons[order.id] = "standoff"
            return False

        if winner.id != order.id:
            states[order.id] = False
            reasons[order.id] = "outmatched"
            return False

        states[order.id] = "visiting"

        occupant = units_by_province.get(
            order.target_province_id
        )

        # Cílová provincie je prázdná.
        if occupant is None:
            states[order.id] = True
            reasons[order.id] = "move"
            return True

        occupant_order = orders_by_unit.get(
            occupant.id
        )

        # ---------------------------------
        # HEAD TO HEAD
        # ---------------------------------

        if (
            occupant_order
            and occupant_order.id in attack_strength
            and not order.via_convoy
            and not occupant_order.via_convoy
            and
            occupant_order.target_province_id
            == order.origin_province_id
        ):
            our_strength = attack_strength[
                order.id
            ]

            their_strength = attack_strength[
                occupant_order.id
            ]

            if our_strength > their_strength:
                # Vlastní jednotku nelze vytlačit.
                if (
                    occupant.owner.country
                    == order.unit.owner.country
                ):
                    states[order.id] = False
                    reasons[order.id] = (
                        "self_dislodge"
                    )
                    return False

                states[order.id] = True
                reasons[order.id] = "move"

                dislodged_by[
                    occupant.id
                ] = order

                return True

            states[order.id] = False
            reasons[order.id] = (
                "head_to_head"
            )

            return False

        # ---------------------------------
        # OBSAZENÁ PROVINCIE, JEDNOTKA ODCHÁZÍ
        # ---------------------------------

        if (
            occupant_order
            and occupant_order.id in attack_strength
        ):
            if resolve_move(
                occupant_order
            ):
                states[order.id] = True
                reasons[order.id] = "move"
                return True

        # ---------------------------------
        # JEDNOTKA ZŮSTÁVÁ
        # ---------------------------------

        our_strength = attack_strength[
            order.id
        ]

        their_strength = defense_strength[
            occupant.id
        ]

        if our_strength <= their_strength:
            states[order.id] = False
            reasons[order.id] = "defended"
            return False

        # Nesmíme vytlačit vlastní jednotku.
        if (
            occupant.owner.country
            == order.unit.owner.country
        ):
            states[order.id] = False
            reasons[order.id] = (
                "self_dislodge"
            )
            return False

        states[order.id] = True
        reasons[order.id] = "move"

        dislodged_by[
            occupant.id
        ] = order

        return True

    for move in move_orders:
        resolve_move(move)

    # =========================================
    # 8. VÝSLEDKY MOVE / HOLD
    # =========================================

    successful_moves = []

    for order in orders:
        if order.order_type == "move":
            if states.get(order.id) is True:
                order.result = "success"
                order.result_reason = "move"

                successful_moves.append(
                    order
                )

            else:
                order.result = "failed"
                order.result_reason = (
                    reasons.get(
                        order.id,
                        "failed",
                    )
                )

        elif order.order_type == "hold":
            if order.unit_id in dislodged_by:
                order.result = "failed"
                order.result_reason = (
                    "dislodged"
                )
            else:
                order.result = "success"
                order.result_reason = "hold"

    # Supporty jsme nastavili výše.
    # Pokud podporující jednotka byla vytlačena,
    # označíme podporu jako neúspěšnou.

    for support in support_orders:
        if support.unit_id in dislodged_by:
            support.result = "failed"
            support.result_reason = (
                "dislodged"
            )

    return successful_moves, dislodged_by


def _resolve_convoys(units, orders):
    if not any(order.via_convoy or order.order_type == "convoy" for order in orders):
        return _evaluate_battles(units, orders, set())
    routes = ConvoyRoutes(orders)
    moves = {o.id: o for o in orders if o.order_type == "move" and o.via_convoy}
    candidates = {key for key, move in moves.items() if routes.exists(move)}
    paradoxes = set()

    def follow(initial, eligible):
        # Test both pessimistic and optimistic assumptions. A support-cut paradox
        # can have TWO fixed points, so convergence from only one side is unsafe.
        state = frozenset(initial)
        history = []
        for _ in range(2 * len(eligible) + 2):
            if state in history:
                cycle = history[history.index(state):]
                return state, set.union(*map(set, cycle)) - set.intersection(*map(set, cycle))
            history.append(state)
            _, dislodged = _evaluate_battles(units, orders, state)
            next_state = frozenset(key for key in eligible if routes.exists(moves[key], dislodged))
            if next_state == state:
                return state, set()
            state = next_state
        # Bounded conservative Szykman-style fallback for long dependency cycles:
        # fail unsettled transports, then reevaluate the remaining orders.
        return state, set.union(*map(set, history)) - set.intersection(*map(set, history))

    # Every retry permanently removes at least one eligible transport, bounding
    # the outer loop by the number of convoyed moves regardless of input order.
    while True:
        eligible = candidates - paradoxes
        low, low_cycle = follow(set(), eligible)
        high, high_cycle = follow(eligible, eligible)
        uncertain = low_cycle | high_cycle | (low ^ high)
        if not uncertain:
            active = set(low)
            break
        paradoxes.update(uncertain)

    successful_moves, dislodged = _evaluate_battles(units, orders, active)
    for key, move in moves.items():
        if key not in active:
            move.result = "failed"
            move.result_reason = (
                "convoy_paradox" if key in paradoxes else
                "convoy_disrupted" if key in candidates else "no_convoy_route"
            )
    by_unit = {o.unit_id: o for o in orders}
    for fleet in routes.fleets:
        move = by_unit.get(fleet.convoyed_unit_id)
        fleet.result = "failed"
        if fleet.unit_id in dislodged:
            fleet.result_reason = "convoy_disrupted"
        elif move is None or move.id not in moves or fleet not in routes.matching(move):
            fleet.result_reason = "convoy_order_mismatch"
        elif move.id not in active:
            fleet.result_reason = move.result_reason
        else:
            fleet.result = "success"
            fleet.result_reason = "convoy"
    return successful_moves, dislodged


@transaction.atomic
def resolve_movement_phase(phase):
    phase = (
        GamePhase.objects
        .select_for_update()
        .select_related("game")
        .get(pk=phase.pk)
    )

    if phase.status != "open":
        raise AdjudicationError(
            "Tato fáze už byla vyhodnocena."
        )

    if phase.phase_type != "movement":
        raise AdjudicationError(
            "Tento resolver umí pouze Movement fázi."
        )

    game = phase.game

    units = list(
        Unit.objects
        .select_for_update()
        .filter(
            game=game,
            is_dislodged=False,
        )
        .select_related(
            "owner",
            "province",
            "coast",
        )
    )

    # =========================================
    # 1. AUTOMATICKÉ HOLD
    # =========================================

    existing_orders = {
        order.unit_id: order
        for order in Order.objects.filter(
            phase=phase
        )
    }

    for unit in units:
        if unit.id not in existing_orders:
            Order.objects.create(
                phase=phase,
                unit=unit,
                order_type="hold",
                origin_province=unit.province,
                origin_coast=unit.coast,
                result="pending",
                result_reason="",
                is_default=True,
            )

    orders = list(
        Order.objects
        .select_for_update()
        .filter(phase=phase)
        .select_related(
            "unit",
            "unit__owner",
            "unit__province",
            "origin_province",
            "origin_coast",
            "target_province",
            "target_coast",
            "supported_unit",
            "supported_unit__owner",
            "supported_origin_province",
            "support_target_province",
            "support_target_coast",
        )
    )

    successful_moves, dislodged_by = _resolve_convoys(units, orders)
    save_snapshot(phase, [order_snapshot(order) for order in orders])

    Order.objects.bulk_update(
        orders,
        [
            "result",
            "result_reason",
        ],
    )

    # =========================================
    # 9. VYTLAČENÉ JEDNOTKY
    # =========================================

    dislodged_units = []

    for unit_id, attack_order in (
        dislodged_by.items()
    ):
        unit = next(
            unit
            for unit in units
            if unit.id == unit_id
        )

        unit.is_dislodged = True

        unit.dislodged_from = (
            unit.province
        )

        unit.dislodged_by_origin = (
            attack_order.origin_province
        )

        dislodged_units.append(
            unit
        )

    if dislodged_units:
        Unit.objects.bulk_update(
            dislodged_units,
            [
                "is_dislodged",
                "dislodged_from",
                "dislodged_by_origin",
            ],
        )

    # =========================================
    # 10. SIMULTÁNNÍ POHYB
    # =========================================

    moved_units = []

    for order in successful_moves:
        unit = order.unit

        unit.province = (
            order.target_province
        )

        unit.coast = (
            order.target_coast
        )

        unit.is_dislodged = False
        unit.dislodged_from = None
        unit.dislodged_by_origin = None

        moved_units.append(
            unit
        )

    if moved_units:
        Unit.objects.bulk_update(
            moved_units,
            [
                "province",
                "coast",
                "is_dislodged",
                "dislodged_from",
                "dislodged_by_origin",
            ],
        )

    # =========================================
    # 11. UZAVŘENÍ FÁZE
    # =========================================

    phase.status = "resolved"
    phase.resolved_at = timezone.now()

    phase.save(
        update_fields=[
            "status",
            "resolved_at",
        ]
    )

    create_next_after_movement(
        movement_phase=phase,
        has_dislodged_units=bool(
            dislodged_units
        ),
    )

    capture_resolved_phase_state(phase)

    return phase
