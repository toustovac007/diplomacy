"""Missing cross-account order privacy cases; other IDOR suites stay authoritative."""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.games.models import Game, GamePhase, GamePlayer, Unit
from apps.maps.models import Province
from apps.orders.models import Order, AdjustmentOrder


class OrderSecurityTests(APITestCase):
    def test_open_order_privacy_and_foreign_unit_writes_in_all_phases(self):
        user = get_user_model().objects.create_user(username="order_a", email="a@security.test")
        other = get_user_model().objects.create_user(username="order_b", email="b@security.test")
        outsider = get_user_model().objects.create_user(username="outsider", email="out@security.test")
        province = Province.objects.create(code="PAR", name="Paris", province_type="inland", is_supply_center=True)
        for phase_type, endpoint in (("movement", ""), ("retreat", "retreats/"), ("adjustment", "adjustments/")):
            with self.subTest(phase_type=phase_type):
                game = Game.objects.create(name="Private", creator=user, status="active", is_public=False)
                player = GamePlayer.objects.create(game=game, user=user, country="FRA")
                owner = GamePlayer.objects.create(game=game, user=other, country="ENG")
                phase = GamePhase.objects.create(game=game, sequence=1, year=1901,
                    season="winter" if phase_type == "adjustment" else "spring", phase_type=phase_type,
                    deadline=timezone.now() + timedelta(days=1))
                unit = Unit.objects.create(game=game, owner=owner, province=province, unit_type="army",
                    is_dislodged=phase_type == "retreat", dislodged_from=province if phase_type == "retreat" else None)
                if phase_type == "adjustment":
                    AdjustmentOrder.objects.create(phase=phase, player=owner, unit=unit, order_type="disband")
                else:
                    Order.objects.create(phase=phase, unit=unit, origin_province=province,
                                         order_type="disband" if phase_type == "retreat" else "hold")
                url = f"/api/orders/games/{game.pk}/{endpoint}"
                self.client.force_authenticate(user)
                self.assertEqual(self.client.get(url).data, [])
                response = self.client.post(url, {"unit_id": unit.pk,
                    "order_type": "hold" if phase_type == "movement" else "disband"}, format="json")
                self.assertEqual(response.status_code, 400)
                self.client.force_authenticate(other)
                self.assertEqual(len(self.client.get(url).data), 1)
                self.client.force_authenticate(outsider)
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.get(f"/api/games/{game.pk}/").status_code, 404)
                self.assertTrue(GamePlayer.objects.filter(pk=player.pk).exists())
