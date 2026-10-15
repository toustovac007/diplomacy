from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.games.models import Game, GamePhase, GamePlayer, SupplyCenterOwnership, Unit
from apps.games.services.supply_centers import (
    get_adjustment_delta, initialize_supply_centers, update_supply_center_ownership,
)
from apps.maps.models import Province
from apps.orders.models import Order
from apps.orders.services.adjudication import resolve_movement_phase


class FallTransitionTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_map", verbosity=0)
        users = [get_user_model().objects.create_user(username=name, email=f"{name}@example.test")
                 for name in ("fall_france", "fall_germany")]
        cls.game = Game.objects.create(name="Fall transition", creator=users[0], status="active", turn_duration_minutes=120)
        cls.france = GamePlayer.objects.create(game=cls.game, user=users[0], country="FRA")
        cls.germany = GamePlayer.objects.create(game=cls.game, user=users[1], country="GER")
        initialize_supply_centers(cls.game)
        cls.phase = GamePhase.objects.create(
            game=cls.game, sequence=7, year=1903, season="fall", phase_type="movement",
            deadline=timezone.now() + timedelta(hours=2),
        )

    def army(self, player, code):
        return Unit.objects.create(game=self.game, owner=player, unit_type="army", province=Province.objects.get(code=code))

    def balanced_units(self):
        for player, codes in [(self.france, ["PAR", "MAR", "BRE"]), (self.germany, ["BER", "MUN", "KIE"])]:
            for code in codes:
                self.army(player, code)

    def assert_spring(self, sequence, now):
        phase = GamePhase.objects.get(game=self.game, status="open")
        self.assertEqual((phase.sequence, phase.year, phase.season, phase.phase_type), (sequence, 1904, "spring", "movement"))
        self.assertEqual(phase.deadline, now + timedelta(minutes=self.game.turn_duration_minutes))
        self.assertFalse(GamePhase.objects.filter(game=self.game, season="winter").exists())

    def test_balanced_fall_without_retreat_skips_winter_for_all_players(self):
        self.balanced_units()
        now = timezone.now()
        with patch("apps.games.services.phase_manager.update_supply_center_ownership", wraps=update_supply_center_ownership) as update:
            with patch("apps.games.services.phase_manager.timezone.now", return_value=now):
                resolve_movement_phase(self.phase)
            update.assert_called_once_with(self.game)
        self.assert_spring(8, now)

    def test_fall_retreat_completion_skips_balanced_winter(self):
        attacker = self.army(self.france, "BUR")
        supporter = self.army(self.france, "RUH")
        self.army(self.france, "PAR")
        self.army(self.france, "MAR")
        defender = self.army(self.germany, "MUN")
        self.army(self.germany, "BER")
        self.army(self.germany, "KIE")
        Order.objects.create(phase=self.phase, unit=attacker, order_type="move", origin_province=attacker.province, target_province=defender.province)
        Order.objects.create(
            phase=self.phase, unit=supporter, order_type="support", origin_province=supporter.province,
            supported_unit=attacker, supported_origin_province=attacker.province,
            support_target_province=defender.province,
        )
        now = timezone.now()
        with patch("apps.games.services.phase_manager.update_supply_center_ownership", wraps=update_supply_center_ownership) as update:
            resolve_movement_phase(self.phase)
            update.assert_not_called()
            self.assertEqual(GamePhase.objects.get(game=self.game, status="open").phase_type, "retreat")
            defender.refresh_from_db()
            self.assertTrue(defender.is_dislodged)
            self.client.force_authenticate(self.germany.user)
            with patch("apps.games.services.phase_manager.timezone.now", return_value=now):
                response = self.client.post(f"/api/orders/games/{self.game.id}/retreats/", {"unit_id": defender.id, "order_type": "disband"})
            self.assertEqual(response.status_code, 201, response.data)
            self.assertTrue(response.data["phase_resolved"])
            update.assert_called_once_with(self.game)
        self.assertEqual(get_adjustment_delta(self.france), 0)
        self.assertEqual(get_adjustment_delta(self.germany), 0)
        self.assert_spring(9, now)

    def test_one_build_still_requires_winter(self):
        self.balanced_units()
        Unit.objects.get(game=self.game, province__code="MAR").delete()
        resolve_movement_phase(self.phase)
        self.assertEqual(get_adjustment_delta(self.france), 1)
        self.assert_winter()

    def test_one_disband_still_requires_winter(self):
        self.balanced_units()
        self.army(self.france, "BUR")
        resolve_movement_phase(self.phase)
        self.assertEqual(get_adjustment_delta(self.france), -1)
        self.assert_winter()

    def assert_winter(self):
        phase = GamePhase.objects.get(game=self.game, status="open")
        self.assertEqual((phase.sequence, phase.year, phase.season, phase.phase_type), (8, 1903, "winter", "adjustment"))

    def test_capture_is_counted_before_deciding_to_create_winter(self):
        self.balanced_units()
        unit = Unit.objects.get(game=self.game, province__code="BRE")
        unit.province = Province.objects.get(code="PIC")
        unit.save(update_fields=["province"])
        self.assertEqual(get_adjustment_delta(self.france), 0)
        Order.objects.create(phase=self.phase, unit=unit, order_type="move", origin_province=unit.province, target_province=Province.objects.get(code="BEL"))
        resolve_movement_phase(self.phase)
        self.assertEqual(SupplyCenterOwnership.objects.get(game=self.game, province__code="BEL").owner_id, self.france.id)
        self.assertEqual(get_adjustment_delta(self.france), 1)
        self.assert_winter()

    def test_eliminated_player_with_zero_centers_and_units_does_not_force_winter(self):
        self.balanced_units()
        Unit.objects.filter(owner=self.germany).delete()
        SupplyCenterOwnership.objects.filter(owner=self.germany).update(owner=None)
        now = timezone.now()
        with patch("apps.games.services.phase_manager.timezone.now", return_value=now):
            resolve_movement_phase(self.phase)
        self.assert_spring(8, now)
