from datetime import timedelta

#import volání mapy ze seedu
from django.core.management import call_command


from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.games.models import (
    Game,
    GamePlayer,
    GamePhase,
    Unit,
)
from apps.maps.models import Province
from apps.orders.models import Order
from apps.orders.services.adjudication import (
    resolve_movement_phase,
)
from apps.orders.services.retreat import (
    can_unit_retreat,
    resolve_retreat_phase,
)
from apps.games.models import (
    Game,
    GamePlayer,
    GamePhase,
    Unit,
    SupplyCenterOwnership,
)
from apps.games.services.supply_centers import (
    initialize_supply_centers,
)



User = get_user_model()


class AdjudicationTestCase(TestCase):

    def setUp(self):
        call_command(
            "seed_map",
            verbosity=0,
        )
        self.user1 = User.objects.create_user(
            username="player1",
            email="player1@test.cz",
            password="testpassword123",
        )

        self.user2 = User.objects.create_user(
            username="player2",
            email="player2@test.cz",
            password="testpassword123",
        )

        self.game = Game.objects.create(
            name="Test adjudikace",
            creator=self.user1,
            status="active",
            turn_duration_minutes=1440,
            max_players=7,
        )

        self.player1 = GamePlayer.objects.create(
            game=self.game,
            user=self.user1,
            country="FRA",
        )

        self.player2 = GamePlayer.objects.create(
            game=self.game,
            user=self.user2,
            country="GER",
        )

        self.phase = GamePhase.objects.create(
            game=self.game,
            sequence=1,
            year=1901,
            season="spring",
            phase_type="movement",
            status="open",
            deadline=timezone.now() + timedelta(hours=24),
        )

    def province(self, code):
        return Province.objects.get(code=code)

    def create_army(self, player, province_code):
        return Unit.objects.create(
            game=self.game,
            owner=player,
            unit_type="army",
            province=self.province(province_code),
        )

    def test_move_to_empty_province_succeeds(self):
        army = self.create_army(
            self.player1,
            "PAR",
        )

        Order.objects.create(
            phase=self.phase,
            unit=army,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        resolve_movement_phase(self.phase)

        army.refresh_from_db()

        self.assertEqual(
            army.province.code,
            "BUR",
        )

        order = Order.objects.get(
            phase=self.phase,
            unit=army,
        )

        self.assertEqual(
            order.result,
            "success",
        )

    def test_move_against_hold_fails(self):
        attacker = self.create_army(
            self.player1,
            "PAR",
        )

        defender = self.create_army(
            self.player2,
            "BUR",
        )

        Order.objects.create(
            phase=self.phase,
            unit=attacker,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=defender,
            order_type="hold",
            origin_province=self.province("BUR"),
        )

        resolve_movement_phase(self.phase)

        attacker.refresh_from_db()
        defender.refresh_from_db()

        self.assertEqual(
            attacker.province.code,
            "PAR",
        )

        self.assertEqual(
            defender.province.code,
            "BUR",
        )

    def test_equal_moves_to_same_province_standoff(self):
        army1 = self.create_army(
            self.player1,
            "PAR",
        )

        army2 = self.create_army(
            self.player2,
            "MUN",
        )

        Order.objects.create(
            phase=self.phase,
            unit=army1,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=army2,
            order_type="move",
            origin_province=self.province("MUN"),
            target_province=self.province("BUR"),
        )

        resolve_movement_phase(self.phase)

        army1.refresh_from_db()
        army2.refresh_from_db()

        self.assertEqual(
            army1.province.code,
            "PAR",
        )

        self.assertEqual(
            army2.province.code,
            "MUN",
        )

    def test_missing_order_becomes_default_hold(self):
        army = self.create_army(
            self.player1,
            "PAR",
        )

        resolve_movement_phase(self.phase)

        army.refresh_from_db()

        self.assertEqual(
            army.province.code,
            "PAR",
        )

        order = Order.objects.get(
            phase=self.phase,
            unit=army,
        )

        self.assertEqual(
            order.order_type,
            "hold",
        )

        self.assertTrue(
            order.is_default,
        )

        self.assertEqual(
            order.result,
            "success",
        )

    def test_supported_move_dislodges_holder(self):
        attacker = self.create_army(
            self.player1,
            "PAR",
        )

        supporter = self.create_army(
            self.player1,
            "PIC",
        )

        defender = self.create_army(
            self.player2,
            "BUR",
        )

        Order.objects.create(
            phase=self.phase,
            unit=attacker,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=supporter,
            order_type="support",
            origin_province=self.province("PIC"),
            supported_unit=attacker,
            supported_origin_province=self.province("PAR"),
            support_target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=defender,
            order_type="hold",
            origin_province=self.province("BUR"),
        )

        resolve_movement_phase(self.phase)

        attacker.refresh_from_db()
        defender.refresh_from_db()

        self.assertEqual(
            attacker.province.code,
            "BUR",
        )

        self.assertTrue(
            defender.is_dislodged,
        )

        self.assertEqual(
            defender.dislodged_from.code,
            "BUR",
        )

        self.assertEqual(
            defender.dislodged_by_origin.code,
            "PAR",
        )

    def test_support_hold_prevents_equal_attack(self):
            attacker = self.create_army(
                self.player1,
                "PAR",
            )

            attacker_support = self.create_army(
                self.player1,
                "PIC",
            )

            defender = self.create_army(
                self.player2,
                "BUR",
            )

            defender_support = self.create_army(
                self.player2,
                "MUN",
            )

            Order.objects.create(
                phase=self.phase,
                unit=attacker,
                order_type="move",
                origin_province=self.province("PAR"),
                target_province=self.province("BUR"),
            )

            Order.objects.create(
                phase=self.phase,
                unit=attacker_support,
                order_type="support",
                origin_province=self.province("PIC"),
                supported_unit=attacker,
                supported_origin_province=self.province("PAR"),
                support_target_province=self.province("BUR"),
            )

            Order.objects.create(
                phase=self.phase,
                unit=defender,
                order_type="hold",
                origin_province=self.province("BUR"),
            )

            Order.objects.create(
                phase=self.phase,
                unit=defender_support,
                order_type="support",
                origin_province=self.province("MUN"),
                supported_unit=defender,
                supported_origin_province=self.province("BUR"),
                support_target_province=self.province("BUR"),
            )

            resolve_movement_phase(self.phase)

            attacker.refresh_from_db()
            defender.refresh_from_db()

            self.assertEqual(
                attacker.province.code,
                "PAR",
            )

            self.assertEqual(
                defender.province.code,
                "BUR",
            )

            self.assertFalse(
                defender.is_dislodged,
            )

    def check_hold_support_defense(self, defender_order_type):
        defender = self.create_army(self.player1, "BEL")
        holder = self.create_army(self.player1, "HOL")
        supporter = Unit.objects.create(
            game=self.game, owner=self.player1, unit_type="fleet",
            province=self.province("ENG"),
        )
        attacker = self.create_army(self.player2, "PIC")
        attack_support = self.create_army(self.player2, "BUR")

        def order(unit, order_type, **fields):
            return Order.objects.create(
                phase=self.phase, unit=unit, order_type=order_type,
                origin_province=unit.province, **fields,
            )

        fields = {}
        if defender_order_type == "support":
            fields = dict(supported_unit=holder,
                          supported_origin_province=holder.province,
                          support_target_province=holder.province)
        elif defender_order_type == "move":
            # HOL is occupied by a friendly holder, so the MOVE cannot leave.
            fields = dict(target_province=holder.province)
        order(defender, defender_order_type, **fields)
        hold_support = order(
            supporter, "support", supported_unit=defender,
            supported_origin_province=defender.province,
            support_target_province=defender.province,
        )
        order(attacker, "move", target_province=defender.province)
        order(attack_support, "support", supported_unit=attacker,
              supported_origin_province=attacker.province,
              support_target_province=defender.province)

        resolve_movement_phase(self.phase)
        defender.refresh_from_db()
        attacker.refresh_from_db()
        hold_support.refresh_from_db()
        if defender_order_type == "move":
            self.assertEqual(hold_support.result_reason, "void_support")
            self.assertEqual(hold_support.result, "failed")
            self.assertTrue(defender.is_dislodged)
            self.assertEqual(attacker.province.code, "BEL")
        else:
            self.assertEqual(hold_support.result_reason, "support")
            self.assertEqual(hold_support.result, "success")
            # Strength-two attack must bounce against strength-two defense.
            self.assertFalse(defender.is_dislodged)
            self.assertEqual(attacker.province.code, "PIC")
            self.assertEqual(defender.province.code, "BEL")

    def test_hold_order_receives_hold_support_defense(self):
        self.check_hold_support_defense("hold")

    def test_support_order_receives_hold_support_defense(self):
        self.check_hold_support_defense("support")

    def test_blocked_move_cannot_receive_hold_support_defense(self):
        self.check_hold_support_defense("move")

    def test_attack_cuts_support(self):
            attacker = self.create_army(
                self.player1,
                "PAR",
            )

            supporter = self.create_army(
                self.player1,
                "PIC",
            )

            defender = self.create_army(
                self.player2,
                "BUR",
            )

            cutter = self.create_army(
                self.player2,
                "BEL",
            )

            Order.objects.create(
                phase=self.phase,
                unit=attacker,
                order_type="move",
                origin_province=self.province("PAR"),
                target_province=self.province("BUR"),
            )

            support_order = Order.objects.create(
                phase=self.phase,
                unit=supporter,
                order_type="support",
                origin_province=self.province("PIC"),
                supported_unit=attacker,
                supported_origin_province=self.province("PAR"),
                support_target_province=self.province("BUR"),
            )

            Order.objects.create(
                phase=self.phase,
                unit=defender,
                order_type="hold",
                origin_province=self.province("BUR"),
            )

            Order.objects.create(
                phase=self.phase,
                unit=cutter,
                order_type="move",
                origin_province=self.province("BEL"),
                target_province=self.province("PIC"),
            )

            resolve_movement_phase(self.phase)

            attacker.refresh_from_db()
            defender.refresh_from_db()
            supporter.refresh_from_db()
            cutter.refresh_from_db()
            support_order.refresh_from_db()

            self.assertEqual(
                attacker.province.code,
                "PAR",
            )

            self.assertEqual(
                defender.province.code,
                "BUR",
            )

            self.assertEqual(
                supporter.province.code,
                "PIC",
            )

            self.assertEqual(
                cutter.province.code,
                "BEL",
            )

            self.assertEqual(
                support_order.result,
                "failed",
            )

            self.assertEqual(
                support_order.result_reason,
                "support_cut",
            )

    def test_dislodgement_creates_retreat_phase(self):
        attacker = self.create_army(
            self.player1,
            "PAR",
        )

        supporter = self.create_army(
            self.player1,
            "PIC",
        )

        defender = self.create_army(
            self.player2,
            "BUR",
        )

        Order.objects.create(
            phase=self.phase,
            unit=attacker,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=supporter,
            order_type="support",
            origin_province=self.province("PIC"),
            supported_unit=attacker,
            supported_origin_province=self.province("PAR"),
            support_target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=defender,
            order_type="hold",
            origin_province=self.province("BUR"),
        )

        resolve_movement_phase(
            self.phase
        )

        retreat_phase = (
            GamePhase.objects.get(
                game=self.game,
                sequence=2,
            )
        )

        self.assertEqual(
            retreat_phase.phase_type,
            "retreat",
        )

        self.assertEqual(
            retreat_phase.season,
            "spring",
        )

        self.assertEqual(
            retreat_phase.year,
            1901,
        )

        self.assertEqual(
            retreat_phase.status,
            "open",
        )

    def test_no_dislodgement_creates_fall_movement(self):
        army = self.create_army(
            self.player1,
            "PAR",
        )

        Order.objects.create(
            phase=self.phase,
            unit=army,
            order_type="hold",
            origin_province=self.province("PAR"),
        )

        resolve_movement_phase(
            self.phase
        )

        next_phase = GamePhase.objects.get(
            game=self.game,
            sequence=2,
        )

        self.assertEqual(
            next_phase.phase_type,
            "movement",
        )

        self.assertEqual(
            next_phase.season,
            "fall",
        )

        self.assertEqual(
            next_phase.year,
            1901,
        )

    def test_successful_retreat(self):
        attacker = self.create_army(
            self.player1,
            "PAR",
        )

        supporter = self.create_army(
            self.player1,
            "PIC",
        )

        defender = self.create_army(
            self.player2,
            "BUR",
        )

        Order.objects.create(
            phase=self.phase,
            unit=attacker,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=supporter,
            order_type="support",
            origin_province=self.province("PIC"),
            supported_unit=attacker,
            supported_origin_province=self.province("PAR"),
            support_target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=defender,
            order_type="hold",
            origin_province=self.province("BUR"),
        )

        resolve_movement_phase(
            self.phase
        )

        defender.refresh_from_db()

        self.assertTrue(
            defender.is_dislodged
        )

        retreat_phase = GamePhase.objects.get(
            game=self.game,
            sequence=2,
        )

        Order.objects.create(
            phase=retreat_phase,
            unit=defender,
            order_type="retreat",
            origin_province=self.province("BUR"),
            target_province=self.province("MUN"),
        )

        resolve_retreat_phase(
            retreat_phase
        )

        defender.refresh_from_db()

        self.assertFalse(
            defender.is_dislodged
        )

        self.assertEqual(
            defender.province.code,
            "MUN",
        )

        next_phase = GamePhase.objects.get(
            game=self.game,
            sequence=3,
        )

        self.assertEqual(
            next_phase.phase_type,
            "movement",
        )

        self.assertEqual(
            next_phase.season,
            "fall",
        )

        self.assertEqual(
            next_phase.year,
            1901,
        )

    def test_missing_retreat_order_causes_disband(self):
        attacker = self.create_army(
            self.player1,
            "PAR",
        )

        supporter = self.create_army(
            self.player1,
            "PIC",
        )

        defender = self.create_army(
            self.player2,
            "BUR",
        )

        defender_id = defender.id

        Order.objects.create(
            phase=self.phase,
            unit=attacker,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=supporter,
            order_type="support",
            origin_province=self.province("PIC"),
            supported_unit=attacker,
            supported_origin_province=self.province("PAR"),
            support_target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=defender,
            order_type="hold",
            origin_province=self.province("BUR"),
        )

        resolve_movement_phase(
            self.phase
        )

        retreat_phase = GamePhase.objects.get(
            game=self.game,
            sequence=2,
        )

        # Defenderovi schválně nedáme žádný rozkaz.
        resolve_retreat_phase(
            retreat_phase
        )

        self.assertFalse(
            Unit.objects.filter(
                id=defender_id
            ).exists()
        )

        next_phase = GamePhase.objects.get(
            game=self.game,
            sequence=3,
        )

        self.assertEqual(
            next_phase.season,
            "fall",
        )

        self.assertEqual(
            next_phase.phase_type,
            "movement",
        )

        self.assertEqual(
            next_phase.year,
            1901,
        )

        self.assertEqual(
            next_phase.status,
            "open",
        )

    def test_two_retreats_to_same_province_both_disband(self):
        # První útok: PAR -> BUR s podporou PIC
        attacker1 = self.create_army(
            self.player1,
            "PAR",
        )

        supporter1 = self.create_army(
            self.player1,
            "PIC",
        )

        defender1 = self.create_army(
            self.player2,
            "BUR",
        )

        # Druhý útok: KIE -> RUH s podporou HOL
        attacker2 = self.create_army(
            self.player1,
            "KIE",
        )

        supporter2 = self.create_army(
            self.player1,
            "HOL",
        )

        defender2 = self.create_army(
            self.player2,
            "RUH",
        )

        defender1_id = defender1.id
        defender2_id = defender2.id

        # PAR -> BUR
        Order.objects.create(
            phase=self.phase,
            unit=attacker1,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        # PIC support PAR -> BUR
        Order.objects.create(
            phase=self.phase,
            unit=supporter1,
            order_type="support",
            origin_province=self.province("PIC"),
            supported_unit=attacker1,
            supported_origin_province=self.province("PAR"),
            support_target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=defender1,
            order_type="hold",
            origin_province=self.province("BUR"),
        )

        # KIE -> RUH
        Order.objects.create(
            phase=self.phase,
            unit=attacker2,
            order_type="move",
            origin_province=self.province("KIE"),
            target_province=self.province("RUH"),
        )

        # HOL support KIE -> RUH
        Order.objects.create(
            phase=self.phase,
            unit=supporter2,
            order_type="support",
            origin_province=self.province("HOL"),
            supported_unit=attacker2,
            supported_origin_province=self.province("KIE"),
            support_target_province=self.province("RUH"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=defender2,
            order_type="hold",
            origin_province=self.province("RUH"),
        )

        resolve_movement_phase(
            self.phase
        )

        defender1.refresh_from_db()
        defender2.refresh_from_db()

        self.assertTrue(
            defender1.is_dislodged
        )

        self.assertTrue(
            defender2.is_dislodged
        )

        retreat_phase = GamePhase.objects.get(
            game=self.game,
            sequence=2,
        )

        # Obě jednotky se pokusí ustoupit do MUN.
        Order.objects.create(
            phase=retreat_phase,
            unit=defender1,
            order_type="retreat",
            origin_province=self.province("BUR"),
            target_province=self.province("MUN"),
        )

        Order.objects.create(
            phase=retreat_phase,
            unit=defender2,
            order_type="retreat",
            origin_province=self.province("RUH"),
            target_province=self.province("MUN"),
        )

        resolve_retreat_phase(
            retreat_phase
        )

        # Při kolizi retreatů zaniknou obě jednotky.
        self.assertFalse(
            Unit.objects.filter(
                id=defender1_id
            ).exists()
        )

        self.assertFalse(
            Unit.objects.filter(
                id=defender2_id
            ).exists()
        )

        # Potom pokračujeme do Fall Movement.
        next_phase = GamePhase.objects.get(
            game=self.game,
            sequence=3,
        )

        self.assertEqual(
            next_phase.season,
            "fall",
        )

        self.assertEqual(
            next_phase.phase_type,
            "movement",
        )

    def test_cannot_retreat_to_attacker_origin(self):
        attacker = self.create_army(
            self.player1,
            "PAR",
        )

        supporter = self.create_army(
            self.player1,
            "PIC",
        )

        defender = self.create_army(
            self.player2,
            "BUR",
        )

        Order.objects.create(
            phase=self.phase,
            unit=attacker,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=supporter,
            order_type="support",
            origin_province=self.province("PIC"),
            supported_unit=attacker,
            supported_origin_province=self.province("PAR"),
            support_target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=defender,
            order_type="hold",
            origin_province=self.province("BUR"),
        )

        resolve_movement_phase(
            self.phase
        )

        defender.refresh_from_db()

        self.assertTrue(
            defender.is_dislodged
        )

        self.assertEqual(
            defender.dislodged_by_origin.code,
            "PAR",
        )

        retreat_phase = GamePhase.objects.get(
            game=self.game,
            sequence=2,
        )

        # PAR je po pohybu prázdná a BUR -> PAR
        # je geograficky legální, ALE právě z PAR
        # přišel útok, který jednotku vytlačil.
        allowed = can_unit_retreat(
            defender,
            retreat_phase,
            self.province("PAR"),
        )

        self.assertFalse(
            allowed
        )

    def test_cannot_retreat_to_standoff_province(self):
        # Útok, který vytlačí BUR.
        attacker = self.create_army(
            self.player1,
            "PAR",
        )

        supporter = self.create_army(
            self.player1,
            "PIC",
        )

        defender = self.create_army(
            self.player2,
            "BUR",
        )

        # Dvě jednotky vytvoří standoff v MUN.
        standoff1 = self.create_army(
            self.player1,
            "RUH",
        )

        standoff2 = self.create_army(
            self.player2,
            "KIE",
        )

        Order.objects.create(
            phase=self.phase,
            unit=attacker,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=supporter,
            order_type="support",
            origin_province=self.province("PIC"),
            supported_unit=attacker,
            supported_origin_province=self.province("PAR"),
            support_target_province=self.province("BUR"),
        )

        Order.objects.create(
            phase=self.phase,
            unit=defender,
            order_type="hold",
            origin_province=self.province("BUR"),
        )

        # RUH -> MUN
        Order.objects.create(
            phase=self.phase,
            unit=standoff1,
            order_type="move",
            origin_province=self.province("RUH"),
            target_province=self.province("MUN"),
        )

        # KIE -> MUN
        Order.objects.create(
            phase=self.phase,
            unit=standoff2,
            order_type="move",
            origin_province=self.province("KIE"),
            target_province=self.province("MUN"),
        )

        resolve_movement_phase(
            self.phase
        )

        defender.refresh_from_db()
        standoff1.refresh_from_db()
        standoff2.refresh_from_db()

        # BUR byla vytlačena.
        self.assertTrue(
            defender.is_dislodged
        )

        # Oba útoky do MUN selhaly.
        self.assertEqual(
            standoff1.province.code,
            "RUH",
        )

        self.assertEqual(
            standoff2.province.code,
            "KIE",
        )

        retreat_phase = GamePhase.objects.get(
            game=self.game,
            sequence=2,
        )

        # BUR sousedí s MUN a MUN je prázdná,
        # ale v Movement fázi tam vznikl standoff.
        allowed = can_unit_retreat(
            defender,
            retreat_phase,
            self.province("MUN"),
        )

        self.assertFalse(
            allowed
        )

    def test_supply_centers_are_initialized(self):
        initialize_supply_centers(
            self.game
        )

        centers = SupplyCenterOwnership.objects.filter(
            game=self.game
        )

        self.assertEqual(
            centers.count(),
            34,
        )

        par = centers.get(
            province__code="PAR"
        )

        self.assertEqual(
            par.owner,
            self.player1,
        )

        mun = centers.get(
            province__code="MUN"
        )

        self.assertEqual(
            mun.owner,
            self.player2,
        )

        bel = centers.get(
            province__code="BEL"
        )

        self.assertIsNone(
            bel.owner
        )

    def test_fall_capture_updates_supply_center_owner(self):
        initialize_supply_centers(
            self.game
        )

        # Z našeho Spring testu uděláme Fall 1901.
        self.phase.season = "fall"

        self.phase.save(
            update_fields=[
                "season",
            ]
        )

        army = self.create_army(
            self.player1,
            "PIC",
        )

        Order.objects.create(
            phase=self.phase,
            unit=army,
            order_type="move",
            origin_province=self.province("PIC"),
            target_province=self.province("BEL"),
        )

        resolve_movement_phase(
            self.phase
        )

        army.refresh_from_db()

        self.assertEqual(
            army.province.code,
            "BEL",
        )

        belgium = SupplyCenterOwnership.objects.get(
            game=self.game,
            province__code="BEL",
        )

        self.assertEqual(
            belgium.owner,
            self.player1,
        )

        next_phase = GamePhase.objects.get(
            game=self.game,
            sequence=2,
        )

        self.assertEqual(
            next_phase.season,
            "winter",
        )

        self.assertEqual(
            next_phase.phase_type,
            "adjustment",
        )

        self.assertEqual(
            next_phase.year,
            1901,
        )

    def test_vacated_supply_center_keeps_owner(self):
        initialize_supply_centers(
            self.game
        )

        paris = SupplyCenterOwnership.objects.get(
            game=self.game,
            province__code="PAR",
        )

        self.assertEqual(
            paris.owner,
            self.player1,
        )

        self.phase.season = "fall"

        self.phase.save(
            update_fields=[
                "season",
            ]
        )

        army = self.create_army(
            self.player1,
            "PAR",
        )

        Order.objects.create(
            phase=self.phase,
            unit=army,
            order_type="move",
            origin_province=self.province("PAR"),
            target_province=self.province("BUR"),
        )

        resolve_movement_phase(
            self.phase
        )

        army.refresh_from_db()

        self.assertEqual(
            army.province.code,
            "BUR",
        )

        paris.refresh_from_db()

        # PAR je prázdná, ale Francie ji stále vlastní.
        self.assertEqual(
            paris.owner,
            self.player1,
        )
