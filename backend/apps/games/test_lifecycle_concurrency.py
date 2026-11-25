from datetime import timedelta
from unittest import skipUnless

from django.core.management import call_command
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.games import test_token_concurrency as fixtures
from apps.games.models import Game, GamePlayer, GamePhase, Unit
from apps.games.services.game_setup import create_starting_units
from apps.games.services.lifecycle import cleanup_waiting_games
from apps.games.services.supply_centers import initialize_supply_centers
from apps.games.services.tokens import release_eliminated_stakes, settle_game
from apps.orders.services.adjudication import resolve_movement_phase, AdjudicationError
from apps.users.models import TokenEntry
from apps.users.tokens import wallet_snapshot


@skipUnless(connection.vendor == "postgresql", "Requires a live PostgreSQL test database")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", GAME_CREATE_COOLDOWN_SECONDS=0)
class LifecycleConcurrencyTests(TransactionTestCase):
    setUp = fixtures.TokenConcurrencyTests.setUp
    game = fixtures.TokenConcurrencyTests.game
    post = fixtures.TokenConcurrencyTests.post
    parallel = fixtures.TokenConcurrencyTests.parallel

    def delete(self, game):
        client = APIClient()
        client.force_authenticate(self.users[0])
        return client.delete(f"/api/games/{game.pk}/").status_code

    def playable(self):
        call_command("seed_map", verbosity=0)
        game = self.game(self.users[:2], 100)
        players = list(game.players.order_by("pk"))
        for player, country in zip(players, ("FRA", "ENG")):
            player.country = country
            player.save()
        game.status = "active"
        game.save()
        create_starting_units(game)
        initialize_supply_centers(game)
        phase = GamePhase.objects.create(game=game, sequence=1, year=1901, season="spring",
            phase_type="movement", deadline=timezone.now())
        return game, players, phase

    def test_join_racing_deletion_never_loses_or_duplicates_a_stake(self):
        game = self.game(self.users[:1], 500)
        statuses = self.parallel([lambda: self.delete(game),
            lambda: self.post(self.users[1], f"/api/games/{game.pk}/join/")])
        self.assertEqual(statuses[0], 204)
        self.assertIn(statuses[1], (200, 404))
        self.assertFalse(Game.objects.filter(pk=game.pk).exists())
        for user in self.users[:2]:
            self.assertEqual(wallet_snapshot(user.pk)["available"], 1000)
            self.assertEqual(wallet_snapshot(user.pk)["frozen"], 0)

    def test_start_racing_deletion_has_one_consistent_outcome(self):
        call_command("seed_map", verbosity=0)
        game = self.game(self.users[:2], 100)
        statuses = self.parallel([lambda: self.delete(game),
            lambda: self.post(self.users[0], f"/api/games/{game.pk}/start/")])
        self.assertIn(tuple(statuses), ((204, 404), (409, 200)))
        exists = Game.objects.filter(pk=game.pk).exists()
        for user in self.users[:2]:
            self.assertEqual(wallet_snapshot(user.pk)["available"], 900 if exists else 1000)
            self.assertEqual(wallet_snapshot(user.pk)["frozen"], 100 if exists else 0)

    def test_two_cleanup_workers_refund_once(self):
        game = self.game(self.users[:2], 500)
        when = timezone.now() - timedelta(days=3)
        Game.objects.filter(pk=game.pk).update(created_at=when)
        GamePlayer.objects.filter(game=game).update(joined_at=when)
        results = self.parallel([cleanup_waiting_games, cleanup_waiting_games])
        self.assertEqual(sum(results), 1)
        self.assertEqual(TokenEntry.objects.filter(kind="refund").count(), 2)
        self.assertTrue(all(wallet_snapshot(user.pk)["available"] == 1000 for user in self.users[:2]))

    def test_unranked_early_refund_racing_final_payment_does_not_pay_twice(self):
        game = self.game(self.users[:2], 500)
        Game.objects.filter(pk=game.pk).update(status="active", scoring="unranked")
        def finish():
            with transaction.atomic():
                locked = Game.objects.select_for_update().get(pk=game.pk)
                locked.status, locked.result_type = "finished", "solo"
                locked.winner = locked.players.get(user=self.users[0])
                locked.save()
                settle_game(locked.pk)
        self.parallel([lambda: release_eliminated_stakes(game), finish])
        for user in self.users[:2]:
            self.assertEqual(wallet_snapshot(user.pk)["available"], 1000)
            self.assertEqual(wallet_snapshot(user.pk)["frozen"], 0)
            self.assertEqual(sum(TokenEntry.objects.filter(user=user).values_list("available_delta", flat=True)), 0)

    def test_tenth_phase_racing_resolution_finishes_and_pays_only_once(self):
        game, players, phase = self.playable()
        Game.objects.filter(pk=game.pk).update(inactive_phase_count=9)
        def resolve():
            try:
                resolve_movement_phase(GamePhase.objects.get(pk=phase.pk))
                return True
            except AdjudicationError:
                return False
        self.assertEqual(sorted(self.parallel([resolve, resolve])), [False, True])
        game.refresh_from_db()
        self.assertEqual((game.status, game.termination_reason), ("finished", "inactivity"))
        self.assertEqual(game.phases.count(), 1)
        self.assertEqual(TokenEntry.objects.filter(game=game, kind="settlement").count(), 2)

    def test_last_moment_order_serializes_with_tenth_resolution(self):
        game, players, phase = self.playable()
        Game.objects.filter(pk=game.pk).update(inactive_phase_count=9)
        unit = Unit.objects.filter(owner=players[0]).first()
        statuses = self.parallel([
            lambda: self.post(self.users[0], f"/api/orders/games/{game.pk}/", {"unit_id": unit.pk, "order_type": "hold"}),
            lambda: resolve_movement_phase(GamePhase.objects.get(pk=phase.pk)),
        ])
        game.refresh_from_db()
        self.assertIn(statuses[0], (201, 404))
        self.assertEqual(game.status, "active" if statuses[0] == 201 else "finished")
        self.assertEqual(game.inactive_phase_count, 0 if statuses[0] == 201 else 10)
