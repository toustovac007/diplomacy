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

    def test_game_detail_exposes_unit_province_types(self):
        self.army(self.france, "PAR")
        self.army(self.france, "BRE")
        Unit.objects.create(game=self.game, owner=self.france, unit_type="fleet",
                            province=Province.objects.get(code="ENG"))
        self.client.force_authenticate(self.france.user)
        response = self.client.get(f"/api/games/{self.game.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {unit["province_code"]: unit["province_type"] for unit in response.data["units"]},
            {"PAR": "inland", "BRE": "coastal", "ENG": "sea"},
        )
        from apps.games.serializer import UnitSerializer
        self.assertTrue(UnitSerializer().fields["province_type"].read_only)

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


class SoloVictoryTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_map", verbosity=0)
        cls.user = get_user_model().objects.create_user(username="solo", email="solo@example.test")
        cls.other_user = get_user_model().objects.create_user(username="opponent", email="opponent@example.test")
        cls.game = Game.objects.create(name="Solo", creator=cls.user, status="active")
        cls.player = GamePlayer.objects.create(game=cls.game, user=cls.user, country="FRA")
        cls.other = GamePlayer.objects.create(game=cls.game, user=cls.other_user, country="GER")
        initialize_supply_centers(cls.game)
        cls.phase = GamePhase.objects.create(game=cls.game, sequence=1, year=1901,
            season="fall", phase_type="movement", deadline=timezone.now() + timedelta(days=1))

    def centers(self, count):
        SupplyCenterOwnership.objects.filter(game=self.game).update(owner=None)
        centers = list(SupplyCenterOwnership.objects.filter(game=self.game)
            .exclude(province__code__in=["BEL", "HOL", "MUN"]).order_by("province__code")[:count])
        SupplyCenterOwnership.objects.filter(pk__in=[center.pk for center in centers]).update(owner=self.player)

    def army(self, code, owner=None):
        return Unit.objects.create(game=self.game, owner=owner or self.player,
                                   unit_type="army", province=Province.objects.get(code=code))

    def move(self, unit, target):
        return Order.objects.create(phase=self.phase, unit=unit, order_type="move",
            origin_province=unit.province, target_province=Province.objects.get(code=target))

    def support(self, unit, attacker, target):
        Order.objects.create(phase=self.phase, unit=unit, order_type="support",
            origin_province=unit.province, supported_unit=attacker,
            supported_origin_province=attacker.province,
            support_target_province=Province.objects.get(code=target))

    def capture(self, before=17):
        self.centers(before)
        army = self.army("PIC")
        self.move(army, "BEL")
        return army

    def assert_finished(self, count, phases=1):
        from apps.games.services.supply_centers import get_supply_center_count
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "finished")
        self.assertEqual(self.game.winner_id, self.player.pk)
        self.assertIsNotNone(self.game.finished_at)
        self.assertEqual(get_supply_center_count(self.player), count)
        self.assertFalse(self.game.phases.filter(status="open").exists())
        self.assertEqual(self.game.phases.count(), phases)
        self.assertFalse(self.game.phases.exclude(status="resolved").exists())

    def test_seventeen_centers_does_not_finish(self):
        self.centers(17)
        resolve_movement_phase(self.phase)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "active")
        self.assertIsNone(self.game.winner_id)
        self.assertIsNone(self.game.finished_at)
        self.assertEqual(self.game.phases.get(status="open").phase_type, "adjustment")

    def test_fall_capture_eighteenth_updates_ownership_before_victory(self):
        from apps.games.services.supply_centers import get_supply_center_count
        self.capture()
        self.assertEqual(get_supply_center_count(self.player), 17)
        resolve_movement_phase(self.phase)
        self.assert_finished(18)

    def test_more_than_eighteen_centers_wins(self):
        self.capture(before=18)
        resolve_movement_phase(self.phase)
        self.assert_finished(19)

    def test_spring_occupation_does_not_finish(self):
        self.capture()
        self.phase.season = "spring"
        self.phase.save(update_fields=["season"])
        resolve_movement_phase(self.phase)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "active")
        self.assertEqual(self.game.phases.get(status="open").season, "fall")
        self.assertFalse(SupplyCenterOwnership.objects.filter(game=self.game, province__code="BEL", owner=self.player).exists())

    def test_fall_waits_for_retreat_and_auto_completion_finishes(self):
        attacker = self.capture()
        defender = self.army("BEL", self.other)
        self.support(self.army("RUH"), attacker, "BEL")
        resolve_movement_phase(self.phase)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "active")
        self.assertIsNone(self.game.winner_id)
        self.assertEqual(self.game.phases.get(status="open").phase_type, "retreat")
        self.client.force_authenticate(self.other_user)
        response = self.client.post(f"/api/orders/games/{self.game.pk}/retreats/",
            {"unit_id": defender.pk, "order_type": "retreat", "target": "HOL"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["phase_resolved"])
        self.assert_finished(18, phases=2)

    def test_retreat_into_eighteenth_center_wins(self):
        self.centers(17)
        defender = self.army("BUR")
        attacker = self.army("MUN", self.other)
        self.move(attacker, "BUR")
        self.support(self.army("RUH", self.other), attacker, "BUR")
        resolve_movement_phase(self.phase)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "active")
        self.client.force_authenticate(self.user)
        response = self.client.post(f"/api/orders/games/{self.game.pk}/retreats/",
            {"unit_id": defender.pk, "order_type": "retreat", "target": "BEL"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assert_finished(18, phases=2)

    def test_finished_game_result_and_access_for_both_players(self):
        self.capture()
        resolve_movement_phase(self.phase)
        for user in [self.user, self.other_user]:
            self.client.force_authenticate(user)
            response = self.client.get(f"/api/games/{self.game.pk}/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["status"], "finished")
            self.assertEqual(response.data["winner"]["id"], self.player.pk)
            self.assertEqual(response.data["winner"]["username"], "solo")
            self.assertEqual(response.data["winner"]["country"], "FRA")
            self.assertEqual(response.data["winner"]["country_name"], "Francie")
            self.assertEqual(response.data["winner_supply_center_count"], 18)
            self.assertIsNotNone(response.data["finished_at"])
            self.assertIsNone(response.data["current_phase"])
            listing = self.client.get("/api/games/")
            rows = listing.data if isinstance(listing.data, list) else listing.data["results"]
            self.assertIn(self.game.pk, [row["id"] for row in rows])

    def test_finished_game_rejects_all_order_and_resolve_posts(self):
        army = self.capture()
        resolve_movement_phase(self.phase)
        self.client.force_authenticate(self.user)
        for suffix in ["", "retreats/", "adjustments/", "resolve/", "resolve-retreat/", "resolve-adjustment/"]:
            with self.subTest(endpoint=suffix):
                response = self.client.post(f"/api/orders/games/{self.game.pk}/{suffix}",
                    {"unit_id": army.pk, "order_type": "hold"})
                self.assertEqual(response.status_code, 404, response.data)
        self.assert_finished(18)

    def test_winner_must_belong_to_game(self):
        from django.core.exceptions import ValidationError
        other_game = Game.objects.create(name="Other", creator=self.user)
        self.game.winner = GamePlayer.objects.create(game=other_game, user=self.user, country="FRA")
        with self.assertRaises(ValidationError):
            self.game.save()

    def test_finished_game_has_no_deadline_work_and_result_is_read_only(self):
        from apps.games.services.deadlines import process_expired_phases
        from apps.games.serializer import GameSerializer
        self.capture()
        resolve_movement_phase(self.phase)
        self.assertEqual(process_expired_phases(now=timezone.now() + timedelta(days=365)), [])
        serializer = GameSerializer()
        for field in ["winner", "finished_at", "winner_supply_center_count"]:
            self.assertTrue(serializer.fields[field].read_only)
        self.assert_finished(18)

    def test_victory_failure_rolls_back_entire_resolution(self):
        army = self.capture()
        with patch("apps.games.services.phase_manager.finish_game", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                resolve_movement_phase(self.phase)
        self.phase.refresh_from_db()
        army.refresh_from_db()
        self.assertEqual(self.phase.status, "open")
        self.assertEqual(army.province.code, "PIC")
        self.assertFalse(SupplyCenterOwnership.objects.filter(game=self.game, province__code="BEL", owner=self.player).exists())
