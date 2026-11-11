from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.games.models import Game, GamePlayer, GamePhase, Unit, SupplyCenterOwnership
from apps.maps.models import Province
from apps.orders.models import Order
from apps.orders.services.adjudication import resolve_movement_phase, _resolve_convoys


class ConvoyTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_map', stdout=StringIO())
        cls.user = get_user_model().objects.create_user(username='convoyer', email='convoyer@test.cz')
        cls.enemy_user = get_user_model().objects.create_user(username='other', email='other@test.cz')
        cls.game = Game.objects.create(name='Convoys', creator=cls.user, status='active')
        cls.player = GamePlayer.objects.create(game=cls.game, user=cls.user, country='ENG')
        cls.enemy = GamePlayer.objects.create(game=cls.game, user=cls.enemy_user, country='FRA')
        cls.phase = GamePhase.objects.create(game=cls.game, sequence=1, year=1901,
            season='spring', phase_type='movement', status='open',
            deadline=timezone.now() + timedelta(days=1))

    def unit(self, code, kind='army', enemy=False):
        return Unit.objects.create(game=self.game, owner=self.enemy if enemy else self.player,
            province=Province.objects.get(code=code), unit_type=kind)

    def post(self, unit, order_type, expected=201, **fields):
        self.client.force_authenticate(unit.owner.user)
        response = self.client.post(f'/api/orders/games/{self.game.pk}/',
            dict(unit_id=unit.pk, order_type=order_type, **fields), format='json')
        self.assertEqual(response.status_code, expected, response.data)
        return response

    def move(self, unit, target, convoy=False):
        self.post(unit, 'move', target=target, via_convoy=convoy)

    def convoy(self, fleet, army, target='BEL'):
        self.post(fleet, 'convoy', convoyed_unit_id=army.pk, convoy_target=target)

    def support(self, unit, army, target):
        self.post(unit, 'support', supported_unit_id=army.pk, support_target=target)

    def setup_route(self, target='BEL', seas=('ENG',)):
        army = self.unit('LON')
        fleets = [self.unit(sea, 'fleet') for sea in seas]
        # Fleet orders may precede the army order.
        for fleet in fleets:
            self.convoy(fleet, army, target)
        self.move(army, target, True)
        return army, fleets

    def resolve(self):
        resolve_movement_phase(self.phase)

    def position(self, unit, code, dislodged=False):
        unit.refresh_from_db()
        self.assertEqual(unit.province.code, code)
        self.assertEqual(unit.is_dislodged, dislodged)

    def reason(self, unit, reason):
        self.assertEqual(Order.objects.get(phase=self.phase, unit=unit).result_reason, reason)

    def test_single_fleet_nonadjacent_convoy_and_readback(self):
        army, fleets = self.setup_route()
        response = self.client.get(f'/api/orders/games/{self.game.pk}/')
        data = response.data if isinstance(response.data, list) else response.data['results']
        saved = next(o for o in data if o['order_type'] == 'convoy')
        self.assertEqual(saved['convoyed_unit_id'], army.pk)
        self.assertEqual(saved['convoyed_origin'], 'LON')
        self.assertEqual(saved['convoy_target_code'], 'BEL')
        self.resolve()
        self.position(army, 'BEL')
        self.reason(fleets[0], 'convoy')

    def test_multi_fleet_convoy(self):
        army, _ = self.setup_route('TUN', ('ENG', 'MAO', 'WES'))
        self.resolve()
        self.position(army, 'TUN')

    def test_normal_nonadjacent_move_stays_illegal(self):
        self.post(self.unit('LON'), 'move', expected=400, target='BEL')

    def test_coastal_fleet_cannot_convoy(self):
        self.post(self.unit('BRE', 'fleet'), 'convoy', expected=400,
            convoyed_unit_id=self.unit('LON').pk, convoy_target='BEL')

    def test_foreign_army_can_be_convoyed(self):
        army = self.unit('LON', enemy=True)
        self.convoy(self.unit('ENG', 'fleet'), army)
        self.move(army, 'BEL', True)
        self.resolve()
        self.position(army, 'BEL')

    def test_fleet_cannot_be_convoyed(self):
        self.post(self.unit('ENG', 'fleet'), 'convoy', expected=400,
            convoyed_unit_id=self.unit('LON', 'fleet').pk, convoy_target='BEL')

    def test_invalid_army_convoy_endpoints(self):
        for origin, destination in [('LON', 'PAR'), ('LON', 'ENG'), ('LON', 'LON'), ('PAR', 'BEL')]:
            with self.subTest(origin=origin, destination=destination):
                army = self.unit(origin)
                self.post(army, 'move', expected=400, target=destination, via_convoy=True)
                army.delete()

    def test_via_convoy_requires_army_and_no_coast(self):
        self.post(self.unit('LON', 'fleet'), 'move', expected=400, target='BEL', via_convoy=True)
        self.post(self.unit('EDI'), 'move', expected=400, target='STP', target_coast_code='nc', via_convoy=True)

    def test_incomplete_chain(self):
        army, fleets = self.setup_route('TUN', ('ENG', 'WES'))
        self.resolve()
        self.position(army, 'LON')
        self.reason(army, 'no_convoy_route')
        self.reason(fleets[0], 'no_convoy_route')

    def test_no_matching_army_move(self):
        army = self.unit('LON')
        fleet = self.unit('ENG', 'fleet')
        self.convoy(fleet, army)
        self.resolve()
        self.position(army, 'LON')
        self.reason(fleet, 'convoy_order_mismatch')
        self.assertTrue(Order.objects.get(unit=army, phase=self.phase).is_default)

    def test_wrong_destination_does_not_make_route(self):
        army = self.unit('LON')
        fleet = self.unit('ENG', 'fleet')
        self.convoy(fleet, army, 'PIC')
        self.move(army, 'BEL', True)
        self.resolve()
        self.reason(army, 'no_convoy_route')
        self.reason(fleet, 'convoy_order_mismatch')

    def attack_channel(self, supported):
        attacker = self.unit('MAO', 'fleet', True)
        self.move(attacker, 'ENG')
        if supported:
            self.support(self.unit('IRI', 'fleet', True), attacker, 'ENG')
        return attacker

    def test_attack_without_dislodgement_does_not_disrupt(self):
        army, _ = self.setup_route()
        self.attack_channel(False)
        self.resolve()
        self.position(army, 'BEL')

    def test_dislodged_fleet_breaks_route(self):
        army, fleets = self.setup_route()
        self.attack_channel(True)
        self.resolve()
        self.position(army, 'LON')
        self.position(fleets[0], 'ENG', True)
        self.reason(army, 'convoy_disrupted')
        self.reason(fleets[0], 'convoy_disrupted')

    def test_alternate_route_survives(self):
        army, fleets = self.setup_route(seas=('ENG', 'NTH'))
        self.attack_channel(True)
        self.resolve()
        self.position(army, 'BEL')
        self.position(fleets[0], 'ENG', True)

    def test_supported_convoy_dislodges_defender_and_creates_retreat(self):
        army, _ = self.setup_route()
        defender = self.unit('BEL', enemy=True)
        self.support(self.unit('PIC'), army, 'BEL')
        self.resolve()
        self.position(army, 'BEL')
        self.position(defender, 'BEL', True)
        self.assertEqual(GamePhase.objects.get(game=self.game, status='open').phase_type, 'retreat')

    def test_equal_defense_bounces(self):
        army, fleets = self.setup_route()
        self.unit('BEL', enemy=True)
        self.resolve()
        self.position(army, 'LON')
        self.reason(army, 'defended')
        self.reason(fleets[0], 'convoy')

    def test_two_convoy_armies_standoff(self):
        first, _ = self.setup_route()
        second = self.unit('EDI', enemy=True)
        self.convoy(self.unit('NTH', 'fleet', True), second)
        self.move(second, 'BEL', True)
        self.resolve()
        self.reason(first, 'standoff')
        self.reason(second, 'standoff')

    def test_ordinary_head_to_head(self):
        first, second = self.unit('LON'), self.unit('WAL', enemy=True)
        self.move(first, 'WAL')
        self.move(second, 'LON')
        self.resolve()
        self.position(first, 'LON')
        self.position(second, 'WAL')
        self.reason(first, 'head_to_head')

    def test_convoy_exchange(self):
        army, _ = self.setup_route('WAL')
        other = self.unit('WAL', enemy=True)
        self.move(other, 'LON')
        self.resolve()
        self.position(army, 'WAL')
        self.position(other, 'LON')

    def support_cut_fixture(self, disrupted=False, absent=False):
        army, fleets = self.setup_route()
        if absent:
            self.post(fleets[0], 'hold')
        if disrupted:
            self.attack_channel(True)
        attack = self.unit('NTH', 'fleet', True)
        supporter = self.unit('BEL', 'fleet', True)
        self.move(attack, 'HOL')
        self.support(supporter, attack, 'HOL')
        self.unit('HOL', 'fleet')
        return army, attack, supporter

    def test_invalid_convoy_does_not_cut_support(self):
        _, attacker, supporter = self.support_cut_fixture(absent=True)
        self.resolve()
        self.position(attacker, 'HOL')
        self.reason(supporter, 'support')

    def test_disrupted_convoy_does_not_cut_support(self):
        _, attacker, supporter = self.support_cut_fixture(disrupted=True)
        self.resolve()
        self.position(attacker, 'HOL')
        self.reason(supporter, 'support')

    def test_valid_convoy_attack_cuts_support_even_when_bounced(self):
        army, attacker, supporter = self.support_cut_fixture()
        self.resolve()
        self.position(army, 'LON')
        self.position(attacker, 'NTH')
        self.reason(supporter, 'support_cut')

    def test_paradox_fails_convoy_independently_of_iteration_order(self):
        army, fleets = self.setup_route()
        attacker = self.unit('NTH', 'fleet', True)
        self.move(attacker, 'ENG')
        supporter = self.unit('BEL', 'fleet', True)
        self.support(supporter, attacker, 'ENG')
        units, orders = list(Unit.objects.filter(game=self.game)), list(Order.objects.filter(phase=self.phase))
        _resolve_convoys(units, orders)
        first = {o.pk: (o.result, o.result_reason) for o in orders}
        _resolve_convoys(list(reversed(units)), list(reversed(orders)))
        self.assertEqual(first, {o.pk: (o.result, o.result_reason) for o in orders})
        self.resolve()
        self.reason(army, 'convoy_paradox')
        self.position(army, 'LON')
        self.position(fleets[0], 'ENG', True)
        self.position(attacker, 'ENG')

    def test_hold_support_defends_convoy_fleet(self):
        army, fleets = self.setup_route()
        supporter = self.unit('BRE', 'fleet')
        self.post(supporter, 'support', supported_unit_id=fleets[0].pk)
        self.attack_channel(True)
        self.resolve()
        self.position(army, 'BEL')
        self.position(fleets[0], 'ENG')
        self.reason(supporter, 'support')

    def test_fall_capture_updates_supply_centers_and_winter(self):
        self.phase.season = 'fall'
        self.phase.save(update_fields=['season'])
        army, _ = self.setup_route()
        self.resolve()
        self.position(army, 'BEL')
        ownership = SupplyCenterOwnership.objects.get(game=self.game, province__code='BEL')
        self.assertEqual(ownership.owner_id, self.player.pk)
        self.assertEqual(GamePhase.objects.get(game=self.game, status='open').phase_type, 'adjustment')

    def test_replacement_clears_convoy_fields(self):
        army, fleets = self.setup_route()
        self.post(fleets[0], 'hold')
        order = Order.objects.get(unit=fleets[0], phase=self.phase)
        self.assertIsNone(order.convoyed_unit_id)
        self.assertIsNone(order.convoy_target_province_id)
        self.post(army, 'hold')
        self.assertFalse(Order.objects.get(unit=army, phase=self.phase).via_convoy)

    def test_cannot_order_enemy_convoy_fleet(self):
        army = self.unit('LON')
        fleet = self.unit('ENG', 'fleet', True)
        self.client.force_authenticate(self.user)
        response = self.client.post(f'/api/orders/games/{self.game.pk}/',
            dict(unit_id=fleet.pk, order_type='convoy', convoyed_unit_id=army.pk, convoy_target='BEL'))
        self.assertEqual(response.status_code, 400)

    def test_independent_convoy_survives_paradox(self):
        army, _ = self.setup_route()
        attacker = self.unit('NTH', 'fleet', True)
        self.move(attacker, 'ENG')
        self.support(self.unit('BEL', 'fleet', True), attacker, 'ENG')
        independent = self.unit('NAP')
        self.convoy(self.unit('ION', 'fleet'), independent, 'TUN')
        self.move(independent, 'TUN', True)
        self.resolve()
        self.reason(army, 'convoy_paradox')
        self.position(independent, 'TUN')

    def test_alternate_route_prevents_support_cut_paradox(self):
        army, _ = self.setup_route(seas=('ENG', 'NTH'))
        attacker = self.unit('MAO', 'fleet', True)
        self.move(attacker, 'ENG')
        self.support(self.unit('BEL', 'fleet', True), attacker, 'ENG')
        self.resolve()
        # The intact NTH route makes the attack on BEL independent of ENG.
        self.reason(army, 'defended')
        self.position(attacker, 'MAO')

    def test_convoy_to_multicoast_province_needs_no_coast(self):
        army, _ = self.setup_route('STP', ('NTH', 'NWG', 'BAR'))
        self.resolve()
        self.position(army, 'STP')
        self.assertIsNone(army.coast_id)

    def test_army_cannot_issue_convoy_and_foreign_game_reference_rejected(self):
        army = self.unit('LON')
        self.post(self.unit('BEL'), 'convoy', expected=400,
            convoyed_unit_id=army.pk, convoy_target='BRE')
        other_game = Game.objects.create(name='Other', creator=self.user)
        army.game = other_game
        army.owner = GamePlayer.objects.create(game=other_game, user=self.user, country='ENG')
        army.save(update_fields=['game', 'owner'])
        self.post(self.unit('ENG', 'fleet'), 'convoy', expected=400,
            convoyed_unit_id=army.pk, convoy_target='BEL')
