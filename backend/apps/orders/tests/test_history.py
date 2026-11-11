from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.games.models import Game, GamePlayer, GamePhase, Unit, SupplyCenterOwnership
from apps.maps.models import Province, Coast
from apps.orders.models import Order, AdjustmentOrder
from apps.orders.services.adjudication import resolve_movement_phase, AdjudicationError
from apps.orders.services.retreat import resolve_retreat_phase
from apps.orders.services.adjustments import resolve_adjustment_phase


class ResolvedHistoryTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_map', stdout=StringIO())
        cls.user = get_user_model().objects.create_user(username='history', email='history@test.cz')
        cls.other_user = get_user_model().objects.create_user(username='other_history', email='other_history@test.cz')
        cls.game = Game.objects.create(name='History', creator=cls.user, status='active')
        cls.player = GamePlayer.objects.create(game=cls.game, user=cls.user, country='ENG')
        cls.other = GamePlayer.objects.create(game=cls.game, user=cls.other_user, country='FRA')
        cls.phase = GamePhase.objects.create(game=cls.game, sequence=1, year=1901,
            season='spring', phase_type='movement', deadline=timezone.now() + timedelta(days=1))

    def unit(self, code, kind='army', other=False):
        return Unit.objects.create(game=self.game, owner=self.other if other else self.player,
            unit_type=kind, province=Province.objects.get(code=code))

    def order(self, unit, kind='hold', **fields):
        return Order.objects.create(phase=self.phase, unit=unit, order_type=kind,
                                    origin_province=unit.province, **fields)

    def move(self, unit, code, **fields):
        return self.order(unit, 'move', target_province=Province.objects.get(code=code), **fields)

    def snapshot(self):
        self.phase.refresh_from_db()
        return self.phase.resolved_orders_snapshot

    def previous(self, user=None):
        self.client.force_authenticate(user or self.user)
        return self.client.get(f'/api/orders/games/{self.game.pk}/previous/')

    def test_movement_snapshot_all_countries_defaults_and_results(self):
        attacker = self.unit('PIC')
        defender = self.unit('BEL', other=True)
        self.move(attacker, 'BEL')
        resolve_movement_phase(self.phase)
        records = {row['saved_unit_id']: row for row in self.snapshot()}
        self.assertEqual(set(records), {attacker.pk, defender.pk})
        self.assertEqual({u['id']: u['province_code'] for u in self.phase.resolved_state_snapshot['units']}, {attacker.pk: 'PIC', defender.pk: 'BEL'})
        self.assertEqual(records[attacker.pk]['result'], 'failed')
        self.assertEqual(records[attacker.pk]['result_reason'], 'defended')
        self.assertEqual(records[defender.pk]['result'], 'success')
        self.assertTrue(records[defender.pk]['is_default'])
        response = self.previous(self.other_user)
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row['country'] for row in response.data['orders']}, {'ENG', 'FRA'})
        self.assertTrue(response.data['history_available'])

    def test_support_snapshot_survives_supported_and_issuing_unit_deletion(self):
        army = self.unit('BEL')
        fleet = self.unit('ENG', 'fleet')
        support = self.order(fleet, 'support', supported_unit=army,
            supported_origin_province=army.province, support_target_province=army.province)
        resolve_movement_phase(self.phase)
        before = self.snapshot()
        board = self.phase.resolved_state_snapshot
        army.province = Province.objects.get(code='HOL')
        army.save()
        army.delete()
        fleet.delete()
        self.assertFalse(Order.objects.filter(pk=support.pk).exists())
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.phase.resolved_state_snapshot, board)
        row = next(row for row in before if row['order_type'] == 'support')
        self.assertEqual((row['supported_unit_type'], row['supported_origin'], row['support_target_code']), ('army', 'BEL', 'BEL'))
        self.assertEqual(self.previous().data['orders'], before)

    def test_convoy_fields_preserved_without_units(self):
        army = self.unit('LON')
        fleet = self.unit('ENG', 'fleet', True)
        self.move(army, 'BEL', via_convoy=True)
        self.order(fleet, 'convoy', convoyed_unit=army, convoyed_origin_province=army.province,
                   convoy_target_province=Province.objects.get(code='BEL'))
        resolve_movement_phase(self.phase)
        army.delete()
        fleet.delete()
        rows = {row['order_type']: row for row in self.snapshot()}
        self.assertTrue(rows['move']['via_convoy'])
        self.assertEqual(rows['move']['origin'], 'LON')
        self.assertEqual(rows['convoy']['convoyed_origin'], 'LON')
        self.assertEqual(rows['convoy']['convoyed_unit_type'], 'army')
        self.assertEqual(rows['convoy']['convoy_target_code'], 'BEL')

    def retreat_phase(self, unit):
        self.phase.status = 'resolved'
        self.phase.resolved_orders_snapshot = []
        self.phase.save()
        self.phase = GamePhase.objects.create(game=self.game, sequence=2, year=1901,
            season='spring', phase_type='retreat', deadline=timezone.now() + timedelta(days=1))
        unit.is_dislodged = True
        unit.dislodged_from = unit.province
        unit.dislodged_by_origin = Province.objects.get(code='PIC')
        unit.save()

    def test_retreat_default_disband_survives_deletion(self):
        unit = self.unit('BEL')
        unit_id = unit.pk
        self.retreat_phase(unit)
        resolve_retreat_phase(self.phase)
        self.assertFalse(Unit.objects.filter(pk=unit_id).exists())
        row, = self.snapshot()
        self.assertEqual(self.phase.resolved_state_snapshot['units'], [])
        self.assertEqual((row['saved_unit_id'], row['origin'], row['order_type']), (unit_id, 'BEL', 'disband'))
        self.assertTrue(row['is_default'])
        self.assertEqual(self.previous().data['orders'], [row])

    def test_retreat_arrow_fields_survive_later_deletion(self):
        unit = self.unit('BEL')
        self.retreat_phase(unit)
        self.order(unit, 'retreat', target_province=Province.objects.get(code='HOL'))
        resolve_retreat_phase(self.phase)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.resolved_state_snapshot['units'][0]['province_code'], 'HOL')
        unit.delete()
        row, = self.snapshot()
        self.assertEqual((row['origin'], row['target_code'], row['result']), ('BEL', 'HOL', 'success'))

    def winter(self):
        self.phase.season = 'winter'
        self.phase.phase_type = 'adjustment'
        self.phase.save()

    def test_manual_adjustment_disband_snapshot(self):
        self.winter()
        unit = self.unit('BUR')
        unit_id = unit.pk
        AdjustmentOrder.objects.create(phase=self.phase, player=self.player, order_type='disband', unit=unit)
        resolve_adjustment_phase(self.phase)
        row, = self.snapshot()
        self.assertEqual(self.phase.resolved_state_snapshot['units'], [])
        self.assertEqual((row['saved_unit_id'], row['unit_type'], row['origin'], row['result_reason']),
                         (unit_id, 'army', 'BUR', 'disband'))
        self.assertFalse(Unit.objects.filter(pk=unit_id).exists())

    def test_automatic_adjustment_disband_snapshot(self):
        self.winter()
        unit = self.unit('ENG', 'fleet')
        resolve_adjustment_phase(self.phase, allow_automatic_disbands=True)
        row, = self.snapshot()
        self.assertEqual(row['unit_type'], 'fleet')
        self.assertEqual(row['result_reason'], 'automatic_disband')
        self.assertTrue(row['is_default'])
        self.assertFalse(Unit.objects.filter(pk=unit.pk).exists())

    def test_adjustment_build_snapshot_with_coast(self):
        self.winter()
        self.player.country = 'RUS'
        self.player.save()
        province = Province.objects.get(code='STP')
        coast = Coast.objects.get(province=province, code='nc')
        SupplyCenterOwnership.objects.create(game=self.game, owner=self.player, province=province)
        AdjustmentOrder.objects.create(phase=self.phase, player=self.player, order_type='build',
            unit_type='fleet', province=province, coast=coast)
        resolve_adjustment_phase(self.phase)
        row, = self.snapshot()
        built, = self.phase.resolved_state_snapshot['units']
        self.assertEqual((built['province_code'], built['coast'], built['unit_type']), ('STP', 'nc', 'fleet'))
        self.assertEqual((row['unit_type'], row['origin'], row['origin_coast_code'], row['result']),
                         ('fleet', 'STP', 'nc', 'success'))

    def test_open_orders_never_exposed_and_nonmember_denied(self):
        self.order(self.unit('LON'))
        self.order(self.unit('PAR', other=True))
        response = self.previous()
        self.assertEqual(response.data['orders'], [])
        self.assertIsNone(response.data['phase'])
        live = self.client.get(f'/api/orders/games/{self.game.pk}/')
        self.assertEqual(len(live.data), 1)
        outsider = get_user_model().objects.create_user(username='outsider', email='outsider@test.cz')
        self.assertEqual(self.previous(outsider).status_code, 404)
        self.game.status = 'waiting'
        self.game.save()
        self.assertEqual(self.previous().status_code, 404)

    def test_movement_to_retreat_sequence_and_no_open_order_leak(self):
        attacker = self.unit('PIC')
        defender = self.unit('BEL', other=True)
        supporter = self.unit('RUH')
        self.move(attacker, 'BEL')
        self.order(supporter, 'support', supported_unit=attacker,
            supported_origin_province=attacker.province, support_target_province=defender.province)
        resolve_movement_phase(self.phase)
        retreat = self.game.phases.get(status='open')
        self.assertEqual(retreat.phase_type, 'retreat')
        Order.objects.create(phase=retreat, unit=defender, order_type='retreat',
            origin_province=defender.province, target_province=Province.objects.get(code='HOL'))
        response = self.previous()
        self.assertEqual(response.data['phase']['id'], self.phase.pk)
        self.assertTrue(all(row['order_type'] != 'retreat' for row in response.data['orders']))

    def test_skipped_winter_selects_fall_even_with_empty_snapshot(self):
        self.phase.season = 'fall'
        self.phase.save()
        # With no countries' home ownership and no units, both deltas are zero.
        self.player.country = None
        self.player.save()
        self.other.country = None
        self.other.save()
        resolve_movement_phase(self.phase)
        self.assertEqual(self.game.phases.get(status='open').season, 'spring')
        response = self.previous()
        self.assertEqual(response.data['phase']['id'], self.phase.pk)
        self.assertTrue(response.data['history_available'])
        self.assertEqual(response.data['orders'], [])

    def test_finished_game_uses_highest_resolved_sequence(self):
        self.phase.status = 'resolved'
        self.phase.resolved_orders_snapshot = []
        self.phase.save()
        latest = GamePhase.objects.create(game=self.game, sequence=5, year=1903, season='fall',
            phase_type='movement', status='resolved', deadline=timezone.now(), resolved_orders_snapshot=[])
        self.game.status = 'finished'
        self.game.save()
        self.assertEqual(self.previous().data['phase']['id'], latest.pk)

    def test_legacy_phase_unavailable_does_not_fall_back_to_old_rows(self):
        self.order(self.unit('LON'))
        self.phase.status = 'resolved'
        self.phase.save()
        self.game.status = 'finished'
        self.game.save()
        self.assertEqual(self.previous().data, {'phase': None, 'orders': [], 'history_available': False})

    def test_rollback_and_repeated_resolution(self):
        self.unit('LON')
        with patch('apps.orders.services.adjudication.create_next_after_movement', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                resolve_movement_phase(self.phase)
        self.assertIsNone(self.snapshot())
        self.assertIsNone(self.phase.resolved_state_snapshot)
        self.assertEqual(self.phase.status, 'open')
        resolve_movement_phase(self.phase)
        before = self.snapshot()
        with self.assertRaises(AdjudicationError):
            resolve_movement_phase(self.phase)
        self.assertEqual(self.snapshot(), before)

    def test_retreat_rollback_restores_deleted_unit_and_snapshot(self):
        unit = self.unit('BEL')
        self.retreat_phase(unit)
        with patch('apps.orders.services.retreat.create_next_after_retreat', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                resolve_retreat_phase(self.phase)
        self.assertTrue(Unit.objects.filter(pk=unit.pk).exists())
        self.assertIsNone(self.snapshot())

    def test_adjustment_rollback_restores_deleted_unit_and_snapshot(self):
        self.winter()
        unit = self.unit('BUR')
        AdjustmentOrder.objects.create(phase=self.phase, player=self.player, order_type='disband', unit=unit)
        with patch('apps.orders.services.adjustments.create_next_after_adjustment', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                resolve_adjustment_phase(self.phase)
        self.assertTrue(Unit.objects.filter(pk=unit.pk).exists())
        self.assertIsNone(self.snapshot())

    def test_active_history_excludes_resolved_phases_after_current_sequence(self):
        self.phase.status = 'resolved'
        self.phase.resolved_orders_snapshot = []
        self.phase.save()
        GamePhase.objects.create(game=self.game, sequence=2, year=1901, season='fall',
            phase_type='movement', deadline=timezone.now())
        GamePhase.objects.create(game=self.game, sequence=9, year=1905, season='fall',
            phase_type='movement', status='resolved', deadline=timezone.now(), resolved_orders_snapshot=[{'private': True}])
        response = self.previous()
        self.assertEqual(response.data['phase']['id'], self.phase.pk)
        self.assertEqual(response.data['orders'], [])

    def board(self):
        self.phase.refresh_from_db()
        return self.phase.resolved_state_snapshot

    def history(self, phase=None, user=None):
        self.client.force_authenticate(user or self.user)
        suffix = f'{phase.pk}/' if phase else ''
        return self.client.get(f'/api/games/{self.game.pk}/history/{suffix}')

    def test_fall_board_after_capture_and_immutable_ownership(self):
        self.phase.season = 'fall'
        self.phase.save()
        army = self.unit('PIC')
        self.move(army, 'BEL')
        resolve_movement_phase(self.phase)
        board = self.board()
        self.assertEqual(board['units'][0]['province_code'], 'BEL')
        self.assertEqual(next(c['owner_country'] for c in board['supply_centers'] if c['province_code'] == 'BEL'), 'ENG')
        SupplyCenterOwnership.objects.filter(game=self.game, province__code='BEL').update(owner=self.other)
        army.delete()
        response = self.history(self.phase)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['state'], board)
        self.assertEqual(response.data['orders'], self.snapshot())

    def test_fall_dislodgement_before_retreat_then_after_retreat(self):
        self.phase.season = 'fall'
        self.phase.save()
        attacker = self.unit('PIC')
        defender = self.unit('BEL', other=True)
        supporter = self.unit('RUH')
        SupplyCenterOwnership.objects.create(game=self.game, province=defender.province, owner=self.other)
        self.move(attacker, 'BEL')
        self.order(supporter, 'support', supported_unit=attacker,
            supported_origin_province=attacker.province, support_target_province=defender.province)
        resolve_movement_phase(self.phase)
        board = self.board()
        occupants = {u['id']: u for u in board['units'] if u['province_code'] == 'BEL'}
        self.assertEqual(set(occupants), {attacker.pk, defender.pk})
        self.assertFalse(occupants[attacker.pk]['is_dislodged'])
        self.assertTrue(occupants[defender.pk]['is_dislodged'])
        self.assertEqual(occupants[defender.pk]['dislodged_from'], 'BEL')
        self.assertEqual(next(c['owner_country'] for c in board['supply_centers'] if c['province_code'] == 'BEL'), 'FRA')
        movement = self.phase
        self.phase = self.game.phases.get(status='open')
        self.order(defender, 'retreat', target_province=Province.objects.get(code='HOL'))
        resolve_retreat_phase(self.phase)
        final = self.board()
        self.assertEqual(next(c['owner_country'] for c in final['supply_centers'] if c['province_code'] == 'BEL'), 'ENG')
        self.assertEqual(next(u['province_code'] for u in final['units'] if u['id'] == defender.pk), 'HOL')
        self.assertEqual(self.history(movement).data['state'], board)

    def test_history_privacy_legacy_ordering_and_skipped_phases(self):
        self.phase.season = 'fall'
        self.phase.save()
        self.player.country = None
        self.player.save()
        self.other.country = None
        self.other.save()
        resolve_movement_phase(self.phase)
        current = self.game.phases.get(status='open')
        self.assertEqual((current.season, current.phase_type), ('spring', 'movement'))
        Order.objects.create(phase=current, unit=self.unit('LON'), order_type='hold', origin_province=Province.objects.get(code='LON'))
        listed = self.history().data['phases']
        self.assertEqual([p['id'] for p in listed], [self.phase.pk])
        self.assertTrue(listed[0]['state_available'])
        self.assertEqual(self.history(current).status_code, 404)
        outsider = get_user_model().objects.create_user(username='history_outside', email='history_outside@test.cz')
        self.assertEqual(self.history(user=outsider).status_code, 404)
        self.assertEqual(self.history(self.phase, outsider).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f'/api/games/{self.game.pk}/history/').status_code, 401)
        legacy = GamePhase.objects.create(game=self.game, sequence=0, year=1900, season='fall', phase_type='movement', status='resolved', deadline=timezone.now())
        self.assertEqual([p['sequence'] for p in self.history().data['phases']], [0, 1])
        detail = self.history(legacy).data
        self.assertFalse(detail['state_available'])
        self.assertFalse(detail['orders_available'])
        self.assertIsNone(detail['state'])
        self.assertIsNone(detail['orders'])
        foreign = Game.objects.create(name='Foreign', creator=self.user, status='active')
        foreign_phase = GamePhase.objects.create(game=foreign, sequence=1, year=1901, season='spring', phase_type='movement', status='resolved', deadline=timezone.now())
        self.assertEqual(self.history(foreign_phase).status_code, 404)

    def test_solo_final_board_and_history(self):
        self.phase.season = 'fall'
        self.phase.save()
        for province in Province.objects.filter(is_supply_center=True).order_by('pk')[:18]:
            SupplyCenterOwnership.objects.create(game=self.game, province=province, owner=self.player)
        resolve_movement_phase(self.phase)
        self.game.refresh_from_db()
        self.assertEqual(self.game.result_type, 'solo')
        self.assertFalse(self.game.phases.filter(status='open').exists())
        self.assertIsNotNone(self.board())
        self.assertEqual(self.history(self.phase).data['state'], self.board())
        self.assertEqual(len(self.history().data['phases']), 1)

    def test_each_detail_uses_its_own_snapshots_and_legacy_orders_remain(self):
        from apps.orders.services.snapshots import capture_resolved_phase_state
        army = self.unit('PIC')
        self.move(army, 'BEL')
        resolve_movement_phase(self.phase)
        first = self.phase
        first_board = self.board()
        first_orders = self.snapshot()
        self.phase = self.game.phases.get(status='open')
        army.refresh_from_db()
        self.move(army, 'HOL')
        resolve_movement_phase(self.phase)
        self.assertEqual(self.history(first).data['orders'], first_orders)
        self.assertEqual(self.history(first).data['state'], first_board)
        latest = self.history(self.phase).data
        self.assertEqual(latest['state']['units'][0]['province_code'], 'HOL')
        self.assertEqual(latest['orders'][0]['target_code'], 'HOL')
        # A repeated capture cannot replace an already recorded historical board.
        capture_resolved_phase_state(first)
        self.assertEqual(self.history(first).data['state'], first_board)
        first.resolved_state_snapshot = None
        first.save(update_fields=['resolved_state_snapshot'])
        legacy = self.history(first).data
        self.assertFalse(legacy['state_available'])
        self.assertTrue(legacy['orders_available'])
        self.assertEqual(legacy['orders'], first_orders)
        self.game.status = 'waiting'
        self.game.save()
        self.assertEqual(self.history().status_code, 404)

    def test_draw_cancelled_phase_has_no_snapshots_or_history(self):
        from apps.games.services.draws import propose, vote
        self.unit('LON')
        self.unit('PAR', other=True)
        resolve_movement_phase(self.phase)
        current = self.game.phases.get(status='open')
        Order.objects.create(phase=current, unit=self.game.units.first(), order_type='hold', origin_province=Province.objects.get(code='LON'))
        proposal, _ = propose(self.game.pk, self.user, [self.player.pk, self.other.pk])
        vote(self.game.pk, proposal.pk, self.other_user, 'accept')
        current.refresh_from_db()
        self.assertEqual(current.status, 'cancelled')
        self.assertIsNone(current.resolved_orders_snapshot)
        self.assertIsNone(current.resolved_state_snapshot)
        self.assertEqual(self.history(current).status_code, 404)
        self.assertEqual([p['id'] for p in self.history().data['phases']], [self.phase.pk])
        self.assertEqual(self.history(self.phase).data['state'], self.board())

    def test_rollback_after_board_capture_for_all_resolvers(self):
        from apps.orders.services.snapshots import capture_resolved_phase_state
        def capture_then_fail(phase):
            capture_resolved_phase_state(phase)
            raise RuntimeError('after snapshot')
        unit = self.unit('BEL')
        for module, resolve in [('adjudication', resolve_movement_phase), ('retreat', resolve_retreat_phase), ('adjustments', resolve_adjustment_phase)]:
            with self.subTest(resolver=module):
                if module == 'retreat':
                    self.retreat_phase(unit)
                elif module == 'adjustments':
                    unit.is_dislodged = False
                    unit.save()
                    self.winter()
                with patch(f'apps.orders.services.{module}.capture_resolved_phase_state', side_effect=capture_then_fail):
                    with self.assertRaises(RuntimeError):
                        resolve(self.phase, **({'allow_automatic_disbands': True} if module == 'adjustments' else {}))
                self.phase.refresh_from_db()
                self.assertEqual(self.phase.status, 'open')
                self.assertIsNone(self.phase.resolved_state_snapshot)
                self.assertIsNone(self.phase.resolved_orders_snapshot)
                self.assertTrue(Unit.objects.filter(pk=unit.pk).exists())
