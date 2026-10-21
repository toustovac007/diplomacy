from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TransactionTestCase
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
        cls.game = Game.objects.create(name="Fall transition", creator=users[0], status="active", movement_duration_minutes=120)
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
        self.assertEqual(phase.deadline, now + timedelta(minutes=self.game.movement_duration_minutes))
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
        self.assertEqual(self.game.result_type, "solo")
        self.assertFalse(self.game.draw_participants.exists())
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


class GameSettingsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_map", verbosity=0)
        cls.users = [get_user_model().objects.create_user(username=f"settings{i}", email=f"settings{i}@example.test") for i in range(4)]

    def setUp(self):
        self.client.force_authenticate(self.users[0])

    def create_game(self, **settings):
        response = self.client.post("/api/games/", {"name": "Settings", **settings}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Game.objects.get(pk=response.data["id"])

    def join_code(self, game, user=None):
        self.client.force_authenticate(user or self.users[1])
        return self.client.post("/api/games/join-by-code/", {"invite_code": str(game.invite_code)})

    def test_capacity_boundaries_and_creator_membership(self):
        for capacity in (2, 7):
            game = self.create_game(max_players=capacity)
            self.assertEqual(game.max_players, capacity)
            self.assertEqual(game.players.get().user, self.users[0])
        for capacity in (1, 8):
            response = self.client.post("/api/games/", {"name": "Invalid", "max_players": capacity})
            self.assertEqual(response.status_code, 400)
            self.assertIn("max_players", response.data)

    def test_defaults_and_legacy_api_duration(self):
        game = self.create_game()
        self.assertEqual((game.max_players, game.is_public), (7, True))
        self.assertEqual((game.movement_duration_minutes, game.retreat_duration_minutes, game.adjustment_duration_minutes), (1440, 720, 720))
        game = self.create_game(turn_duration_minutes=120, retreat_duration_minutes=60)
        self.assertEqual((game.movement_duration_minutes, game.retreat_duration_minutes, game.adjustment_duration_minutes), (120, 60, 120))

    def test_invalid_durations(self):
        for field in ("movement_duration_minutes", "retreat_duration_minutes", "adjustment_duration_minutes", "turn_duration_minutes"):
            for value in (0, -1, 10081):
                with self.subTest(field=field, value=value):
                    response = self.client.post("/api/games/", {"name": "Invalid", field: value})
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(field, response.data)

    def test_public_discovery_and_invite_privacy(self):
        public = self.create_game()
        private = self.create_game(is_public=False)
        active = self.create_game()
        active.status = "active"
        active.save(update_fields=["status"])
        self.assertEqual(self.client.get("/api/games/public/").data, [])
        self.client.force_authenticate(self.users[1])
        response = self.client.get("/api/games/public/")
        self.assertEqual([row["id"] for row in response.data], [public.pk])
        self.assertNotIn("invite_code", response.data[0])
        self.assertEqual(self.client.get(f"/api/games/{private.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/games/").data, [])
        self.client.force_authenticate(self.users[0])
        response = self.client.get(f"/api/games/{private.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["invite_code"], str(private.invite_code))
        from apps.games.serializer import GameSerializer
        self.assertNotIn("invite_code", GameSerializer(private).data)

    def test_invites_generated_unique_and_cannot_be_supplied(self):
        first = self.create_game()
        second = self.create_game(invite_code=str(first.invite_code))
        self.assertNotEqual(first.invite_code, second.invite_code)
        self.assertEqual(first.invite_code.version, 4)

    def test_private_join_requires_code_and_preserves_capacity(self):
        game = self.create_game(is_public=False, max_players=2)
        self.client.force_authenticate(self.users[1])
        self.assertEqual(self.client.post(f"/api/games/{game.pk}/join/").status_code, 404)
        response = self.join_code(game)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["invite_code"], str(game.invite_code))
        self.assertEqual(self.join_code(game).status_code, 400)
        self.assertEqual(self.join_code(game, self.users[2]).status_code, 400)
        self.assertEqual(game.players.count(), 2)
        self.client.force_authenticate(self.users[1])
        self.assertEqual(self.client.get(f"/api/games/{game.pk}/").status_code, 200)
        self.assertEqual(self.client.get("/api/games/").data[0]["id"], game.pk)

    def test_public_join_still_works_and_rejects_full(self):
        game = self.create_game(max_players=2)
        self.client.force_authenticate(self.users[1])
        self.assertEqual(self.client.post(f"/api/games/{game.pk}/join/").status_code, 200)
        self.client.force_authenticate(self.users[2])
        self.assertEqual(self.client.post(f"/api/games/{game.pk}/join/").status_code, 400)

    def test_invalid_or_missing_invite(self):
        import uuid
        for payload, expected in [({}, 400), ({"invite_code": "invalid"}, 400), ({"invite_code": str(uuid.uuid4())}, 404)]:
            response = self.client.post("/api/games/join-by-code/", payload)
            self.assertEqual(response.status_code, expected)

    def test_start_before_full_unique_countries_and_first_deadline(self):
        game = self.create_game(is_public=False, max_players=5, movement_duration_minutes=360)
        code = game.invite_code
        GamePlayer.objects.create(game=game, user=self.users[1])
        GamePlayer.objects.create(game=game, user=self.users[2])
        now = timezone.now()
        with patch("apps.games.services.phase_manager.timezone.now", return_value=now):
            response = self.client.post(f"/api/games/{game.pk}/start/")
        self.assertEqual(response.status_code, 200, response.data)
        game.refresh_from_db()
        self.assertEqual(game.invite_code, code)
        phase = game.phases.get()
        self.assertEqual((phase.year, phase.season, phase.phase_type), (1901, "spring", "movement"))
        self.assertEqual(phase.deadline, now + timedelta(minutes=360))
        countries = list(game.players.values_list("country", flat=True))
        self.assertEqual(len(set(countries)), 3)
        self.assertNotIn(None, countries)
        for player in game.players.all():
            self.assertTrue(Unit.objects.filter(owner=player).exists())
            self.assertTrue(SupplyCenterOwnership.objects.filter(owner=player).exists())
        self.assertEqual(self.join_code(game, self.users[3]).status_code, 400)

    def test_start_rejects_too_few_too_many_and_non_creator(self):
        game = self.create_game(max_players=2)
        self.assertEqual(self.client.post(f"/api/games/{game.pk}/start/").status_code, 400)
        for user in self.users[1:3]:
            GamePlayer.objects.create(game=game, user=user)
        self.assertEqual(self.client.post(f"/api/games/{game.pk}/start/").status_code, 400)
        self.client.force_authenticate(self.users[1])
        self.assertEqual(self.client.post(f"/api/games/{game.pk}/start/").status_code, 403)
        self.assertFalse(game.phases.exists())

    def test_each_phase_uses_its_own_duration_and_transitions(self):
        from apps.games.services.phase_manager import create_phase, create_next_after_movement, create_next_after_retreat, create_next_after_adjustment
        game = self.create_game(movement_duration_minutes=1440, retreat_duration_minutes=360, adjustment_duration_minutes=720)
        now = timezone.now()
        with patch("apps.games.services.phase_manager.timezone.now", return_value=now):
            movement = create_phase(game, 1, 1901, "fall", "movement")
            retreat = create_next_after_movement(movement, True)
            with patch("apps.games.services.phase_manager.get_adjustment_delta", return_value=1):
                adjustment = create_next_after_retreat(retreat)
            spring = create_next_after_adjustment(adjustment)
            fall = create_next_after_movement(spring, False)
        for phase, minutes in [(movement, 1440), (retreat, 360), (adjustment, 720), (spring, 1440), (fall, 1440)]:
            self.assertEqual(phase.deadline, now + timedelta(minutes=minutes))
        self.assertEqual((spring.year, spring.season), (1902, "spring"))
        self.assertEqual((fall.season, fall.phase_type), ("fall", "movement"))


class GameSettingsMigrationTests(TransactionTestCase):
    def test_existing_games_keep_all_durations_and_get_distinct_invites(self):
        from django.conf import settings
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        before = [("games", "0009_resolved_orders_snapshot")]
        after = [("games", "0010_game_creation_settings")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(before)
        try:
            old_apps = executor.loader.project_state(before).apps
            User = old_apps.get_model(settings.AUTH_USER_MODEL)
            user = User.objects.create(username="migration", email="migration@example.test")
            OldGame = old_apps.get_model("games", "Game")
            ids = [OldGame.objects.create(name="Legacy", creator_id=user.pk, turn_duration_minutes=value).pk for value in (120, 2880)]
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            MigratedGame = executor.loader.project_state(after).apps.get_model("games", "Game")
            games = list(MigratedGame.objects.filter(pk__in=ids).order_by("pk"))
            self.assertEqual(len({game.invite_code for game in games}), 2)
            for game, duration in zip(games, (120, 2880)):
                self.assertTrue(game.is_public)
                self.assertEqual((game.movement_duration_minutes, game.retreat_duration_minutes, game.adjustment_duration_minutes), (duration, duration, duration))
        finally:
            MigrationExecutor(connection).migrate(latest)


class DrawTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_map", verbosity=0)
        cls.users = [get_user_model().objects.create_user(username=f"draw{i}", email=f"draw{i}@example.test") for i in range(5)]
        cls.game = Game.objects.create(name="Draw", creator=cls.users[3], status="active")
        cls.players = [GamePlayer.objects.create(game=cls.game, user=user, country=country)
                       for user, country in zip(cls.users[:4], ["FRA", "ENG", "GER", "ITA"])]
        cls.army = Unit.objects.create(game=cls.game, owner=cls.players[0], unit_type="army", province=Province.objects.get(code="PAR"))
        cls.german = Unit.objects.create(game=cls.game, owner=cls.players[2], unit_type="army", province=Province.objects.get(code="BUR"))
        SupplyCenterOwnership.objects.create(game=cls.game, province=Province.objects.get(code="LON"), owner=cls.players[1])
        cls.previous = GamePhase.objects.create(game=cls.game, sequence=1, year=1901, season="spring", phase_type="movement",
            status="resolved", resolved_orders_snapshot=[], deadline=timezone.now(), resolved_at=timezone.now())
        cls.phase = GamePhase.objects.create(game=cls.game, sequence=2, year=1901, season="fall", phase_type="movement", deadline=timezone.now() + timedelta(days=1))
        cls.order = Order.objects.create(phase=cls.phase, unit=cls.army, order_type="move", origin_province=cls.army.province, target_province=cls.german.province)
        cls.foreign_game = Game.objects.create(name="Foreign", creator=cls.users[4], status="active")
        cls.foreign = GamePlayer.objects.create(game=cls.foreign_game, user=cls.users[4], country="RUS")

    def setUp(self):
        self.client.force_authenticate(self.users[0])
        self.base = f"/api/games/{self.game.pk}/draw-proposals/"

    def propose(self, ids=None):
        return self.client.post(self.base, {"participant_ids": ids if ids is not None else [self.players[0].pk, self.players[1].pk]}, format="json")

    def proposal(self):
        response = self.propose()
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["proposal"]["id"]

    def vote(self, proposal, player=1, vote="accept", **extra):
        self.client.force_authenticate(self.users[player])
        return self.client.post(f"{self.base}{proposal}/vote/", {"vote": vote, **extra}, format="json")

    def test_survival_uses_centers_or_units_not_creator_status(self):
        from apps.games.services.draws import surviving_players
        self.assertSetEqual(set(surviving_players(self.game).values_list("pk", flat=True)), {p.pk for p in self.players[:3]})
        self.assertFalse(self.players[1].units.exists())
        self.assertFalse(self.players[2].owned_supply_centers.exists())
        self.german.is_dislodged = True
        self.german.save(update_fields=["is_dislodged"])
        self.assertIn(self.players[2], surviving_players(self.game))
        self.client.force_authenticate(self.users[3])
        self.assertEqual(self.propose([p.pk for p in self.players]).status_code, 403)

    def test_proposal_snapshots_all_voters_and_auto_accepts(self):
        from apps.games.models import DrawProposal
        pid = self.proposal()
        proposal = DrawProposal.objects.get(pk=pid)
        self.assertSetEqual(set(proposal.participants.values_list("pk", flat=True)), {self.players[0].pk, self.players[1].pk})
        self.assertSetEqual(set(proposal.voters.values_list("pk", flat=True)), {p.pk for p in self.players[:3]})
        self.assertEqual(proposal.votes.get(player=self.players[0]).vote, "accept")
        self.assertIsNotNone(proposal.votes.get(player=self.players[0]).voted_at)
        self.assertEqual(proposal.votes.filter(vote__isnull=True).count(), 2)
        self.german.delete()
        self.assertEqual(proposal.voters.count(), 3)
        self.assertEqual(self.vote(pid, 2).status_code, 200)

    def test_invalid_winner_lists(self):
        for ids in ([self.players[0].pk], [self.players[1].pk, self.players[2].pk],
                    [self.players[0].pk, self.foreign.pk], [self.players[0].pk, self.players[3].pk],
                    [self.players[0].pk, self.players[1].pk, self.players[1].pk]):
            with self.subTest(ids=ids):
                self.assertEqual(self.propose(ids).status_code, 400)

    def test_one_open_proposal_api_and_database_constraint(self):
        from apps.games.models import DrawProposal
        from django.db import IntegrityError, transaction
        self.proposal()
        self.assertEqual(self.propose().status_code, 400)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DrawProposal.objects.create(game=self.game, proposer=self.players[1])

    def test_non_winner_must_accept_before_finish(self):
        from apps.games.models import DrawProposal
        pid = self.proposal()
        response = self.vote(pid)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["game_status"], "active")
        self.assertEqual(self.vote(pid).status_code, 200)
        response = self.vote(pid, 2)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["game_status"], "finished")
        self.game.refresh_from_db()
        self.assertEqual(self.game.result_type, "draw")
        self.assertIsNone(self.game.winner)
        self.assertIsNotNone(self.game.finished_at)
        self.assertSetEqual(set(self.game.draw_participants.values_list("pk", flat=True)), {self.players[0].pk, self.players[1].pk})
        proposal = DrawProposal.objects.get(pk=pid)
        self.assertEqual(proposal.status, "accepted")
        self.assertIsNotNone(proposal.resolved_at)

    def test_accept_can_change_to_reject_and_new_proposal_is_allowed(self):
        from apps.games.models import DrawProposal
        pid = self.proposal()
        self.vote(pid)
        response = self.vote(pid, 1, "reject")
        self.assertEqual(response.data["proposal"]["status"], "rejected")
        self.game.refresh_from_db()
        self.phase.refresh_from_db()
        self.assertEqual(self.game.status, "active")
        self.assertEqual(self.phase.status, "open")
        self.assertIsNone(self.game.result_type)
        self.assertEqual(self.vote(pid, 2).status_code, 400)
        self.assertIsNotNone(DrawProposal.objects.get(pk=pid).resolved_at)
        self.client.force_authenticate(self.users[0])
        self.assertEqual(self.propose().status_code, 201)

    def test_creator_non_voter_and_foreign_user_cannot_vote_or_cancel(self):
        pid = self.proposal()
        self.assertEqual(self.vote(pid, 3).status_code, 403)
        self.assertEqual(self.client.post(f"{self.base}{pid}/cancel/").status_code, 403)
        self.assertEqual(self.vote(pid, 4).status_code, 404)
        self.assertEqual(self.client.get(self.base + "current/").status_code, 404)
        foreign_url = f"/api/games/{self.foreign_game.pk}/draw-proposals/{pid}/vote/"
        self.assertEqual(self.client.post(foreign_url, {"vote": "accept"}).status_code, 404)

    def test_proposer_cancel_and_resolved_actions_rejected(self):
        pid = self.proposal()
        response = self.client.post(f"{self.base}{pid}/cancel/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["proposal"]["status"], "cancelled")
        self.assertEqual(self.client.post(f"{self.base}{pid}/cancel/").status_code, 400)
        self.assertEqual(self.vote(pid).status_code, 400)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.status, "open")
        self.assertIsNone(self.client.get(self.base + "current/").data["proposal"])

    def test_draw_cancels_without_adjudication_and_preserves_real_history(self):
        from apps.games.services.deadlines import process_expired_phases
        pid = self.proposal()
        self.vote(pid)
        self.vote(pid, 2)
        self.phase.refresh_from_db()
        self.army.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.phase.status, "cancelled")
        self.assertIsNone(self.phase.resolved_orders_snapshot)
        self.assertEqual(self.army.province.code, "PAR")
        self.assertEqual(self.game.phases.count(), 2)
        self.assertFalse(self.game.phases.filter(status="open").exists())
        response = self.client.get(f"/api/orders/games/{self.game.pk}/previous/")
        self.assertEqual(response.data["phase"]["id"], self.previous.pk)
        self.assertEqual(response.data["orders"], [])
        self.assertTrue(response.data["history_available"])
        self.assertEqual(process_expired_phases(now=timezone.now() + timedelta(days=2)), [])
        for path in ("", "retreats/", "adjustments/", "resolve/", "resolve-retreat/", "resolve-adjustment/"):
            self.assertEqual(self.client.post(f"/api/orders/games/{self.game.pk}/{path}", {"unit_id": self.army.pk, "order_type": "hold"}).status_code, 404)

    def test_finished_serializer_and_writes(self):
        pid = self.proposal()
        self.vote(pid)
        self.vote(pid, 2)
        response = self.client.get(f"/api/games/{self.game.pk}/")
        self.assertEqual(response.data["result_type"], "draw")
        self.assertIsNone(response.data["winner"])
        self.assertIsNone(response.data["current_phase"])
        self.assertEqual(len(response.data["draw_participants"]), 2)
        self.assertEqual(self.vote(pid).status_code, 400)
        self.client.force_authenticate(self.users[0])
        self.assertEqual(self.propose().status_code, 400)
        self.assertEqual(self.client.post(f"{self.base}{pid}/cancel/").status_code, 400)
        self.assertEqual(self.client.get(self.base + "current/").data["game_status"], "finished")

    def test_proposal_status_public_to_members_but_not_in_game_serializer(self):
        pid = self.proposal()
        self.client.force_authenticate(self.users[3])
        self.assertEqual(self.client.get(self.base + "current/").data["proposal"]["id"], pid)
        data = self.client.get(f"/api/games/{self.game.pk}/").data
        self.assertIsNone(data["result_type"])
        self.assertEqual(data["draw_participants"], [])
        self.assertFalse({"proposal", "draw_proposals", "votes", "voters"} & data.keys())
        from apps.games.serializer import GameSerializer
        self.assertTrue(GameSerializer().fields["result_type"].read_only)
        self.assertTrue(GameSerializer().fields["draw_participants"].read_only)

    def test_proposed_participants_cannot_be_changed_by_vote_payload(self):
        from apps.games.models import DrawProposal
        pid = self.proposal()
        self.assertEqual(self.vote(pid, participant_ids=[self.players[2].pk]).status_code, 400)
        proposal = DrawProposal.objects.get(pk=pid)
        self.assertSetEqual(set(proposal.participants.values_list("pk", flat=True)), {self.players[0].pk, self.players[1].pk})
        self.assertEqual(self.client.patch(f"{self.base}{pid}/vote/", {"participant_ids": []}).status_code, 405)
        self.assertEqual(self.vote(pid, vote="unknown").status_code, 400)

    def test_chat_stays_private_and_becomes_read_only(self):
        chat_base = f"/api/games/{self.game.pk}/chats/"
        cid = self.client.post(chat_base, {"conversation_type": "direct", "participant_ids": [self.players[1].pk]}, format="json").data["id"]
        messages = f"{chat_base}{cid}/messages/"
        self.assertEqual(self.client.post(messages, {"text": "Diplomacy"}).status_code, 201)
        pid = self.proposal()
        self.vote(pid)
        self.vote(pid, 2)
        self.assertEqual(self.client.get(messages).status_code, 404)
        self.client.force_authenticate(self.users[0])
        self.assertEqual(self.client.get(messages).status_code, 200)
        self.assertEqual(self.client.post(messages, {"text": "Too late"}).status_code, 400)
        self.client.force_authenticate(self.users[3])
        self.assertEqual(self.client.get(messages).status_code, 404)

    def test_waiting_and_unauthenticated_proposals_rejected(self):
        self.game.status = "waiting"
        self.game.save(update_fields=["status"])
        self.assertEqual(self.propose().status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.propose().status_code, 401)

    def test_solo_completion_uses_same_helper_and_cancels_pending_proposal(self):
        from apps.games.services.victory import finish_game
        from apps.games.models import DrawProposal
        from django.db import transaction
        pid = self.proposal()
        with transaction.atomic():
            game = Game.objects.select_for_update().get(pk=self.game.pk)
            finish_game(game, self.players[0])
        self.game.refresh_from_db()
        self.assertEqual(self.game.result_type, "solo")
        self.assertEqual(self.game.winner, self.players[0])
        self.assertFalse(self.game.draw_participants.exists())
        self.assertEqual(DrawProposal.objects.get(pk=pid).status, "cancelled")

    def test_finish_failure_rolls_back_vote_and_proposal(self):
        from apps.games.models import DrawProposal
        pid = self.proposal()
        self.vote(pid)
        with patch("apps.games.services.draws.finish_game", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.vote(pid, 2)
        proposal = DrawProposal.objects.get(pk=pid)
        self.assertEqual(proposal.status, "open")
        self.assertIsNone(proposal.votes.get(player=self.players[2]).vote)
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "active")


class DrawMigrationTests(TransactionTestCase):
    def test_existing_solo_results_backfilled_and_active_results_empty(self):
        from django.conf import settings
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        before = [("games", "0010_game_creation_settings")]
        after = [("games", "0011_draw_voting")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            user = apps.get_model(settings.AUTH_USER_MODEL).objects.create(username="drawmigration", email="dm@example.test")
            OldGame = apps.get_model("games", "Game")
            solo = OldGame.objects.create(name="Solo", creator_id=user.pk, status="finished")
            player = apps.get_model("games", "GamePlayer").objects.create(game_id=solo.pk, user_id=user.pk, country="FRA")
            solo.winner_id = player.pk
            solo.save()
            active = OldGame.objects.create(name="Active", creator_id=user.pk, status="active")
            waiting = OldGame.objects.create(name="Waiting", creator_id=user.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(after)
            self.assertEqual(Game.objects.get(pk=solo.pk).result_type, "solo")
            self.assertIsNone(Game.objects.get(pk=active.pk).result_type)
            self.assertIsNone(Game.objects.get(pk=waiting.pk).result_type)
        finally:
            MigrationExecutor(connection).migrate(latest)


class ConcurrentDrawTests(TransactionTestCase):
    def test_simultaneous_proposals_cannot_create_two_open_proposals(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections
        from rest_framework.exceptions import APIException
        from apps.games.models import DrawProposal
        from apps.games.services.draws import propose
        call_command("seed_map", verbosity=0)
        users = [get_user_model().objects.create_user(username=f"drawparallel{i}", email=f"dp{i}@example.test") for i in range(2)]
        game = Game.objects.create(name="Concurrent draws", creator=users[0], status="active")
        players = [GamePlayer.objects.create(game=game, user=user, country=country) for user, country in zip(users, ["FRA", "ENG"])]
        for player, code in zip(players, ["PAR", "LON"]):
            SupplyCenterOwnership.objects.create(game=game, owner=player, province=Province.objects.get(code=code))
        barrier = Barrier(2)

        def create(index):
            try:
                barrier.wait(timeout=5)
                propose(game.pk, users[index], [p.pk for p in players])
                return 201
            except APIException as error:
                return error.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(create, [0, 1]))
        self.assertTrue(set(statuses) <= {201, 400, 503})
        self.assertLessEqual(statuses.count(201), 1)
        self.assertLessEqual(DrawProposal.objects.filter(game=game, status="open").count(), 1)
