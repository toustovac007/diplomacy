from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.core.cache import cache
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from apps.users.email_verification import mark_verified
from .models import Game, GamePlayer


def make_user(username):
    user = User.objects.create_user(username=username, email=f"{username}@example.test", password="Bamboo!river83-moon")
    mark_verified(user)
    return user


def existing_games(user, count, status="waiting"):
    games = [Game.objects.create(name=f"Existing {number}", creator=user, status=status) for number in range(count)]
    Game.objects.filter(pk__in=[game.pk for game in games]).update(created_at=timezone.now()-timedelta(days=1))
    return games


@override_settings(GAME_CREATE_COOLDOWN_SECONDS=10, GAME_MAX_OPEN_CREATED=10)
class GameCreationSecurityTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = make_user("creator")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer "+str(RefreshToken.for_user(self.user).access_token))

    def create(self, **data):
        return self.client.post("/api/games/", {"name":"Test", **data}, format="json")

    def test_success_then_cooldown_with_retry_after_and_exact_boundary(self):
        start = timezone.now()
        with patch("apps.games.services.creation.timezone.now", return_value=start):
            first = self.create()
            second = self.create()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second["Retry-After"], "10")
        self.assertEqual(Game.objects.count(), 1)
        self.assertEqual(GamePlayer.objects.get().user, self.user)
        cache.clear()
        with patch("apps.games.services.creation.timezone.now", return_value=start+timedelta(seconds=9.5)):
            response = self.create()
        self.assertEqual(response.status_code,429)
        self.assertEqual(response["Retry-After"],"1")
        with patch("apps.games.services.creation.timezone.now", return_value=start+timedelta(seconds=10)):
            self.assertEqual(self.create().status_code,201)

    def test_waiting_and_active_count_together_finished_and_other_creators_do_not(self):
        existing_games(self.user,6)
        active = existing_games(self.user,4,"active")
        existing_games(self.user,12,"finished")
        other = make_user("other")
        joined = existing_games(other,12)
        GamePlayer.objects.create(game=joined[0],user=self.user)
        response = self.create()
        self.assertEqual(response.status_code,409)
        self.assertIn("10",str(response.data))
        Game.objects.filter(pk=active[0].pk).update(status="finished")
        self.assertEqual(self.create(status="finished",creator=other.username).status_code,201)
        self.assertEqual(Game.objects.filter(creator=self.user,status__in=["waiting","active"]).count(),10)

    @override_settings(GAME_CREATE_COOLDOWN_SECONDS=0)
    def test_script_of_one_hundred_requests_cannot_create_more_than_ten_games(self):
        statuses=[self.create(name=f"Burst {number}").status_code for number in range(100)]
        self.assertEqual(statuses.count(201),10)
        self.assertEqual(statuses.count(409),90)
        self.assertEqual(Game.objects.count(),10)
        self.assertEqual(GamePlayer.objects.count(),10)

    def test_existing_over_limit_account_keeps_data_and_can_still_join(self):
        existing_games(self.user,12)
        self.assertEqual(self.create().status_code,409)
        self.assertEqual(Game.objects.filter(creator=self.user).count(),12)
        other=make_user("other")
        game=existing_games(other,1)[0]
        self.assertEqual(self.client.post(f"/api/games/{game.pk}/join/").status_code,200)

    def test_completed_or_deleted_game_does_not_reset_cooldown(self):
        self.assertEqual(self.create().status_code,201)
        Game.objects.all().delete()
        self.assertEqual(self.create().status_code,429)
        self.assertEqual(Game.objects.count(),0)

    def test_recent_legacy_game_without_timestamp_is_respected(self):
        Game.objects.create(name="Legacy",creator=self.user)
        self.assertIsNone(self.user.last_game_created_at)
        self.assertEqual(self.create().status_code,429)

    def test_cooldown_is_per_creator_not_shared_between_accounts(self):
        self.assertEqual(self.create().status_code,201)
        other=make_user("independent")
        self.client.credentials(HTTP_AUTHORIZATION="Bearer "+str(RefreshToken.for_user(other).access_token))
        self.assertEqual(self.create().status_code,201)

    def test_membership_failure_rolls_back_game_and_cooldown(self):
        with patch("apps.games.services.creation.GamePlayer.objects.create",side_effect=RuntimeError("test failure")):
            with self.assertRaises(RuntimeError):
                self.create()
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_game_created_at)
        self.assertEqual(Game.objects.count(),0)
        self.assertEqual(self.create().status_code,201)

    def test_invalid_inputs_do_not_consume_creation_budget(self):
        for name in ("", " "*5, "x"*101, "A\nB", "A\x00B", "A\u202eB"):
            response=self.create(name=name)
            self.assertEqual(response.status_code,400)
            self.assertIn("name",response.data)
        self.assertEqual(self.create(name="Žluťoučká aliance " + "x"*82).status_code,201)


@skipUnless(connection.vendor=="postgresql","Requires a live PostgreSQL test database")
@override_settings(GAME_CREATE_COOLDOWN_SECONDS=10,GAME_MAX_OPEN_CREATED=10)
class CreationConcurrencyTests(TransactionTestCase):
    def parallel(self,user):
        barrier=Barrier(2)
        def create(_):
            try:
                client=APIClient()
                client.force_authenticate(user)
                barrier.wait(timeout=10)
                return client.post('/api/games/',{'name':'Parallel'},format='json').status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(create,range(2)))

    def test_two_requests_cannot_spend_the_last_slot(self):
        user=make_user("parallel")
        existing_games(user,9)
        self.assertEqual(sorted(self.parallel(user)),[201,409])
        self.assertEqual(Game.objects.filter(creator=user).count(),10)
        self.assertEqual(GamePlayer.objects.filter(user=user).count(),1)

    def test_two_requests_cannot_bypass_cooldown(self):
        user=make_user("parallel")
        self.assertEqual(sorted(self.parallel(user)),[201,429])
        self.assertEqual(Game.objects.count(),1)
