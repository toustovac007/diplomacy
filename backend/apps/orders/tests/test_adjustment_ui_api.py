from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.games.models import Game, GamePhase, GamePlayer, SupplyCenterOwnership, Unit
from apps.games.services.supply_centers import initialize_supply_centers
from apps.maps.models import Province
from apps.orders.models import AdjustmentOrder


class AdjustmentUiApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_map", verbosity=0)
        cls.user = get_user_model().objects.create_user(username="winter", email="winter@example.test")
        cls.other = get_user_model().objects.create_user(username="other_winter", email="other_winter@example.test")
        cls.game = Game.objects.create(name="Winter UI", creator=cls.user, status="active")
        cls.player = GamePlayer.objects.create(game=cls.game, user=cls.user, country="FRA")
        cls.russia = GamePlayer.objects.create(game=cls.game, user=cls.other, country="RUS")
        initialize_supply_centers(cls.game)
        cls.phase = GamePhase.objects.create(
            game=cls.game, sequence=1, year=1901, season="winter", phase_type="adjustment",
            deadline=timezone.now() + timedelta(days=1),
        )

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.url = f"/api/orders/games/{self.game.id}/adjustments/"
        self.status_url = f"/api/orders/games/{self.game.id}/adjustment-status/"
        self.resolve_url = f"/api/orders/games/{self.game.id}/resolve-adjustment/"

    def army(self, code):
        return Unit.objects.create(game=self.game, owner=self.player, unit_type="army", province=Province.objects.get(code=code))

    def build(self, code, unit_type="army", **extra):
        return self.client.post(self.url, {"order_type": "build", "unit_type": unit_type, "province": code, **extra}, format="json")

    def test_status_and_build_get_cancel_resubmit(self):
        self.army("BUR")
        data = self.client.get(self.status_url).data
        self.assertEqual((data["supply_center_count"], data["unit_count"], data["delta"]), (3, 1, 2))
        self.assertEqual((data["build_count"], data["disband_count"], data["builds_remaining"]), (2, 0, 2))
        centers = {c["code"]: c for c in data["buildable_home_centers"]}
        self.assertTrue(centers["PAR"]["army_allowed"])
        self.assertFalse(centers["PAR"]["fleet_allowed"])
        self.assertTrue(centers["BRE"]["fleet_allowed"])
        response = self.build("BRE", "fleet")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.client.get(self.url).data[0]["province_code"], "BRE")
        data = self.client.get(self.status_url).data
        self.assertEqual(data["builds_remaining"], 1)
        self.assertNotIn("BRE", [c["code"] for c in data["buildable_home_centers"]])
        self.assertEqual(self.client.delete(f"{self.url}{response.data['id']}/").status_code, 204)
        self.assertEqual(self.build("BRE", "army").status_code, 201)

    def test_non_home_lost_and_occupied_centers_rejected(self):
        SupplyCenterOwnership.objects.filter(game=self.game, province__code="BEL").update(owner=self.player)
        SupplyCenterOwnership.objects.filter(game=self.game, province__code="PAR").update(owner=None)
        self.army("MAR")
        for code in ["BEL", "PAR", "MAR"]:
            with self.subTest(code=code):
                self.assertEqual(self.build(code).status_code, 400)
        codes = [c["code"] for c in self.client.get(self.status_url).data["buildable_home_centers"]]
        self.assertEqual(codes, ["BRE"])

    def test_stp_coasts_are_authoritative_and_saved(self):
        self.client.force_authenticate(self.other)
        center = next(c for c in self.client.get(self.status_url).data["buildable_home_centers"] if c["code"] == "STP")
        self.assertEqual(set(center["fleet_coast_codes"]), {"nc", "sc"})
        self.assertEqual(center["province_type"], "coastal")
        self.assertEqual(self.build("STP", "fleet", coast_code="ec").status_code, 400)
        self.assertEqual(self.build("STP", "fleet").status_code, 400)
        response = self.build("STP", "fleet", coast_code="nc")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.client.get(self.url).data[0]["saved_coast_code"], "nc")

    def test_disband_counts_saved_order_and_cancel(self):
        units = [self.army(code) for code in ["PAR", "MAR", "BUR", "PIC"]]
        data = self.client.get(self.status_url).data
        self.assertEqual((data["delta"], data["disband_count"], data["disbands_remaining"]), (-1, 1, 1))
        response = self.client.post(self.url, {"order_type": "disband", "unit_id": units[0].id})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.client.get(self.url).data[0]["saved_unit_id"], units[0].id)
        self.assertEqual(self.client.get(self.status_url).data["disbands_remaining"], 0)
        self.assertEqual(self.client.delete(f"{self.url}{response.data['id']}/").status_code, 204)
        self.assertEqual(self.client.get(self.status_url).data["disbands_remaining"], 1)
        self.assertEqual(self.client.post(self.resolve_url).status_code, 400)
        self.assertEqual(self.client.post(self.url, {"order_type": "disband", "unit_id": units[1].id}).status_code, 201)
        self.assertEqual(self.client.post(self.resolve_url).status_code, 200)
        self.assertFalse(Unit.objects.filter(pk=units[1].id).exists())

    def test_cannot_cancel_foreign_order_or_resolve_as_noncreator(self):
        response = self.build("PAR")
        self.assertEqual(response.status_code, 201)
        order_id = response.data["id"]
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.delete(f"{self.url}{order_id}/").status_code, 404)
        self.assertEqual(self.client.post(self.resolve_url).status_code, 403)
        self.assertTrue(AdjustmentOrder.objects.filter(pk=order_id).exists())

    def test_cannot_cancel_closed_or_expired_phase(self):
        order_id = self.build("PAR").data["id"]
        self.phase.deadline = timezone.now() - timedelta(seconds=1)
        self.phase.save(update_fields=["deadline"])
        self.assertEqual(self.client.delete(f"{self.url}{order_id}/").status_code, 404)
        self.phase.status = "resolved"
        self.phase.save(update_fields=["status"])
        self.assertEqual(self.client.delete(f"{self.url}{order_id}/").status_code, 404)
        self.assertEqual(self.client.get(self.status_url).status_code, 404)

    def test_zero_delta_stays_open(self):
        for code in ["PAR", "MAR", "BRE"]:
            self.army(code)
        for code in ["MOS", "WAR", "STP", "SEV"]:
            Unit.objects.create(game=self.game, owner=self.russia, unit_type="army", province=Province.objects.get(code=code))
        data = self.client.get(self.status_url).data
        self.assertEqual((data["delta"], data["build_count"], data["disband_count"]), (0, 0, 0))
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.status, "open")
