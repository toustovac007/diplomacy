from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APITestCase

from apps.games.models import (
    Game,
    GamePlayer,
    GamePhase,
    SupplyCenterOwnership,
    Unit,
)

from apps.games.services.supply_centers import (
    initialize_supply_centers,
)

from apps.maps.models import Province


from apps.orders.services.adjustments import (
    AdjustmentError,
    can_build_unit,
    get_adjustment_delta,
    get_automatic_disband_units,
    get_buildable_home_centers,
    resolve_adjustment_phase,
)






User = get_user_model()


class AdjustmentApiTestCase(APITestCase):

    def setUp(self):
        call_command(
            "seed_map",
            verbosity=0,
        )

        self.user = User.objects.create_user(
            username="france_api",
            email="france_api@test.cz",
            password="test12345",
        )

        self.game = Game.objects.create(
            name="Adjustment API",
            creator=self.user,
            status="active",
            turn_duration_minutes=1440,
            max_players=7,
        )

        self.player = GamePlayer.objects.create(
            game=self.game,
            user=self.user,
            country="FRA",
        )

        initialize_supply_centers(
            self.game
        )

        self.phase = GamePhase.objects.create(
            game=self.game,
            sequence=1,
            year=1901,
            season="winter",
            phase_type="adjustment",
            status="open",
            deadline=(
                timezone.now()
                + timedelta(hours=24)
            ),
        )

        self.client.force_authenticate(
            user=self.user
        )

    def province(self, code):
        return Province.objects.get(
            code=code
        )

    def create_army(self, code):
        return Unit.objects.create(
            game=self.game,
            owner=self.player,
            unit_type="army",
            province=self.province(code),
        )

    def test_create_build_order(self):
        # FRA má standardně 3 SC a jen 2 jednotky.
        self.create_army("BUR")
        self.create_army("PIC")

        response = self.client.post(
            f"/api/orders/games/{self.game.id}/adjustments/",
            {
                "order_type": "build",
                "unit_type": "fleet",
                "province": "BRE",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response.data["order_type"],
            "build",
        )

        self.assertEqual(
            response.data["province_code"],
            "BRE",
        )

    def test_cannot_build_in_non_home_center(self):
        self.create_army("BUR")
        self.create_army("PIC")

        # Francie získá BEL.
        SupplyCenterOwnership.objects.filter(
            game=self.game,
            province__code="BEL",
        ).update(
            owner=self.player
        )

        response = self.client.post(
            f"/api/orders/games/{self.game.id}/adjustments/",
            {
                "order_type": "build",
                "unit_type": "army",
                "province": "BEL",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_create_disband_order(self):
        unit1 = self.create_army("PAR")
        self.create_army("MAR")
        self.create_army("BUR")
        self.create_army("PIC")

        # 3 centra, 4 jednotky = -1.
        response = self.client.post(
            f"/api/orders/games/{self.game.id}/adjustments/",
            {
                "order_type": "disband",
                "unit_id": unit1.id,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        self.assertEqual(
            response.data["order_type"],
            "disband",
        )

        self.assertEqual(
            response.data["saved_unit_id"],
            unit1.id,
        )

    def test_resolve_build_via_api_creates_unit_and_spring(self):
        self.create_army("BUR")
        self.create_army("PIC")

        build_response = self.client.post(
            f"/api/orders/games/{self.game.id}/adjustments/",
            {
                "order_type": "build",
                "unit_type": "fleet",
                "province": "BRE",
            },
            format="json",
        )

        self.assertEqual(
            build_response.status_code,
            status.HTTP_201_CREATED,
        )

        resolve_response = self.client.post(
            f"/api/orders/games/{self.game.id}/resolve-adjustment/",
            {},
            format="json",
        )

        self.assertEqual(
            resolve_response.status_code,
            status.HTTP_200_OK,
        )

        self.assertTrue(
            Unit.objects.filter(
                game=self.game,
                owner=self.player,
                province__code="BRE",
                unit_type="fleet",
            ).exists()
        )

        next_phase = GamePhase.objects.get(
            game=self.game,
            sequence=2,
        )

        self.assertEqual(
            next_phase.year,
            1902,
        )

        self.assertEqual(
            next_phase.season,
            "spring",
        )

        self.assertEqual(
            next_phase.phase_type,
            "movement",
        )
