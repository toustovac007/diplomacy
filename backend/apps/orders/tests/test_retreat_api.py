from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.games.models import Game, GamePhase, GamePlayer, Unit
from apps.maps.models import Province
from apps.orders.models import Order
from apps.games.services.deadlines import process_expired_phases


class RetreatApiTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_map", verbosity=0)
        cls.user = get_user_model().objects.create_user(username="retreat_creator", email="creator@example.test")
        cls.game = Game.objects.create(
            name="Retreat API", creator=cls.user, status="active",
            turn_duration_minutes=1440,
        )
        cls.player = GamePlayer.objects.create(game=cls.game, user=cls.user, country="FRA")
        for sequence, phase_type, phase_status in [(1, "movement", "resolved"), (2, "retreat", "open")]:
            GamePhase.objects.create(
                game=cls.game, sequence=sequence, year=1901, season="spring",
                phase_type=phase_type, status=phase_status,
                deadline=timezone.now() + timedelta(days=1),
            )

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.url = f"/api/orders/games/{self.game.id}/retreats/"

    def unit(self, code, unit_type="army", dislodged=True):
        province = Province.objects.get(code=code)
        return Unit.objects.create(
            game=self.game, owner=self.player, unit_type=unit_type,
            province=province, is_dislodged=dislodged,
            dislodged_from=province if dislodged else None,
        )

    def test_game_exposes_dislodged_units_and_saved_decision_can_be_replaced(self):
        unit = self.unit("BUR")
        self.unit("MUN")  # A missing decision keeps replacement available.
        active = self.unit("PAR", dislodged=False)
        game = self.client.get(f"/api/games/{self.game.id}/").data
        flags = {item["id"]: item["is_dislodged"] for item in game["units"]}
        self.assertTrue(flags[unit.id])
        self.assertFalse(flags[active.id])
        response = self.client.post(self.url, {
            "unit_id": unit.id, "order_type": "retreat", "target": "BEL",
        })
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["phase_resolved"])
        saved = self.client.get(self.url).data[0]
        self.assertEqual(saved["saved_unit_id"], unit.id)
        self.assertEqual(saved["target_code"], "BEL")
        self.assertIsNone(saved["target_coast"])
        response = self.client.post(self.url, {"unit_id": unit.id, "order_type": "disband"})
        self.assertEqual(response.status_code, 201, response.data)
        saved = self.client.get(self.url).data
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["order_type"], "disband")
        self.assertIsNone(saved[0]["target_code"])

    def test_fleet_coast_is_returned_and_invalid_target_rejected(self):
        unit = self.unit("MAO", "fleet")
        self.unit("MUN")
        response = self.client.post(self.url, {
            "unit_id": unit.id, "order_type": "retreat", "target": "SPA",
            "target_coast_code": "nc",
        })
        self.assertEqual(response.status_code, 201, response.data)
        saved = self.client.get(self.url).data[0]
        self.assertEqual(saved["saved_unit_id"], unit.id)
        self.assertEqual(saved["target_coast"], "nc")
        response = self.client.post(self.url, {
            "unit_id": unit.id, "order_type": "retreat", "target": "MOS",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("target", response.data)

    def test_single_retreat_resolves_and_duplicate_post_cannot_resolve_again(self):
        unit = self.unit("BUR")
        payload = {"unit_id": unit.id, "order_type": "retreat", "target": "BEL"}
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["phase_resolved"])
        self.assertEqual(response.data["saved_unit_id"], unit.id)
        unit.refresh_from_db()
        self.assertEqual(unit.province.code, "BEL")
        self.assertFalse(unit.is_dislodged)
        self.assertEqual(GamePhase.objects.get(game=self.game, sequence=2).status, "resolved")
        self.assertEqual(GamePhase.objects.get(game=self.game, sequence=3).phase_type, "movement")
        self.assertEqual(self.client.post(self.url, payload).status_code, 404)
        self.assertEqual(GamePhase.objects.filter(game=self.game).count(), 3)

    def test_single_disband_returns_snapshot_despite_cascade_deletion(self):
        unit = self.unit("BUR")
        unit_id = unit.id
        response = self.client.post(self.url, {"unit_id": unit_id, "order_type": "disband"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["phase_resolved"])
        self.assertEqual(response.data["saved_unit_id"], unit_id)
        self.assertEqual(response.data["order_type"], "disband")
        self.assertFalse(Unit.objects.filter(pk=unit_id).exists())
        self.assertFalse(Order.objects.filter(pk=response.data["id"]).exists())

    def test_final_decision_by_other_player_resolves(self):
        first = self.unit("BUR")
        second = self.unit("MUN")
        other = get_user_model().objects.create_user(username="final_player", email="final@example.test")
        player = GamePlayer.objects.create(game=self.game, user=other, country="GER")
        second.owner = player
        second.save(update_fields=["owner"])
        response = self.client.post(self.url, {"unit_id": first.id, "order_type": "retreat", "target": "BEL"})
        self.assertFalse(response.data["phase_resolved"])
        self.assertEqual(GamePhase.objects.get(game=self.game, sequence=2).status, "open")
        self.assertTrue(Unit.objects.filter(pk=second.id, is_dislodged=True).exists())
        self.client.force_authenticate(other)
        response = self.client.post(self.url, {"unit_id": second.id, "order_type": "disband"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["phase_resolved"])
        self.assertEqual(GamePhase.objects.get(game=self.game, sequence=2).status, "resolved")

    def test_invalid_final_order_leaves_phase_open(self):
        unit = self.unit("BUR")
        response = self.client.post(self.url, {"unit_id": unit.id, "order_type": "retreat", "target": "MOS"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(GamePhase.objects.get(game=self.game, sequence=2).status, "open")
        self.assertFalse(Order.objects.filter(unit=unit).exists())

    def test_irrelevant_orders_do_not_complete_phase(self):
        first = self.unit("BUR")
        missing = self.unit("MUN")
        active = self.unit("PAR", dislodged=False)
        previous = GamePhase.objects.get(game=self.game, sequence=1)
        current = GamePhase.objects.get(game=self.game, sequence=2)
        Order.objects.create(phase=previous, unit=missing, order_type="disband", origin_province=missing.province)
        Order.objects.create(phase=current, unit=active, order_type="disband", origin_province=active.province)
        Order.objects.create(phase=current, unit=missing, order_type="hold", origin_province=missing.province)
        response = self.client.post(self.url, {"unit_id": first.id, "order_type": "retreat", "target": "BEL"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["phase_resolved"])
        current.refresh_from_db()
        self.assertEqual(current.status, "open")

    def test_deadline_still_disbands_missing_decision(self):
        first = self.unit("BUR")
        missing = self.unit("MUN")
        response = self.client.post(self.url, {"unit_id": first.id, "order_type": "retreat", "target": "BEL"})
        self.assertFalse(response.data["phase_resolved"])
        self.assertEqual(process_expired_phases(), [])
        phase = GamePhase.objects.get(game=self.game, sequence=2)
        phase.deadline = timezone.now() - timedelta(seconds=1)
        phase.save(update_fields=["deadline"])
        results = process_expired_phases()
        self.assertEqual(results[0]["status"], "resolved")
        self.assertFalse(Unit.objects.filter(pk=missing.id).exists())
        first.refresh_from_db()
        self.assertEqual(first.province.code, "BEL")

    def test_manual_resolve_remains_creator_only_and_defaults_to_disband(self):
        unit = self.unit("BUR")
        other = get_user_model().objects.create_user(username="retreat_other", email="other@example.test")
        GamePlayer.objects.create(game=self.game, user=other, country="GER")
        url = f"/api/orders/games/{self.game.id}/resolve-retreat/"
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_authenticate(self.user)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(Unit.objects.filter(pk=unit.pk).exists())
        game = self.client.get(f"/api/games/{self.game.id}/").data
        self.assertEqual(game["current_phase"]["phase_type"], "movement")
