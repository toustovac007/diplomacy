from apps.maps.models import Province, Coast

from apps.games.models import Unit


STARTING_UNITS = {
    "AUS": [
        ("army", "VIE", None),
        ("army", "BUD", None),
        ("fleet", "TRI", None),
    ],

    "ENG": [
        ("fleet", "LON", None),
        ("fleet", "EDI", None),
        ("army", "LVP", None),
    ],

    "FRA": [
        ("army", "PAR", None),
        ("army", "MAR", None),
        ("fleet", "BRE", None),
    ],

    "GER": [
        ("army", "BER", None),
        ("army", "MUN", None),
        ("fleet", "KIE", None),
    ],

    "ITA": [
        ("army", "ROM", None),
        ("army", "VEN", None),
        ("fleet", "NAP", None),
    ],

    "RUS": [
        ("army", "MOS", None),
        ("army", "WAR", None),
        ("fleet", "SEV", None),
        ("fleet", "STP", "sc"),
    ],

    "TUR": [
        ("army", "CON", None),
        ("army", "SMY", None),
        ("fleet", "ANK", None),
    ],
}


def create_starting_units(game):
    if game.units.exists():
        raise ValueError(
            "Tato hra už obsahuje jednotky."
        )

    players = game.players.all()

    for player in players:
        placements = STARTING_UNITS.get(player.country)

        if placements is None:
            raise ValueError(
                f"Neznámý stát: {player.country}"
            )

        for unit_type, province_code, coast_code in placements:
            province = Province.objects.get(
                code=province_code
            )

            coast = None

            if coast_code is not None:
                coast = Coast.objects.get(
                    province=province,
                    code=coast_code,
                )

            Unit.objects.create(
                game=game,
                owner=player,
                unit_type=unit_type,
                province=province,
                coast=coast,
            )