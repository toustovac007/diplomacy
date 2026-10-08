from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.games.models import (
    Game,
    GamePlayer,
    GamePhase,
    Unit,
)

from apps.maps.models import Province

from apps.games.services.deadlines import (
    process_expired_phases,
)

from apps.games.services.supply_centers import (
    initialize_supply_centers,
)




User = get_user_model()


class DeadlineTestCase(TestCase):

    def setUp(self):
        call_command(
            "seed_map",
            verbosity=0,
        )

        self.user1 = User.objects.create_user(
            username="deadline_france",
            email="deadline_france@test.cz",
            password="test12345",
        )

        self.user2 = User.objects.create_user(
            username="deadline_germany",
            email="deadline_germany@test.cz",
            password="test12345",
        )

        self.game = Game.objects.create(
            name="Deadline test",
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

    def test_expired_movement_is_resolved(self):
        phase = GamePhase.objects.create(
            game=self.game,
            sequence=1,
            year=1901,
            season="spring",
            phase_type="movement",
            status="open",
            deadline=(
                    timezone.now()
                    - timedelta(minutes=1)
            ),
        )

        army = self.create_army(
            self.france,
            "PAR",
        )

        # Žádný order.
        # Resolver tedy musí vytvořit automatický HOLD.

        results = process_expired_phases()

        phase.refresh_from_db()
        army.refresh_from_db()

        self.assertEqual(
            phase.status,
            "resolved",
        )

        self.assertEqual(
            army.province.code,
            "PAR",
        )

        self.assertEqual(
            len(results),
            1,
        )

        self.assertEqual(
            results[0]["status"],
            "resolved",
        )

        next_phase = GamePhase.objects.get(
            game=self.game,
            sequence=2,
        )

        self.assertEqual(
            next_phase.season,
            "fall",
        )

        self.assertEqual(
            next_phase.phase_type,
            "movement",
        )

    def test_future_phase_is_not_resolved(self):
        phase = GamePhase.objects.create(
            game=self.game,
            sequence=1,
            year=1901,
            season="spring",
            phase_type="movement",
            status="open",
            deadline=(
                    timezone.now()
                    + timedelta(hours=24)
            ),
        )

        results = process_expired_phases()

        phase.refresh_from_db()

        self.assertEqual(
            phase.status,
            "open",
        )

        self.assertEqual(
            results,
            [],
        )

        self.assertFalse(
            GamePhase.objects.filter(
                game=self.game,
                sequence=2,
            ).exists()
        )

    def test_only_expired_phase_is_processed(self):
        expired_game = self.game

        future_game = Game.objects.create(
            name="Future game",
            creator=self.user1,
            status="active",
            turn_duration_minutes=1440,
            max_players=7,
        )

        GamePlayer.objects.create(
            game=future_game,
            user=self.user1,
            country="ENG",
        )

        expired_phase = GamePhase.objects.create(
            game=expired_game,
            sequence=1,
            year=1901,
            season="spring",
            phase_type="movement",
            status="open",
            deadline=(
                    timezone.now()
                    - timedelta(minutes=5)
            ),
        )

        future_phase = GamePhase.objects.create(
            game=future_game,
            sequence=1,
            year=1901,
            season="spring",
            phase_type="movement",
            status="open",
            deadline=(
                    timezone.now()
                    + timedelta(hours=5)
            ),
        )

        process_expired_phases()

        expired_phase.refresh_from_db()
        future_phase.refresh_from_db()

        self.assertEqual(
            expired_phase.status,
            "resolved",
        )

        self.assertEqual(
            future_phase.status,
            "open",
        )

    def test_management_command_processes_deadline(self):
        phase = GamePhase.objects.create(
            game=self.game,
            sequence=1,
            year=1901,
            season="spring",
            phase_type="movement",
            status="open",
            deadline=(
                    timezone.now()
                    - timedelta(minutes=1)
            ),
        )

        call_command(
            "process_deadlines",
            verbosity=0,
        )

        phase.refresh_from_db()

        self.assertEqual(
            phase.status,
            "resolved",
        )

    def test_expired_adjustment_automatically_disbands_unit(self):
        initialize_supply_centers(
            self.game
        )

        # Francie má 3 supply centra.
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

        extra_unit = self.create_army(
            self.france,
            "TYR",
        )

        extra_unit_id = extra_unit.id

        phase = GamePhase.objects.create(
            game=self.game,
            sequence=1,
            year=1901,
            season="winter",
            phase_type="adjustment",
            status="open",
            deadline=(
                    timezone.now()
                    - timedelta(minutes=1)
            ),
        )

        # Hráč nezadal žádný DISBAND.
        process_expired_phases()

        phase.refresh_from_db()

        self.assertEqual(
            phase.status,
            "resolved",
        )

        # Nejvzdálenější jednotka byla automaticky odstraněna.
        self.assertFalse(
            Unit.objects.filter(
                id=extra_unit_id
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

    def test_process_game_tasks_command(self):
        phase = GamePhase.objects.create(
            game=self.game,
            sequence=1,
            year=1901,
            season="spring",
            phase_type="movement",
            status="open",
            deadline=(
                    timezone.now()
                    - timedelta(minutes=1)
            ),
        )

        call_command(
            "process_game_tasks",
            verbosity=0,
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
            next_phase.season,
            "fall",
        )

        self.assertEqual(
            next_phase.phase_type,
            "movement",
        )


