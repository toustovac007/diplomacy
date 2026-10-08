from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from datetime import timedelta
from django.utils import timezone

from apps.games.models import (
    Game,
    GamePlayer,
    GamePhase,
    SupplyCenterOwnership,
    Unit,
)
from apps.orders.models import (
    AdjustmentOrder,
)
from apps.maps.models import Province

from apps.games.services.supply_centers import (
    initialize_supply_centers,
)

from apps.orders.services.adjustments import (
    AdjustmentError,
    can_build_unit,
    get_adjustment_delta,
    get_buildable_home_centers,
    resolve_adjustment_phase,
)

from apps.orders.services.adjustments import (
    AdjustmentError,
    can_build_unit,
    get_adjustment_delta,
    get_automatic_disband_units,
    get_buildable_home_centers,
    resolve_adjustment_phase,
)



User = get_user_model()


class AdjustmentTestCase(TestCase):
    def create_winter_phase(self):
        return GamePhase.objects.create(
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
    def setUp(self):
        call_command(
            "seed_map",
            verbosity=0,
        )

        self.user1 = User.objects.create_user(
            username="france",
            email="france@test.cz",
            password="test12345",
        )

        self.user2 = User.objects.create_user(
            username="germany",
            email="germany@test.cz",
            password="test12345",
        )

        self.game = Game.objects.create(
            name="Adjustment test",
            creator=self.user1,
            status="active",
            turn_duration_minutes=1440,
            max_players=7,
        )

        self.france = GamePlayer.objects.create(
            game=self.game,
            user=self.user1,
            country="FRA",
        )

        self.germany = GamePlayer.objects.create(
            game=self.game,
            user=self.user2,
            country="GER",
        )

        initialize_supply_centers(
            self.game
        )

    def province(self, code):
        return Province.objects.get(
            code=code
        )

    def create_army(
        self,
        player,
        province_code,
    ):
        return Unit.objects.create(
            game=self.game,
            owner=player,
            unit_type="army",
            province=self.province(
                province_code
            ),
        )

    def test_adjustment_delta_is_centers_minus_units(self):
        # Francie začíná se 3 domácími SC.
        self.create_army(
            self.france,
            "PAR",
        )

        self.create_army(
            self.france,
            "MAR",
        )

        self.create_army(
            self.france,
            "BUR",
        )

        self.assertEqual(
            get_adjustment_delta(
                self.france
            ),
            0,
        )

        # Francie získá BEL.
        SupplyCenterOwnership.objects.filter(
            game=self.game,
            province__code="BEL",
        ).update(
            owner=self.france
        )

        self.assertEqual(
            get_adjustment_delta(
                self.france
            ),
            1,
        )

    def test_buildable_home_centers_exclude_occupied(self):
        self.create_army(
            self.france,
            "PAR",
        )

        centers = get_buildable_home_centers(
            self.france
        )

        codes = set(
            centers.values_list(
                "code",
                flat=True,
            )
        )

        self.assertNotIn(
            "PAR",
            codes,
        )

        self.assertIn(
            "MAR",
            codes,
        )

        self.assertIn(
            "BRE",
            codes,
        )

    def test_build_rules(self):
        # Pro jistotu dáme Francii ještě BEL,
        # takže má dostatečnou BUILD kapacitu.
        SupplyCenterOwnership.objects.filter(
            game=self.game,
            province__code="BEL",
        ).update(
            owner=self.france
        )

        # Army v PAR je legální.
        self.assertTrue(
            can_build_unit(
                self.france,
                self.province("PAR"),
                "army",
            )
        )

        # Fleet v BRE je legální.
        self.assertTrue(
            can_build_unit(
                self.france,
                self.province("BRE"),
                "fleet",
            )
        )

        # Fleet v PAR není legální,
        # protože PAR je inland.
        self.assertFalse(
            can_build_unit(
                self.france,
                self.province("PAR"),
                "fleet",
            )
        )

        # BEL sice Francie vlastní,
        # ale není to francouzské HOME centrum.
        self.assertFalse(
            can_build_unit(
                self.france,
                self.province("BEL"),
                "army",
            )
        )

    def test_cannot_build_when_unit_count_matches_centers(self):
        self.create_army(
            self.france,
            "PAR",
        )

        self.create_army(
            self.france,
            "MAR",
        )

        self.create_army(
            self.france,
            "BUR",
        )

        self.assertEqual(
            get_adjustment_delta(
                self.france
            ),
            0,
        )

        # BRE je sice volné domácí centrum,
        # ale Francie má stejně jednotek jako center.
        self.assertFalse(
            can_build_unit(
                self.france,
                self.province("BRE"),
                "fleet",
            )
        )

    def test_resolve_build_creates_unit_and_next_spring(self):
        # Francie bude mít 4 centra.
        SupplyCenterOwnership.objects.filter(
            game=self.game,
            province__code="BEL",
        ).update(
            owner=self.france
        )

        # Ale pouze 3 jednotky.
        self.create_army(
            self.france,
            "BUR",
        )

        self.create_army(
            self.france,
            "PIC",
        )

        self.create_army(
            self.france,
            "GAS",
        )

        self.assertEqual(
            get_adjustment_delta(
                self.france
            ),
            1,
        )

        phase = self.create_winter_phase()

        AdjustmentOrder.objects.create(
            phase=phase,
            player=self.france,
            order_type="build",
            unit_type="fleet",
            province=self.province("BRE"),
        )

        resolve_adjustment_phase(
            phase
        )

        self.assertTrue(
            Unit.objects.filter(
                game=self.game,
                owner=self.france,
                province__code="BRE",
                unit_type="fleet",
            ).exists()
        )

        phase.refresh_from_db()

        self.assertEqual(
            phase.status,
            "resolved",
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

        self.assertEqual(
            next_phase.status,
            "open",
        )

    def test_resolve_disband_removes_unit(self):
        # Německo má standardně 3 centra.
        unit1 = self.create_army(
            self.germany,
            "BER",
        )

        unit2 = self.create_army(
            self.germany,
            "MUN",
        )

        unit3 = self.create_army(
            self.germany,
            "KIE",
        )

        extra_unit = self.create_army(
            self.germany,
            "RUH",
        )

        extra_unit_id = extra_unit.id

        self.assertEqual(
            get_adjustment_delta(
                self.germany
            ),
            -1,
        )

        phase = self.create_winter_phase()

        order = AdjustmentOrder.objects.create(
            phase=phase,
            player=self.germany,
            order_type="disband",
            unit=extra_unit,
        )

        resolve_adjustment_phase(
            phase
        )

        self.assertFalse(
            Unit.objects.filter(
                id=extra_unit_id
            ).exists()
        )

        order.refresh_from_db()

        self.assertEqual(
            order.result,
            "success",
        )

        self.assertEqual(
            order.result_reason,
            "disband",
        )

        # FK je SET_NULL, historický order zůstane.
        self.assertIsNone(
            order.unit
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

    def test_missing_required_disband_prevents_resolution(self):
        self.create_army(
            self.germany,
            "BER",
        )

        self.create_army(
            self.germany,
            "MUN",
        )

        self.create_army(
            self.germany,
            "KIE",
        )

        self.create_army(
            self.germany,
            "RUH",
        )

        self.assertEqual(
            get_adjustment_delta(
                self.germany
            ),
            -1,
        )

        phase = self.create_winter_phase()

        with self.assertRaises(
                AdjustmentError
        ):
            resolve_adjustment_phase(
                phase
            )

        phase.refresh_from_db()

        self.assertEqual(
            phase.status,
            "open",
        )

        self.assertFalse(
            GamePhase.objects.filter(
                game=self.game,
                sequence=2,
            ).exists()
        )

    def test_unused_build_can_be_waived(self):
        # Francie má 3 centra, ale jen 2 jednotky.
        self.create_army(
            self.france,
            "BUR",
        )

        self.create_army(
            self.france,
            "PIC",
        )

        self.assertEqual(
            get_adjustment_delta(
                self.france
            ),
            1,
        )

        phase = self.create_winter_phase()

        # Žádný BUILD order.
        resolve_adjustment_phase(
            phase
        )

        self.assertEqual(
            Unit.objects.filter(
                game=self.game,
                owner=self.france,
            ).count(),
            2,
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



    def test_automatic_disband_prefers_unit_outside_supply_center(self):
        par = self.create_army(
            self.france,
            "PAR",
        )

        bre = self.create_army(
            self.france,
            "BRE",
        )

        mar = self.create_army(
            self.france,
            "MAR",
        )

        gas = self.create_army(
            self.france,
            "GAS",
        )

        selected = get_automatic_disband_units(
            self.france,
            1,
        )

        self.assertEqual(
            len(selected),
            1,
        )

        self.assertEqual(
            selected[0].id,
            gas.id,
        )

    def test_automatic_disband_prefers_farthest_unit(self):
        self.create_army(
            self.france,
            "BUR",
        )

        self.create_army(
            self.france,
            "PIC",
        )

        self.create_army(
            self.france,
            "GAS",
        )

        tyr = self.create_army(
            self.france,
            "TYR",
        )

        selected = get_automatic_disband_units(
            self.france,
            1,
        )

        self.assertEqual(
            selected[0].id,
            tyr.id,
        )

    def test_automatic_disband_prefers_fleet_on_equal_distance(self):
        self.create_army(
            self.france,
            "BUR",
        )

        self.create_army(
            self.france,
            "PIC",
        )

        self.create_army(
            self.france,
            "GAS",
        )

        fleet = Unit.objects.create(
            game=self.game,
            owner=self.france,
            unit_type="fleet",
            province=self.province("ENG"),
        )

        selected = get_automatic_disband_units(
            self.france,
            1,
        )

        self.assertEqual(
            selected[0].id,
            fleet.id,
        )