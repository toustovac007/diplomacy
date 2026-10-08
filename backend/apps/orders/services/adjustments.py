from apps.games.models import (
    SupplyCenterOwnership,
    Unit,
)
from apps.maps.models import Province

from collections import deque

from apps.maps.models import ProvinceAdjacency

def get_adjustment_delta(player):
    """
    Kladné číslo = počet BUILD.
    Záporné číslo = počet povinných DISBAND.
    Nula = žádná změna.
    """

    centers = (
        SupplyCenterOwnership.objects
        .filter(
            game=player.game,
            owner=player,
        )
        .count()
    )

    units = (
        Unit.objects
        .filter(
            game=player.game,
            owner=player,
            is_dislodged=False,
        )
        .count()
    )

    return centers - units


def get_build_count(player):
    return max(
        get_adjustment_delta(player),
        0,
    )


def get_disband_count(player):
    return max(
        -get_adjustment_delta(player),
        0,
    )


def get_buildable_home_centers(player):
    """
    Vrátí neobsazená domácí supply centra,
    která hráč aktuálně vlastní.
    """

    owned_home_center_ids = (
        SupplyCenterOwnership.objects
        .filter(
            game=player.game,
            owner=player,
            province__is_supply_center=True,
            province__home_country__code=player.country,
        )
        .values_list(
            "province_id",
            flat=True,
        )
    )

    occupied_ids = (
        Unit.objects
        .filter(
            game=player.game,
            is_dislodged=False,
        )
        .values_list(
            "province_id",
            flat=True,
        )
    )

    return (
        Province.objects
        .filter(
            id__in=owned_home_center_ids,
        )
        .exclude(
            id__in=occupied_ids,
        )
        .order_by("code")
    )


def can_build_unit(
    player,
    province,
    unit_type,
    coast=None,
):
    # Hráč vůbec nemá právo stavět.
    if get_build_count(player) <= 0:
        return False

    # Musí jít o supply centrum,
    # které hráč vlastní.
    ownership_exists = (
        SupplyCenterOwnership.objects
        .filter(
            game=player.game,
            province=province,
            owner=player,
        )
        .exists()
    )

    if not ownership_exists:
        return False

    # Musí jít o domácí centrum daného státu.
    if (
        province.home_country is None
        or province.home_country.code != player.country
    ):
        return False

    # Centrum musí být prázdné.
    if Unit.objects.filter(
        game=player.game,
        province=province,
        is_dislodged=False,
    ).exists():
        return False

    if unit_type == "army":
        # Armádu nelze postavit na moři.
        if province.province_type == "sea":
            return False

        # Army nepoužívá coast.
        if coast is not None:
            return False

        return True

    if unit_type == "fleet":
        # Flotila musí vzniknout v pobřežní provincii.
        if province.province_type != "coastal":
            return False

        coast_count = province.coasts.count()

        # STP, SPA, BUL...
        if coast_count > 1:
            if coast is None:
                return False

            if coast.province_id != province.id:
                return False

        elif coast is not None:
            return False

        return True

    return False

from django.db import transaction
from django.utils import timezone

from apps.games.models import (
    GamePhase,
    GamePlayer,
    Unit,
)

from apps.games.services.phase_manager import (
    create_next_after_adjustment,
)

from apps.orders.models import (
    AdjustmentOrder,
)

class AdjustmentError(Exception):
    pass


@transaction.atomic
def resolve_adjustment_phase(
    phase,
    allow_automatic_disbands=False,
):
    phase = (
        GamePhase.objects
        .select_for_update()
        .select_related("game")
        .get(pk=phase.pk)
    )

    if phase.status != "open":
        raise AdjustmentError(
            "Tato fáze už byla vyhodnocena."
        )

    if phase.phase_type != "adjustment":
        raise AdjustmentError(
            "Tato fáze není Adjustment."
        )

    if phase.season != "winter":
        raise AdjustmentError(
            "Adjustment lze vyhodnotit pouze v zimě."
        )

    players = list(
        GamePlayer.objects
        .filter(game=phase.game)
        .select_related("user")
    )

    orders = list(
        AdjustmentOrder.objects
        .select_for_update()
        .filter(phase=phase)
        .select_related(
            "player",
            "province",
            "coast",
            "unit",
            "unit__province",
        )
        .order_by("id")
    )

    orders_by_player = {}

    for player in players:
        orders_by_player[player.id] = []

    for order in orders:
        orders_by_player.setdefault(
            order.player_id,
            [],
        ).append(order)

    # =====================================
    # 1. NEJDŘÍV VŠECHNO ZVALIDUJEME
    # =====================================

    deltas = {}

    for player in players:
        delta = get_adjustment_delta(
            player
        )

        deltas[player.id] = delta

        player_orders = orders_by_player.get(
            player.id,
            [],
        )

        build_orders = [
            order
            for order in player_orders
            if order.order_type == "build"
        ]

        disband_orders = [
            order
            for order in player_orders
            if order.order_type == "disband"
        ]

        # -----------------------------
        # BUILD
        # -----------------------------

        if delta > 0:
            if disband_orders:
                raise AdjustmentError(
                    f"{player.country} má právo stavět, "
                    "nemůže zadávat DISBAND."
                )

            if len(build_orders) > delta:
                raise AdjustmentError(
                    f"{player.country} může postavit "
                    f"maximálně {delta} jednotek."
                )

            for order in build_orders:
                if order.province is None:
                    raise AdjustmentError(
                        "BUILD nemá provincii."
                    )

                if order.unit_type not in (
                    "army",
                    "fleet",
                ):
                    raise AdjustmentError(
                        "Neplatný typ jednotky pro BUILD."
                    )

                if not can_build_unit(
                    player=player,
                    province=order.province,
                    unit_type=order.unit_type,
                    coast=order.coast,
                ):
                    raise AdjustmentError(
                        f"Neplatný BUILD v "
                        f"{order.province.code}."
                    )

        # -----------------------------
        # DISBAND
        # -----------------------------

        elif delta < 0:
            required = abs(delta)

            if build_orders:
                raise AdjustmentError(
                    f"{player.country} musí rozpouštět "
                    "jednotky, nemůže stavět."
                )

            if len(disband_orders) > required:
                raise AdjustmentError(
                    f"{player.country} může rozpustit "
                    f"maximálně {required} jednotek."
                )

            if (
                    len(disband_orders) < required
                    and not allow_automatic_disbands
            ):
                raise AdjustmentError(
                    f"{player.country} musí zadat přesně "
                    f"{required} DISBAND rozkazů."
                )

            unit_ids = set()

            for order in disband_orders:
                if order.unit is None:
                    raise AdjustmentError(
                        "DISBAND nemá jednotku."
                    )

                if (
                    order.unit.game_id
                    != phase.game_id
                ):
                    raise AdjustmentError(
                        "Jednotka nepatří do této hry."
                    )

                if (
                    order.unit.owner_id
                    != player.id
                ):
                    raise AdjustmentError(
                        "Nelze rozpustit cizí jednotku."
                    )

                if order.unit.is_dislodged:
                    raise AdjustmentError(
                        "V zimní fázi nemůže být "
                        "jednotka stále vytlačená."
                    )

                if order.unit_id in unit_ids:
                    raise AdjustmentError(
                        "Stejnou jednotku nelze "
                        "rozpustit dvakrát."
                    )

                unit_ids.add(
                    order.unit_id
                )

        # -----------------------------
        # ŽÁDNÁ ÚPRAVA
        # -----------------------------

        else:
            if player_orders:
                raise AdjustmentError(
                    f"{player.country} nemá žádnou "
                    "zimní úpravu."
                )

    # =====================================
    # 2. PROVEDEME BUILD
    # =====================================

    for player in players:
        delta = deltas[player.id]

        if delta <= 0:
            continue

        player_orders = orders_by_player.get(
            player.id,
            [],
        )

        build_orders = [
            order
            for order in player_orders
            if order.order_type == "build"
        ]

        for order in build_orders:
            Unit.objects.create(
                game=phase.game,
                owner=player,
                unit_type=order.unit_type,
                province=order.province,
                coast=order.coast,
            )

            order.result = "success"
            order.result_reason = "build"

    # =====================================
    # 3. PROVEDEME DISBAND
    # =====================================

    # =====================================
    # 3. PROVEDEME DISBAND
    # =====================================

    for player in players:
        delta = deltas[player.id]

        if delta >= 0:
            continue

        required = abs(delta)

        player_orders = orders_by_player.get(
            player.id,
            [],
        )

        disband_orders = [
            order
            for order in player_orders
            if order.order_type == "disband"
        ]

        manually_selected_ids = {
            order.unit_id
            for order in disband_orders
            if order.unit_id is not None
        }

        missing_count = (
                required
                - len(disband_orders)
        )

        automatic_units = []

        if missing_count > 0:
            if not allow_automatic_disbands:
                raise AdjustmentError(
                    f"{player.country} nemá zadaný "
                    "dostatečný počet DISBAND rozkazů."
                )

            automatic_units = (
                get_automatic_disband_units(
                    player=player,
                    count=missing_count,
                    excluded_unit_ids=manually_selected_ids,
                )
            )

            if len(automatic_units) != missing_count:
                raise AdjustmentError(
                    f"Nepodařilo se určit automatický "
                    f"DISBAND pro {player.country}."
                )

        # -------------------------------
        # Ručně zadané DISBANDy
        # -------------------------------

        for order in disband_orders:
            unit = order.unit

            order.result = "success"
            order.result_reason = "disband"

            order.save(
                update_fields=[
                    "result",
                    "result_reason",
                ]
            )

            unit.delete()

        # -------------------------------
        # Automatické DISBANDy
        # -------------------------------

        for unit in automatic_units:
            auto_order = AdjustmentOrder.objects.create(
                phase=phase,
                player=player,
                order_type="disband",
                unit=unit,
                unit_type=None,
                province=None,
                coast=None,
                result="success",
                result_reason="automatic_disband",
                is_default=True,
            )

            unit.delete()

    # =====================================
    # 4. UZAVŘEME WINTER
    # =====================================

    phase.status = "resolved"
    phase.resolved_at = timezone.now()

    phase.save(
        update_fields=[
            "status",
            "resolved_at",
        ]
    )

    # =====================================
    # 5. SPRING DALŠÍHO ROKU
    # =====================================

    create_next_after_adjustment(
        phase
    )

    return phase


def get_distance_to_owned_center(
    province_id,
    owned_center_ids,
):
    """
    Nejkratší vzdálenost provincie od libovolného
    supply centra vlastněného hráčem.

    Počítáme čistě sousední provincie bez ohledu
    na army/fleet movement pravidla.
    """

    if not owned_center_ids:
        return float("inf")

    if province_id in owned_center_ids:
        return 0

    adjacency_rows = (
        ProvinceAdjacency.objects
        .values_list(
            "from_province_id",
            "to_province_id",
        )
        .distinct()
    )

    graph = {}

    for from_id, to_id in adjacency_rows:
        graph.setdefault(
            from_id,
            set(),
        ).add(to_id)

        graph.setdefault(
            to_id,
            set(),
        ).add(from_id)

    queue = deque(
        [
            (province_id, 0)
        ]
    )

    visited = {
        province_id
    }

    while queue:
        current_id, distance = queue.popleft()

        for neighbour_id in graph.get(
            current_id,
            set(),
        ):
            if neighbour_id in visited:
                continue

            if neighbour_id in owned_center_ids:
                return distance + 1

            visited.add(
                neighbour_id
            )

            queue.append(
                (
                    neighbour_id,
                    distance + 1,
                )
            )

    return float("inf")


def get_automatic_disband_units(
    player,
    count,
    excluded_unit_ids=None,
):
    """
    Vrátí jednotky, které se mají automaticky
    rozpustit podle pravidel Civil Disorder.
    """

    if excluded_unit_ids is None:
        excluded_unit_ids = set()

    owned_center_ids = set(
        SupplyCenterOwnership.objects
        .filter(
            game=player.game,
            owner=player,
        )
        .values_list(
            "province_id",
            flat=True,
        )
    )

    units = list(
        Unit.objects
        .filter(
            game=player.game,
            owner=player,
            is_dislodged=False,
        )
        .exclude(
            id__in=excluded_unit_ids,
        )
        .select_related(
            "province",
        )
    )

    ranked_units = []

    for unit in units:
        distance = get_distance_to_owned_center(
            unit.province_id,
            owned_center_ids,
        )

        # Supply center jednotky mají nižší
        # prioritu pro odstranění.
        on_supply_center = (
            unit.province.is_supply_center
        )

        # Fleet má při shodě přednost před Army.
        unit_type_priority = (
            0
            if unit.unit_type == "fleet"
            else 1
        )

        ranked_units.append(
            (
                1 if on_supply_center else 0,
                -distance,
                unit_type_priority,
                unit.province.name.lower(),
                unit,
            )
        )

    ranked_units.sort(
        key=lambda item: item[:4]
    )

    return [
        item[4]
        for item in ranked_units[:count]
    ]


