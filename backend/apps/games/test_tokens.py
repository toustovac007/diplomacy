from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.db.models import Sum
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.games.models import Game, GamePlayer, GameStake, SupplyCenterOwnership, Unit
from apps.games.services.phase_manager import create_phase
from apps.games.services.tokens import release_eliminated_stakes, settle_game
from apps.games.services.victory import finish_game
from apps.maps.models import Province
from apps.users.models import User, TokenEntry
from apps.users.tokens import process_token_refills, reserve_stake, wallet_snapshot


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", GAME_CREATE_COOLDOWN_SECONDS=0)
class TokenTests(TestCase):
    def user(self, name):
        email = name + "@example.test"
        return User.objects.create_user(username=name, email=email,
            email_verified_at=timezone.now(), email_verified_for=email)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def game(self, count=3, stake=100, scoring="dss", *, users=None, status="active"):
        users = users or [self.user(f"player{User.objects.count() + i}") for i in range(count)]
        with transaction.atomic():
            game = Game.objects.create(name="Token game", creator=users[0], token_stake=stake,
                                        scoring=scoring, status=status)
            players = []
            for user in users:
                player = GamePlayer.objects.create(game=game, user=user)
                reserve_stake(game, player)
                players.append(player)
        return game, players

    def centers(self, player, count):
        for index in range(count):
            province = Province.objects.create(code=f"{Province.objects.count() + 1:03X}", name=f"Test center {player.pk} {index}",
                                                province_type="inland", is_supply_center=True)
            SupplyCenterOwnership.objects.create(game=player.game, province=province, owner=player)

    def test_initial_grant_for_regular_and_oauth_style_accounts(self):
        normal = self.user("normal")
        oauth = User(username="social", email="social@example.test")
        oauth.set_unusable_password()
        oauth.save()
        for user in (normal, oauth):
            self.assertEqual(wallet_snapshot(user.pk)["total"], 1000)
            user.save()
            self.assertEqual(wallet_snapshot(user.pk)["available"], 1000)

    def test_create_reserves_creator_stake_and_ignores_forged_pot(self):
        user = self.user("creator")
        response = self.client_for(user).post("/api/games/", {
            "name": "Sázky", "token_stake": 800, "scoring": "sos", "token_pot": 99999,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["token_pot"], 800)
        self.assertEqual(response.data["scoring"], "sos")
        self.assertEqual((wallet_snapshot(user.pk)["available"], wallet_snapshot(user.pk)["frozen"]), (200, 800))
        self.assertEqual(TokenEntry.objects.get(user=user).available_delta, -800)

    def test_insufficient_creation_rolls_back_membership_pot_and_cooldown(self):
        user = self.user("poor")
        response = self.client_for(user).post("/api/games/", {"name": "Too much", "token_stake": 1500})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Game.objects.count(), 0)
        self.assertEqual(GamePlayer.objects.count(), 0)
        self.assertEqual(GameStake.objects.count(), 0)
        self.assertEqual(TokenEntry.objects.count(), 0)
        user.refresh_from_db()
        self.assertIsNone(user.last_game_created_at)
        self.assertEqual(user.tokens_available, 1000)

    def test_stake_and_scoring_choices_are_enforced(self):
        client = self.client_for(self.user("choices"))
        for data in ({"token_stake": 0}, {"token_stake": -100}, {"token_stake": 101},
                     {"token_stake": 100.5}, {"token_stake": True}, {"scoring": "bogus"}):
            response = client.post("/api/games/", {"name": "Invalid", **data}, format="json")
            self.assertEqual(response.status_code, 400, data)
        self.assertFalse(Game.objects.exists())

    def test_join_reserves_once_and_duplicate_is_not_charged(self):
        game, _ = self.game(count=2, stake=500, status="waiting")
        user = self.user("joiner")
        client = self.client_for(user)
        url = f"/api/games/{game.pk}/join/"
        self.assertEqual(client.post(url).status_code, 200)
        self.assertEqual(client.post(url).status_code, 400)
        self.assertEqual(wallet_snapshot(user.pk)["available"], 500)
        self.assertEqual(wallet_snapshot(user.pk)["frozen"], 500)
        game.refresh_from_db()
        self.assertEqual(game.token_pot, 1500)
        self.assertEqual(TokenEntry.objects.filter(user=user, kind="stake").count(), 1)

    def test_private_code_join_checks_funds_and_numeric_id_stays_private(self):
        game, _ = self.game(count=2, stake=800, status="waiting")
        game.is_public = False
        game.save()
        user = self.user("privatejoin")
        User.objects.filter(pk=user.pk).update(tokens_available=700)
        client = self.client_for(user)
        self.assertEqual(client.post(f"/api/games/{game.pk}/join/").status_code, 404)
        response = client.post("/api/games/join-by-code/", {"invite_code": str(game.invite_code)})
        self.assertEqual(response.status_code, 409)
        self.assertFalse(game.players.filter(user=user).exists())
        self.assertEqual(wallet_snapshot(user.pk)["available"], 700)

    def test_public_join_insufficient_funds_rolls_back(self):
        game, _ = self.game(count=2, stake=1000, status="waiting")
        user = self.user("publicpoor")
        User.objects.filter(pk=user.pk).update(tokens_available=999)
        response = self.client_for(user).post(f"/api/games/{game.pk}/join/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(game.players.count(), 2)
        self.assertEqual(wallet_snapshot(user.pk)["frozen"], 0)

    def test_ranked_solo_pays_whole_pot_and_repeated_settlement_is_inert(self):
        for scoring in ("dss", "sos"):
            game, players = self.game(scoring=scoring)
            finish_game(game, players[0])
            before = list(User.objects.values_list("pk", "tokens_available"))
            entries = TokenEntry.objects.count()
            settle_game(game.pk)
            self.assertEqual(list(User.objects.values_list("pk", "tokens_available")), before)
            self.assertEqual(TokenEntry.objects.count(), entries)
            self.assertEqual([wallet_snapshot(p.user_id)["available"] for p in players], [1200, 900, 900])
            self.assertFalse(GameStake.objects.filter(player__game=game, status="locked").exists())
            self.assertIsNotNone(Game.objects.get(pk=game.pk).tokens_settled_at)

    def test_stale_finish_cannot_change_a_settled_result(self):
        game, players = self.game()
        stale = Game.objects.get(pk=game.pk)
        finish_game(game, players[0])
        with self.assertRaises(ValueError):
            finish_game(stale, players[1])
        self.assertEqual(Game.objects.get(pk=game.pk).winner_id, players[0].pk)

    def test_dss_splits_only_selected_winners_remainder_to_strongest(self):
        game, players = self.game(count=4)
        self.centers(players[0], 1)
        self.centers(players[1], 3)
        self.centers(players[2], 2)
        finish_game(game, draw_participants=players[:3])
        self.assertEqual(list(GameStake.objects.filter(player__game=game).order_by("player_id")
                              .values_list("payout", flat=True)), [133, 134, 133, 0])

    def test_sos_uses_squared_centers_and_all_remainder_goes_to_strongest(self):
        game, players = self.game(scoring="sos")
        for player, count in zip(players, (3, 2, 1)):
            self.centers(player, count)
        finish_game(game, draw_participants=players)
        self.assertEqual(list(GameStake.objects.filter(player__game=game).order_by("player_id")
                              .values_list("payout", flat=True)), [194, 85, 21])

    def test_sos_zero_center_draw_is_equal_and_ties_are_deterministic(self):
        game, players = self.game(count=3, scoring="sos")
        finish_game(game, draw_participants=players[:2])
        self.assertEqual(list(GameStake.objects.filter(player__game=game).order_by("player_id")
                              .values_list("payout", flat=True)), [150, 150, 0])

    def test_unranked_refunds_everyone_even_after_elimination_and_solo(self):
        game, players = self.game(stake=1000, scoring="unranked")
        release_eliminated_stakes(game)
        self.assertEqual(wallet_snapshot(players[1].user_id)["frozen"], 1000)
        finish_game(game, players[0])
        for player in players:
            self.assertEqual(wallet_snapshot(player.user_id)["available"], 1000)
        self.assertFalse(TokenEntry.objects.filter(kind="refill").exists())

    def test_eliminated_stake_stays_in_pot_without_early_refill_or_double_forfeit(self):
        game, players = self.game(stake=1000)
        self.centers(players[0], 1)
        release_eliminated_stakes(game)
        release_eliminated_stakes(game)
        game.refresh_from_db()
        self.assertEqual(game.token_pot, 3000)
        self.assertEqual(wallet_snapshot(players[1].user_id)["total"], 0)
        self.assertIsNone(wallet_snapshot(players[1].user_id)["refill_due_at"])
        self.assertEqual(TokenEntry.objects.filter(kind="forfeit").count(), 2)
        finish_game(game, players[0])
        self.assertEqual(GameStake.objects.filter(player__game=game).aggregate(n=Sum("payout"))["n"], 3000)
        self.assertEqual(wallet_snapshot(players[0].user_id)["available"], 3000)
        self.assertEqual(wallet_snapshot(players[1].user_id)["available"], 300)

    def test_center_or_any_unit_including_dislodged_prevents_elimination(self):
        game, players = self.game(count=4)
        self.centers(players[0], 1)
        for player, dislodged in zip(players[1:3], (False, True)):
            province = Province.objects.create(code=f"{Province.objects.count() + 1:03X}", name=f"Unit {player.pk}", province_type="inland")
            Unit.objects.create(game=game, owner=player, unit_type="army", province=province,
                                is_dislodged=dislodged)
        create_phase(game, 1, 1901, "spring", "movement")
        self.assertEqual(list(GameStake.objects.filter(player__game=game).order_by("player_id")
                              .values_list("status", flat=True)), ["locked", "locked", "locked", "forfeited"])

    def test_refill_immediate_then_delayed_48_hours_and_idempotent(self):
        now = timezone.now()
        game, players = self.game(count=2, stake=1000)
        with patch("apps.games.services.tokens.timezone.now", return_value=now):
            finish_game(game, players[0])
        loser = players[1].user
        self.assertEqual(wallet_snapshot(loser.pk)["available"], 300)
        second, again = self.game(stake=100, users=[loser, players[0].user])
        with patch("apps.games.services.tokens.timezone.now", return_value=now + timedelta(hours=1)):
            finish_game(second, again[1])
        self.assertEqual(wallet_snapshot(loser.pk)["available"], 200)
        self.assertEqual(wallet_snapshot(loser.pk)["refill_due_at"], now + timedelta(days=2))
        self.assertEqual(process_token_refills(now=now + timedelta(hours=47)), 0)
        self.assertEqual(process_token_refills(now=now + timedelta(hours=48)), 1)
        self.assertEqual(process_token_refills(now=now + timedelta(hours=48)), 0)
        loser.refresh_from_db()
        self.assertEqual(loser.tokens_available, 300)
        self.assertEqual(loser.last_token_refill_at, now + timedelta(hours=48))
        self.assertEqual(list(TokenEntry.objects.filter(user=loser, kind="refill")
                              .values_list("available_delta", flat=True)), [300, 100])

    def test_refill_counts_frozen_tokens_and_does_not_consume_cooldown_when_unneeded(self):
        user, other = self.user("pending"), self.user("other")
        self.game(stake=200, users=[user, other])
        last = timezone.now() - timedelta(days=3)
        User.objects.filter(pk=user.pk).update(tokens_available=100, last_token_refill_at=last,
                                               token_refill_due_at=last + timedelta(days=2))
        self.assertEqual(process_token_refills(), 0)
        user.refresh_from_db()
        self.assertIsNone(user.token_refill_due_at)
        self.assertEqual(user.last_token_refill_at, last)
        self.assertEqual(wallet_snapshot(user.pk)["total"], 300)

    def test_other_game_winnings_cancel_pending_refill(self):
        user, opponent = self.user("recovered"), self.user("opponent")
        game, players = self.game(stake=100, users=[user, opponent])
        last = timezone.now()
        User.objects.filter(pk=user.pk).update(tokens_available=100, last_token_refill_at=last,
                                               token_refill_due_at=last + timedelta(days=2))
        finish_game(game, players[0])
        user.refresh_from_db()
        self.assertEqual(user.tokens_available, 300)
        self.assertIsNone(user.token_refill_due_at)
        self.assertEqual(user.last_token_refill_at, last)

    def test_mismatched_pot_rolls_back_entire_finish(self):
        game, players = self.game()
        Game.objects.filter(pk=game.pk).update(token_pot=301)
        with self.assertRaises(ValueError):
            finish_game(game, players[0])
        game.refresh_from_db()
        self.assertEqual(game.status, "active")
        self.assertIsNone(game.tokens_settled_at)
        self.assertFalse(TokenEntry.objects.filter(kind="settlement").exists())

    def test_ranking_is_top_ten_total_wealth_and_excludes_unverified_accounts(self):
        users = [self.user(f"rank{i}") for i in range(12)]
        for index, user in enumerate(users):
            User.objects.filter(pk=user.pk).update(tokens_available=1000 + index)
        self.game(stake=800, users=users[-2:])
        User.objects.create_user(username="unverified", email="unknown@example.test", tokens_available=99999)
        client = self.client_for(users[0])
        response = client.get("/api/users/ranking/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 10)
        self.assertEqual([row["username"] for row in response.data], [u.username for u in reversed(users[2:])])
        self.assertEqual(response.data[0]["total"], 1011)
        self.assertEqual(response.data[0]["frozen"], 800)
        self.assertNotIn("email", response.data[0])
        self.assertEqual(client.get("/api/users/tokens/").data["total"], 1000)

    def test_anonymous_and_unverified_accounts_cannot_read_wallet_or_ranking(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        unverified = User.objects.create_user(username="pendingmail", email="pendingmail@example.test")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer " + str(RefreshToken.for_user(unverified).access_token))
        for url in ("/api/users/tokens/", "/api/users/ranking/"):
            self.assertEqual(APIClient().get(url).status_code, 401)
            self.assertEqual(client.get(url).status_code, 401)

    def test_ledger_reconciles_accounts_and_settled_pot(self):
        game, players = self.game(stake=1000)
        self.centers(players[0], 1)
        release_eliminated_stakes(game)
        finish_game(game, players[0])
        for player in players:
            snapshot = wallet_snapshot(player.user_id)
            entries = TokenEntry.objects.filter(user_id=player.user_id)
            self.assertEqual(snapshot["available"], 1000 + sum(entries.values_list("available_delta", flat=True)))
            self.assertEqual(snapshot["frozen"], sum(entries.values_list("frozen_delta", flat=True)))
        self.assertEqual(sum(GameStake.objects.filter(player__game=game).values_list("payout", flat=True)), 3000)


class TokenMigrationTests(TransactionTestCase):
    def test_existing_account_gets_one_initial_grant_and_new_account_gets_default(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        before = [("games", "0013_phase_readiness"), ("users", "0004_game_creation_cooldown")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(before)
        try:
            old_user = executor.loader.project_state(before).apps.get_model("users", "User")
            existing = old_user.objects.create(username="beforetokens", email="beforetokens@example.test")
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            migrated_user = executor.loader.project_state(latest).apps.get_model("users", "User")
            existing = migrated_user.objects.get(pk=existing.pk)
            self.assertEqual(existing.tokens_available, 1000)
            self.assertIsNone(existing.last_token_refill_at)
            self.assertIsNone(existing.token_refill_due_at)
            existing.tokens_available = 650
            existing.save()
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(migrated_user.objects.get(pk=existing.pk).tokens_available, 650)
            new_user = migrated_user.objects.create(username="aftertokens", email="aftertokens@example.test")
            self.assertEqual(new_user.tokens_available, 1000)
        finally:
            MigrationExecutor(connection).migrate(latest)
