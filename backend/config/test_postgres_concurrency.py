"""Live PostgreSQL regressions: explicitly skipped on SQLite, never emulated."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from apps.games.readiness_tests import fixture
from apps.games.models import GamePhase, Unit
from apps.games.services.draws import propose, vote
from apps.maps.models import Province
from apps.orders.services.adjudication import resolve_movement_phase, AdjudicationError
from apps.users.models import User, OAuthFlow
from apps.users import oauth


@skipUnless(connection.vendor == "postgresql", "Requires a live PostgreSQL test database")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.game, self.players, self.phase = fixture()

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

    def post(self, user, endpoint, data=None):
        client = APIClient()
        client.force_authenticate(user)
        return client.post(f"/api/games/{self.game.pk}/{endpoint}/", data or {}, format="json").status_code

    def waiting(self):
        self.game.phases.all().delete()
        self.game.status, self.game.max_players = "waiting", 4
        self.game.save()

    def units(self):
        for player, code in zip(self.players, ("PAR", "LON", "BER")):
            Unit.objects.create(game=self.game, owner=player, province=Province.objects.get(code=code), unit_type="army")

    def test_two_joins_cannot_take_the_same_last_slot(self):
        self.waiting()
        users = [User.objects.create_user(username=f"joining{i}", email=f"joining{i}@example.test") for i in range(2)]
        statuses = self.parallel([lambda user=user: self.post(user, "join") for user in users])
        self.assertEqual(sorted(statuses), [200, 400])
        self.assertEqual(self.game.players.count(), 4)

    def test_start_serializes_with_join(self):
        self.waiting()
        user = User.objects.create_user(username="joining", email="joining@example.test")
        statuses = self.parallel([lambda: self.post(self.players[0].user, "start"), lambda: self.post(user, "join")])
        self.assertEqual(statuses[0], 200)
        self.assertIn(statuses[1], (200, 400))
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "active")
        self.assertLessEqual(self.game.players.count(), 4)
        self.assertFalse(self.game.players.filter(country=None).exists())
        self.assertEqual(self.game.phases.count(), 1)

    def test_simultaneous_final_ready_requests_resolve_once(self):
        self.units()
        self.assertEqual(self.post(self.players[0].user, "readiness", {"ready": True}), 200)
        statuses = self.parallel([lambda player=player: self.post(player.user, "readiness", {"ready": True})
                                  for player in self.players[1:]])
        self.assertEqual(statuses, [200, 200])
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.status, "resolved")
        self.assertEqual(self.game.phases.filter(sequence=2).count(), 1)

    def test_same_phase_cannot_resolve_twice(self):
        self.units()

        def resolve():
            try:
                resolve_movement_phase(GamePhase.objects.get(pk=self.phase.pk))
                return True
            except AdjudicationError:
                return False

        self.assertEqual(sorted(self.parallel([resolve, resolve])), [False, True])
        self.assertEqual(self.game.phases.count(), 2)

    def test_concurrent_final_draw_votes_finish_once(self):
        self.units()
        proposal, _ = propose(self.game.pk, self.players[0].user, [p.pk for p in self.players])
        self.parallel([lambda player=player: vote(self.game.pk, proposal.pk, player.user, "accept")
                       for player in self.players[1:]])
        self.game.refresh_from_db()
        proposal.refresh_from_db()
        self.assertEqual((self.game.status, self.game.result_type, proposal.status), ("finished", "draw", "accepted"))
        self.assertEqual(self.game.draw_participants.count(), 3)
        self.assertEqual(proposal.votes.filter(vote="accept").count(), 3)

    def test_oauth_flow_consumed_only_once(self):
        flow = OAuthFlow.objects.create(provider="google", state_digest=oauth.digest("test-state"),
            code_verifier="test-verifier", nonce="test-nonce", intent="login",
            binding_digest=oauth.digest("test-browser"), expires_at=timezone.now() + timedelta(minutes=5))

        def consume():
            try:
                oauth.consume_flow("google", "test-state", {oauth.cookie_name(flow): "test-browser"})
                return True
            except oauth.OAuthFailure:
                return False

        self.assertEqual(sorted(self.parallel([consume, consume])), [False, True])
