"""JSON-only historical records, captured before related units can be deleted."""


def code(value):
    return value.code if value is not None else None


def order_snapshot(order):
    unit = order.unit
    return {
        "id": order.pk, "saved_unit_id": order.unit_id,
        "player_id": unit.owner_id, "country": unit.owner.country,
        "unit_type": unit.unit_type, "order_type": order.order_type,
        "origin": code(order.origin_province), "origin_coast_code": code(order.origin_coast),
        "target_code": code(order.target_province), "saved_target_coast": code(order.target_coast),
        "via_convoy": order.via_convoy,
        "supported_unit_id": order.supported_unit_id,
        "supported_unit_type": order.supported_unit.unit_type if order.supported_unit_id else None,
        "supported_origin": code(order.supported_origin_province),
        "supported_origin_coast_code": code(order.supported_origin_coast),
        "support_target_code": code(order.support_target_province),
        "saved_support_target_coast": code(order.support_target_coast),
        "convoyed_unit_id": order.convoyed_unit_id,
        "convoyed_unit_type": order.convoyed_unit.unit_type if order.convoyed_unit_id else None,
        "convoyed_origin": code(order.convoyed_origin_province),
        "convoy_target_code": code(order.convoy_target_province),
        "result": order.result, "result_reason": order.result_reason, "is_default": order.is_default,
    }


def adjustment_snapshot(order):
    unit = order.unit if order.order_type == "disband" else None
    return {
        "id": order.pk, "saved_unit_id": order.unit_id,
        "player_id": order.player_id, "country": order.player.country,
        "order_type": order.order_type,
        "unit_type": unit.unit_type if unit else order.unit_type,
        "origin": code(unit.province if unit else order.province),
        "origin_coast_code": code(unit.coast if unit else order.coast),
        "result": order.result, "result_reason": order.result_reason, "is_default": order.is_default,
    }


def save_snapshot(phase, orders):
    # Resolvers reject resolved phases; never append or reconstruct from old rows.
    phase.resolved_orders_snapshot = orders
    phase.save(update_fields=["resolved_orders_snapshot"])


def capture_resolved_phase_state(phase):
    """Called inside the resolver transaction, after all transition effects."""
    from apps.games.serializer import UnitSerializer, SupplyCenterOwnershipSerializer

    if phase.status != "resolved" or phase.resolved_state_snapshot is not None:
        return
    units = phase.game.units.select_related(
        "owner__user", "province", "coast", "dislodged_from"
    ).order_by("pk")
    rows = []
    for unit in units:
        row = dict(UnitSerializer(unit).data)
        row["dislodged_from"] = code(unit.dislodged_from)
        rows.append(row)
    centers = phase.game.supply_center_ownerships.select_related("province", "owner").order_by("province__code")
    phase.resolved_state_snapshot = {
        "units": rows,
        "supply_centers": list(SupplyCenterOwnershipSerializer(centers, many=True).data),
    }
    phase.save(update_fields=["resolved_state_snapshot"])
