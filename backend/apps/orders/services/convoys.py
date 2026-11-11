"""Convoy geography; route availability is decided only during adjudication."""
from collections import defaultdict

from apps.maps.models import ProvinceAdjacency


def can_army_convoy(unit, destination, coast=None):
    return (
        unit.unit_type == "army"
        and unit.province.province_type == "coastal"
        and destination.province_type == "coastal"
        and destination.id != unit.province_id
        and coast is None
    )


class ConvoyRoutes:
    def __init__(self, orders):
        self.fleets = [order for order in orders if order.order_type == "convoy"]
        self.adjacency = defaultdict(set)
        for origin, target in ProvinceAdjacency.objects.filter(fleet_allowed=True).values_list(
            "from_province_id", "to_province_id",
        ):
            # Coast-specific edges collapse to provinces: the passenger is an Army.
            self.adjacency[origin].add(target)

    def matching(self, move):
        return [order for order in self.fleets if (
            order.convoyed_unit_id == move.unit_id
            and order.convoyed_origin_province_id == move.origin_province_id
            and order.convoy_target_province_id == move.target_province_id
            and order.unit.unit_type == "fleet"
            and order.origin_province.province_type == "sea"
        )]

    def exists(self, move, dislodged=()):
        if not can_army_convoy(move.unit, move.target_province, move.target_coast):
            return False
        seas = {order.origin_province_id for order in self.matching(move)
                if order.unit_id not in dislodged}
        frontier = list(self.adjacency[move.origin_province_id] & seas)
        visited = set(frontier)
        while frontier:
            sea = frontier.pop()
            if move.target_province_id in self.adjacency[sea]:
                return True
            neighbours = (self.adjacency[sea] & seas) - visited
            visited.update(neighbours)
            frontier.extend(neighbours)
        return False
