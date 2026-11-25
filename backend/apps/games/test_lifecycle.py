from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.games.models import Game, GamePlayer, GamePhase, GameStake, Unit
from apps.games.services.game_setup import create_starting_units
from apps.games.services.lifecycle import cleanup_waiting_games, cancel_waiting_game, finish_if_inactive
from apps.games.services.supply_centers import initialize_supply_centers
from apps.games.services.tokens import release_eliminated_stakes, settle_game
from apps.games.services.victory import finish_game
from apps.games import test_tokens as token_fixtures
from apps.orders.services.adjudication import resolve_movement_phase
from apps.orders.services.adjustments import resolve_adjustment_phase
from apps.orders.services.retreat import resolve_retreat_phase
from apps.users.models import User, TokenEntry
from apps.users.tokens import wallet_snapshot


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", GAME_CREATE_COOLDOWN_SECONDS=0)
class LifecycleTests(TestCase):
    user = token_fixtures.TokenTests.user
    game = token_fixtures.TokenTests.game
    client_for = token_fixtures.TokenTests.client_for
    centers = token_fixtures.TokenTests.centers

    @classmethod
    def setUpTestData(cls):
        call_command("seed_map", verbosity=0)

    def waiting(self, *, stake=500):
        return self.game(count=2, stake=stake, status="waiting")

    def age(self, game, when):
        Game.objects.filter(pk=game.pk).update(created_at=when)
        GamePlayer.objects.filter(game=game).update(joined_at=when)

    def playable(self, scoring="dss"):
        game, players = self.game(count=2, scoring=scoring)
        for player, country in zip(players, ("FRA", "ENG")):
            player.country = country
            player.save(update_fields=["country"])
        create_starting_units(game)
        initialize_supply_centers(game)
        phase = GamePhase.objects.create(game=game, sequence=1, year=1901, season="spring",
            phase_type="movement", deadline=timezone.now() + timedelta(days=1))
        return game, players, phase

    def test_creator_delete_refunds_all_and_retains_reconcilable_ledger(self):
        game, players = self.waiting()
        url = f"/api/games/{game.pk}/"
        response = self.client_for(players[0].user).delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Game.objects.filter(pk=game.pk).exists())
        for player in players:
            self.assertEqual(wallet_snapshot(player.user_id)["available"], 1000)
            self.assertEqual(wallet_snapshot(player.user_id)["frozen"], 0)
            entries = TokenEntry.objects.filter(user_id=player.user_id)
            self.assertEqual(sum(entries.values_list("available_delta", flat=True)), 0)
            self.assertEqual(sum(entries.values_list("frozen_delta", flat=True)), 0)
            self.assertEqual(entries.filter(kind="refund", game__isnull=True).count(), 1)
        self.assertEqual(self.client_for(players[0].user).delete(url).status_code, 404)
        self.assertEqual(TokenEntry.objects.filter(kind="refund").count(), 2)

    def test_members_and_outsiders_cannot_delete(self):
        game, players = self.waiting()
        url = f"/api/games/{game.pk}/"
        for user in (players[1].user, self.user("outsider")):
            self.assertEqual(self.client_for(user).delete(url).status_code, 403)
        self.assertEqual(APIClient().delete(url).status_code, 401)
        self.assertEqual(Game.objects.count(), 1)
        self.assertFalse(TokenEntry.objects.filter(kind="refund").exists())

    def test_active_and_finished_games_cannot_be_deleted(self):
        game, players = self.game(count=2)
        client = self.client_for(players[0].user)
        self.assertEqual(client.delete(f"/api/games/{game.pk}/").status_code, 409)
        finish_game(game, players[0])
        self.assertEqual(client.delete(f"/api/games/{game.pk}/").status_code, 409)
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())

    def test_refund_failure_rolls_back_everything(self):
        game, players = self.waiting()
        with patch("apps.games.services.lifecycle.refund_stake", side_effect=RuntimeError("refund failed")):
            with self.assertRaises(RuntimeError):
                cancel_waiting_game(game.pk, actor=players[0].user)
        self.assertEqual(wallet_snapshot(players[0].user_id)["available"], 500)
        self.assertEqual(game.players.count(), 2)
        self.assertEqual(GameStake.objects.filter(status="locked").count(), 2)

    def test_cleanup_waits_exactly_48_hours_and_refunds_only_waiting_games(self):
        now = timezone.now()
        old, players = self.waiting()
        self.age(old, now - timedelta(days=2))
        fresh, _ = self.waiting()
        self.age(fresh, now - timedelta(days=2) + timedelta(seconds=1))
        active, _ = self.game(count=2)
        self.age(active, now - timedelta(days=5))
        self.assertEqual(cleanup_waiting_games(now=now), 1)
        self.assertEqual(cleanup_waiting_games(now=now), 0)
        self.assertTrue(Game.objects.filter(pk=fresh.pk).exists())
        self.assertTrue(Game.objects.filter(pk=active.pk).exists())
        self.assertTrue(all(wallet_snapshot(p.user_id)["available"] == 1000 for p in players))

    def test_new_join_extends_expiry_duplicate_join_does_not(self):
        now = timezone.now()
        game, players = self.waiting()
        self.age(game, now - timedelta(days=3))
        newcomer = self.user("newjoin")
        response = self.client_for(newcomer).post(f"/api/games/{game.pk}/join/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(cleanup_waiting_games(now=now), 0)
        latest = GamePlayer.objects.get(game=game, user=newcomer).joined_at
        self.assertEqual(self.client_for(newcomer).post(f"/api/games/{game.pk}/join/").status_code, 400)
        self.assertEqual(GamePlayer.objects.get(game=game, user=newcomer).joined_at, latest)
        self.assertEqual(cleanup_waiting_games(now=latest + timedelta(days=2)), 1)

    def test_expiry_is_rechecked_under_lock_after_shortlist(self):
        now = timezone.now()
        game, _ = self.waiting()
        self.age(game, now - timedelta(days=3))
        newcomer = self.user("rescue")
        self.client_for(newcomer).post(f"/api/games/{game.pk}/join/")
        self.assertFalse(cancel_waiting_game(game.pk, expired_before=now))
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())

    def test_deadline_command_also_cleans_waiting_games_without_expired_phases(self):
        game, _ = self.waiting()
        self.age(game, timezone.now() - timedelta(days=3))
        call_command("process_deadlines", verbosity=0)
        self.assertFalse(Game.objects.filter(pk=game.pk).exists())

    def test_ten_actual_default_phases_end_draw_without_an_eleventh_phase(self):
        for scoring in ("dss", "sos", "unranked"):
            game, players, phase = self.playable(scoring)
            for index in range(10):
                resolve_movement_phase(phase)
                game.refresh_from_db()
                self.assertEqual(game.inactive_phase_count, index + 1)
                if index < 9:
                    self.assertEqual(game.status, "active")
                    phase = game.phases.get(status="open")
            self.assertEqual(game.status, "finished")
            self.assertEqual(game.result_type, "draw")
            self.assertEqual(game.termination_reason, "inactivity")
            self.assertEqual(game.phases.count(), 10)
            self.assertFalse(game.phases.filter(status="open").exists())
            self.assertEqual(set(game.draw_participants.values_list("pk", flat=True)), {p.pk for p in players})
            self.assertEqual(sum(GameStake.objects.filter(player__game=game).values_list("payout", flat=True)), 200)

    def test_user_hold_resets_streak_and_invalid_order_does_not(self):
        game, players, phase = self.playable()
        Game.objects.filter(pk=game.pk).update(inactive_phase_count=9)
        unit = Unit.objects.filter(owner=players[0]).first()
        client = self.client_for(players[0].user)
        url = f"/api/orders/games/{game.pk}/"
        self.assertEqual(client.post(url, {"unit_id": unit.pk, "order_type": "bogus"}).status_code, 400)
        phase.refresh_from_db()
        self.assertFalse(phase.has_submitted_orders)
        self.assertEqual(client.post(url, {"unit_id": unit.pk, "order_type": "hold"}).status_code, 201)
        resolve_movement_phase(phase)
        game.refresh_from_db()
        self.assertEqual((game.status, game.inactive_phase_count), ("active", 0))
        resolve_movement_phase(game.phases.get(status="open"))
        game.refresh_from_db()
        self.assertEqual(game.inactive_phase_count, 1)

    def test_retreat_and_winter_resolutions_count_as_one_phase_each(self):
        for kind in ("retreat", "adjustment"):
            game, players, phase = self.playable()
            Game.objects.filter(pk=game.pk).update(inactive_phase_count=9)
            phase.phase_type = kind
            phase.season = "spring" if kind == "retreat" else "winter"
            phase.save()
            if kind == "retreat":
                resolve_retreat_phase(phase)
            else:
                resolve_adjustment_phase(phase, allow_automatic_disbands=True)
            game.refresh_from_db()
            self.assertEqual((game.status, game.inactive_phase_count), ("finished", 10))
            self.assertEqual(game.phases.count(), 1)

    def test_explicit_retreat_disband_counts_even_after_order_is_deleted(self):
        game, players, phase = self.playable()
        Game.objects.filter(pk=game.pk).update(inactive_phase_count=9)
        phase.phase_type = "retreat"
        phase.save()
        unit = Unit.objects.filter(owner=players[0], unit_type="army").first()
        unit.is_dislodged = True
        unit.save()
        response = self.client_for(players[0].user).post(f"/api/orders/games/{game.pk}/retreats/",
            {"unit_id": unit.pk, "order_type": "disband"})
        self.assertEqual(response.status_code, 201, response.data)
        phase.refresh_from_db()
        self.assertEqual(phase.status, "resolved")
        self.assertTrue(phase.has_submitted_orders)
        self.assertFalse(phase.orders.exists())
        game.refresh_from_db()
        self.assertEqual((game.status, game.inactive_phase_count), ("active", 0))

    def test_already_checked_phase_cannot_increment_twice(self):
        game, _, phase = self.playable()
        phase.status = "resolved"
        phase.save()
        with transaction.atomic():
            self.assertFalse(finish_if_inactive(game, phase))
            self.assertFalse(finish_if_inactive(game, phase))
        game.refresh_from_db()
        self.assertEqual(game.inactive_phase_count, 1)

    def test_inactivity_draw_can_include_one_survivor(self):
        game, players = self.game(count=2)
        self.centers(players[0], 1)
        phase = GamePhase.objects.create(game=game, sequence=1, phase_type="movement", season="spring",
            status="resolved", deadline=timezone.now())
        game.inactive_phase_count = 9
        game.save()
        with transaction.atomic():
            self.assertTrue(finish_if_inactive(game, phase))
        self.assertEqual(list(game.draw_participants.values_list("pk", flat=True)), [players[0].pk])
        self.assertEqual(GameStake.objects.get(player=players[0]).payout, 200)

    def test_no_survivor_returns_stakes_instead_of_losing_the_pot(self):
        game, players = self.game(count=2, scoring="sos")
        release_eliminated_stakes(game)
        phase = GamePhase.objects.create(game=game, sequence=1, phase_type="movement", season="spring",
            status="resolved", deadline=timezone.now())
        game.inactive_phase_count = 9
        game.save()
        with transaction.atomic():
            self.assertTrue(finish_if_inactive(game, phase))
        self.assertTrue(all(wallet_snapshot(p.user_id)["available"] == 1000 for p in players))

    def test_unranked_eliminated_refund_is_immediate_and_not_paid_again(self):
        game, players = self.game(count=3, scoring="unranked", stake=1000)
        self.centers(players[0], 1)
        self.centers(players[1], 1)
        release_eliminated_stakes(game)
        release_eliminated_stakes(game)
        self.assertEqual(wallet_snapshot(players[2].user_id)["available"], 1000)
        self.assertEqual(wallet_snapshot(players[2].user_id)["frozen"], 0)
        self.assertEqual(TokenEntry.objects.filter(user=players[2].user, kind="refund").count(), 1)
        response = self.client_for(players[0].user).get(f"/api/games/{game.pk}/")
        self.assertEqual(response.data["token_pot"], 3000)
        self.assertEqual(response.data["token_pot_remaining"], 2000)
        finish_game(game, players[0])
        settle_game(game.pk)
        self.assertTrue(all(wallet_snapshot(p.user_id)["available"] == 1000 for p in players))
        self.assertEqual(sum(GameStake.objects.filter(player__game=game).values_list("payout", flat=True)), 3000)


class LifecycleMigrationTests(TransactionTestCase):
    def test_existing_eliminated_unranked_stake_is_returned_once_and_pending_orders_preserved(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [("games", "0014_game_scoring_game_token_pot_game_token_stake_and_more"),
                  ("users", "0005_user_last_token_refill_at_user_token_refill_due_at_and_more"),
                  ("orders", "0006_convoy_orders")]
        executor.migrate(before)
        try:
            old = executor.loader.project_state(before).apps
            users = [old.get_model("users", "User").objects.create(username=f"legacy{i}",
                email=f"legacy{i}@example.test", tokens_available=0) for i in range(2)]
            game = old.get_model("games", "Game").objects.create(name="Legacy unranked", creator=users[0],
                status="active", scoring="unranked", token_stake=1000, token_pot=2000)
            players = [old.get_model("games", "GamePlayer").objects.create(game=game, user=user) for user in users]
            for player in players:
                old.get_model("games", "GameStake").objects.create(player=player, amount=1000)
                old.get_model("users", "TokenEntry").objects.create(user_id=player.user_id, game=game,
                    kind="stake", available_delta=-1000, frozen_delta=1000)
            province = old.get_model("maps", "Province").objects.create(code="ZZZ", name="Legacy center",
                province_type="inland", is_supply_center=True)
            old.get_model("games", "SupplyCenterOwnership").objects.create(game=game, province=province, owner=players[0])
            unit = old.get_model("games", "Unit").objects.create(game=game, owner=players[0], unit_type="army", province=province)
            phase = old.get_model("games", "GamePhase").objects.create(game=game, sequence=1,
                season="spring", phase_type="movement", deadline=timezone.now())
            old.get_model("orders", "Order").objects.create(phase=phase, unit=unit,
                order_type="hold", origin_province=province, is_default=False)
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(User.objects.get(pk=users[0].pk).tokens_available, 0)
            self.assertEqual(User.objects.get(pk=users[1].pk).tokens_available, 1000)
            self.assertEqual(GameStake.objects.get(player_id=players[1].pk).status, "refunded")
            self.assertTrue(GamePhase.objects.get(pk=phase.pk).has_submitted_orders)
            self.assertEqual(Game.objects.get(pk=game.pk).inactive_phase_count, 0)
            MigrationExecutor(connection).migrate(latest)
            release_eliminated_stakes(Game.objects.get(pk=game.pk))
            self.assertEqual(TokenEntry.objects.filter(kind="refund").count(), 1)
            self.assertEqual(User.objects.get(pk=users[1].pk).tokens_available, 1000)
        finally:
            MigrationExecutor(connection).migrate(latest)
