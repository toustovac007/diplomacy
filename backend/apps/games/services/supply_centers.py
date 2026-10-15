from apps.games.models import (
    GamePlayer,
    SupplyCenterOwnership,
    Unit,
)
from apps.maps.models import Province


def initialize_supply_centers(game):
    players = {
        player.country: player
        for player in GamePlayer.objects.filter(
            game=game
        )
    }

    supply_centers = (
        Province.objects
        .filter(is_supply_center=True)
        .select_related("home_country")
    )

    for province in supply_centers:
        owner = None

        if province.home_country:
            owner = players.get(
                province.home_country.code
            )

        SupplyCenterOwnership.objects.get_or_create(
            game=game,
            province=province,
            defaults={
                "owner": owner,
            },
        )


def update_supply_center_ownership(game):
    # Pro jistotu doplní chybějící SC záznamy.
    initialize_supply_centers(game)

    units_on_centers = (
        Unit.objects
        .filter(
            game=game,
            is_dislodged=False,
            province__is_supply_center=True,
        )
        .select_related(
            "province",
            "owner",
        )
    )

    for unit in units_on_centers:
        SupplyCenterOwnership.objects.filter(
            game=game,
            province=unit.province,
        ).update(
            owner=unit.owner
        )


def get_supply_center_count(player):
    return SupplyCenterOwnership.objects.filter(
        game=player.game,
        owner=player,
    ).count()


def get_adjustment_delta(player):
    """Owned centers minus active units: positive builds, negative disbands."""
    units = Unit.objects.filter(
        game=player.game,
        owner=player,
        is_dislodged=False,
    ).count()
    return get_supply_center_count(player) - units
