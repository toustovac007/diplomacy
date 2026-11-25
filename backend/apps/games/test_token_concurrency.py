"""Actual PostgreSQL row-lock tests; never claim SQLite proves concurrency."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless

from django.db import connection, connections, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.games.models import Game, GamePlayer, GameStake
from apps.games.services.tokens import release_eliminated_stakes, settle_game
from apps.users.models import User, TokenEntry
from apps.users.tokens import process_token_refills, reserve_stake, wallet_snapshot


@skipUnless(connection.vendor == "postgresql", "Requires a live PostgreSQL test database")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", GAME_CREATE_COOLDOWN_SECONDS=0)
class TokenConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.users = [User.objects.create_user(username=f"tokenuser{i}", email=f"token{i}@example.test") for i in range(3)]

    def parallel(self, actions):
        barrier = Barrier(len(actions))
        def run(action):
            try:
                barrier.wait(timeout=10)
                return action()
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures = [pool.submit(run, action) for action in actions]
            return [future.result(timeout=30) for future in futures]

    def game(self, users, amount, *, finished=False):
        with transaction.atomic():
            game = Game.objects.create(name="Concurrent stakes", creator=users[0], token_stake=amount)
            players = []
            for user in users:
                player = GamePlayer.objects.create(game=game, user=user)
                reserve_stake(game, player)
                players.append(player)
            if finished:
                game.status, game.result_type, game.winner = "finished", "solo", players[0]
                game.save()
        return game

    def post(self, user, url, data=None):
        client = APIClient()
        client.force_authenticate(user)
        return client.post(url, data or {}, format="json").status_code

    def test_two_joins_to_different_games_cannot_double_spend(self):
        games = [self.game([creator], 800) for creator in self.users[1:]]
        joining = self.users[0]
        statuses = self.parallel([lambda game=game: self.post(joining, f"/api/games/{game.pk}/join/") for game in games])
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(wallet_snapshot(joining.pk)["available"], 200)
        self.assertEqual(wallet_snapshot(joining.pk)["frozen"], 800)
        self.assertEqual(GamePlayer.objects.filter(user=joining).count(), 1)

    def test_two_creations_cannot_double_spend(self):
        user = self.users[0]
        statuses = self.parallel([lambda: self.post(user, "/api/games/", {"name": "Create", "token_stake": 800})] * 2)
        self.assertEqual(sorted(statuses), [201, 409])
        self.assertEqual(Game.objects.count(), 1)
        self.assertEqual(wallet_snapshot(user.pk)["available"], 200)

    def test_creation_and_join_share_the_same_wallet_lock(self):
        user = self.users[0]
        game = self.game([self.users[1]], 800)
        statuses = self.parallel([
            lambda: self.post(user, "/api/games/", {"name": "Create", "token_stake": 800}),
            lambda: self.post(user, f"/api/games/{game.pk}/join/"),
        ])
        self.assertEqual(statuses.count(409), 1)
        self.assertEqual(sum(code in (200, 201) for code in statuses), 1)
        self.assertEqual(wallet_snapshot(user.pk)["available"], 200)
        self.assertEqual(wallet_snapshot(user.pk)["frozen"], 800)

    def test_simultaneous_settlements_pay_and_refill_only_once(self):
        game = self.game(self.users[:2], 1000, finished=True)
        self.parallel([lambda: settle_game(game.pk)] * 2)
        self.assertEqual(TokenEntry.objects.filter(kind="settlement").count(), 2)
        self.assertEqual(TokenEntry.objects.filter(kind="refill").count(), 1)
        self.assertEqual(wallet_snapshot(self.users[0].pk)["available"], 2000)
        self.assertEqual(wallet_snapshot(self.users[1].pk)["available"], 300)

    def test_two_games_with_opposite_winners_lock_users_in_consistent_order(self):
        games = [self.game(self.users[:2], 500, finished=True),
                 self.game(list(reversed(self.users[:2])), 500, finished=True)]
        self.parallel([lambda game=game: settle_game(game.pk) for game in games])
        for user in self.users[:2]:
            self.assertEqual(wallet_snapshot(user.pk)["available"], 1000)
            self.assertEqual(wallet_snapshot(user.pk)["frozen"], 0)
        self.assertFalse(TokenEntry.objects.filter(kind="refill").exists())

    def test_two_refill_workers_cannot_mint_twice(self):
        now = timezone.now()
        user = self.users[0]
        User.objects.filter(pk=user.pk).update(tokens_available=200,
            last_token_refill_at=now - timedelta(days=3), token_refill_due_at=now - timedelta(days=1))
        results = self.parallel([lambda: process_token_refills(now=now)] * 2)
        self.assertEqual(sum(results), 1)
        self.assertEqual(TokenEntry.objects.filter(user=user, kind="refill").count(), 1)
        self.assertEqual(wallet_snapshot(user.pk)["available"], 300)

    def test_elimination_racing_settlement_does_not_double_release(self):
        game = self.game(self.users[:2], 1000)
        Game.objects.filter(pk=game.pk).update(status="active")
        def finish():
            with transaction.atomic():
                locked = Game.objects.select_for_update().get(pk=game.pk)
                locked.status, locked.result_type = "finished", "solo"
                locked.winner = locked.players.get(user=self.users[0])
                locked.save()
                settle_game(locked.pk)
        self.parallel([lambda: release_eliminated_stakes(game), finish])
        self.assertFalse(GameStake.objects.filter(player__game=game).exclude(status="settled").exists())
        for user in self.users[:2]:
            deltas = sum(TokenEntry.objects.filter(user=user).values_list("frozen_delta", flat=True))
            self.assertEqual(deltas, 0)
        self.assertEqual(TokenEntry.objects.filter(kind="refill").count(), 1)
