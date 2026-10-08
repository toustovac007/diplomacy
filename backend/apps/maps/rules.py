from .models import ProvinceAdjacency


def can_army_move(from_province, to_province):
    return ProvinceAdjacency.objects.filter(
        from_province=from_province,
        to_province=to_province,
        army_allowed=True,
    ).exists()


def can_fleet_move(
    from_province,
    to_province,
    from_coast=None,
    to_coast=None,
):
    query = ProvinceAdjacency.objects.filter(
        from_province=from_province,
        to_province=to_province,
        fleet_allowed=True,
    )

    if from_coast is not None:
        query = query.filter(
            from_coast=from_coast
        )

    if to_province.coasts.count() > 1:
        if to_coast is None:
            return False

        if to_coast.province_id != to_province.id:
            return False

        query = query.filter(
            to_coast=to_coast
        )

    elif to_coast is not None:
        return False

    return query.exists()


def can_unit_move(
    unit,
    target_province,
    target_coast=None,
):
    if unit.province_id == target_province.id:
        return False

    if unit.unit_type == "army":
        if target_coast is not None:
            return False

        return can_army_move(
            unit.province,
            target_province,
        )

    if unit.unit_type == "fleet":
        return can_fleet_move(
            from_province=unit.province,
            to_province=target_province,
            from_coast=unit.coast,
            to_coast=target_coast,
        )

    return False


def can_unit_support_to(
    unit,
    target_province,
    target_coast=None,
):
    """
    Jednotka může podporovat akci v provincii,
    do které by se sama mohla přesunout.

    Výjimka oproti běžnému MOVE:
    flotila může podporovat armádu do provincie
    s více pobřežími, aniž by armáda určovala
    konkrétní coast.
    """

    if unit.unit_type == "army":
        return can_army_move(
            unit.province,
            target_province,
        )

    if unit.unit_type == "fleet":
        query = ProvinceAdjacency.objects.filter(
            from_province=unit.province,
            to_province=target_province,
            fleet_allowed=True,
        )

        if unit.coast is not None:
            query = query.filter(
                from_coast=unit.coast
            )

        if target_coast is not None:
            if target_coast.province_id != target_province.id:
                return False

            query = query.filter(
                to_coast=target_coast
            )

        return query.exists()

    return False