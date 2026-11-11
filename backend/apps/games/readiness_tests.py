from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
import os
import runpy
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient

from apps.games.models import Game, GamePhase, GamePlayer, PhaseReadiness, SupplyCenterOwnership, Unit
from apps.games.services.deadlines import process_expired_phases
from apps.games.services.draws import propose, vote
from apps.games.services.supply_centers import initialize_supply_centers
from apps.maps.models import Province
from apps.orders.models import Order, AdjustmentOrder
from apps.orders.services.adjudication import resolve_movement_phase
from apps.orders.services.adjustments import resolve_adjustment_phase


def fixture():
    call_command("seed_map", verbosity=0)
    users = [get_user_model().objects.create_user(username=name, email=f"{name}@example.test")
             for name in ("ready_france", "ready_england", "ready_germany")]
    game = Game.objects.create(name="Readiness", creator=users[0], status="active")
    players = [GamePlayer.objects.create(game=game, user=user, country=country)
               for user, country in zip(users, ("FRA", "ENG", "GER"))]
    phase = GamePhase.objects.create(game=game, sequence=1, year=1901, season="spring",
                                    phase_type="movement", deadline=timezone.now() + timedelta(days=1))
    return game, players, phase


@override_settings(ALLOW_MANUAL_PHASE_RESOLVE=False)
class ReadinessTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.game, cls.players, cls.phase = fixture()

    def setUp(self):
        self.url = f"/api/games/{self.game.pk}/readiness/"
        self.orders_url = f"/api/orders/games/{self.game.pk}/"
        self.client.force_authenticate(self.players[0].user)

    def unit(self, index, code, **kwargs):
        return Unit.objects.create(game=self.game, owner=self.players[index],
                                   province=Province.objects.get(code=code), unit_type="army", **kwargs)

    def ready(self, index=0, value=True):
        self.client.force_authenticate(self.players[index].user)
        return self.client.post(self.url, {"ready": value}, format="json")

    def winter(self):
        self.phase.phase_type = "adjustment"
        self.phase.season = "winter"
        self.phase.save()
        initialize_supply_centers(self.game)

    def test_required_counts_own_missing_orders_privacy_and_no_center_requirement(self):
        first = self.unit(0, "PAR")
        self.unit(0, "BUR")
        self.unit(1, "LON")
        self.unit(2, "MUN", is_dislodged=True)
        self.assertFalse(SupplyCenterOwnership.objects.filter(owner=self.players[0]).exists())
        self.assertEqual(self.client.post(self.orders_url, {"unit_id": first.pk, "order_type": "hold"}).status_code, 201)
        data = self.client.get(self.url).data
        self.assertEqual((data["required_count"], data["ready_count"], data["missing_order_count"]), (2, 0, 1))
        self.assertEqual(set(data), {"game_status", "phase", "readiness_supported", "is_required", "is_ready",
                                   "ready_count", "required_count", "missing_order_count", "builds_remaining",
                                   "disbands_remaining", "phase_resolved", "next_phase_id"})
        self.assertTrue(self.ready().data["is_ready"])
        self.client.force_authenticate(self.players[1].user)
        other = self.client.get(self.url).data
        self.assertEqual((other["ready_count"], other["missing_order_count"], other["is_ready"]), (1, 1, False))
        self.client.force_authenticate(self.players[2].user)
        self.assertFalse(self.client.get(self.url).data["is_required"])
        self.assertEqual(self.ready(2).status_code, 400)

    def test_ready_missing_orders_no_default_rows_deadline_unchanged_unready_unlocks(self):
        unit = self.unit(0, "PAR")
        self.unit(1, "LON")
        deadline = self.phase.deadline
        self.assertEqual(self.ready().status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.deadline, deadline)
        # Every Movement order goes through the same lock before validation.
        for kind in ("hold", "move", "support", "convoy"):
            response = self.client.post(self.orders_url, {"unit_id": unit.pk, "order_type": kind})
            self.assertEqual(response.status_code, 400)
            self.assertIn("Nejdřív zruš připravenost", response.data["detail"])
        self.assertFalse(self.ready(value=False).data["is_ready"])
        row = PhaseReadiness.objects.get(phase=self.phase, player=self.players[0])
        self.assertIsNone(row.ready_at)
        self.assertEqual(self.client.post(self.orders_url, {"unit_id": unit.pk, "order_type": "hold"}).status_code, 201)
        self.ready()
        self.assertEqual(self.client.post(self.orders_url, {"unit_id": unit.pk, "order_type": "move", "target": "BUR"}).status_code, 400)
        self.assertEqual(Order.objects.get(unit=unit).order_type, "hold")

    def test_last_ready_calls_existing_resolver_defaults_holds_skips_retreat_and_resets(self):
        self.unit(0, "PAR")
        self.unit(1, "LON")
        self.ready()
        with patch("apps.orders.services.adjudication.resolve_movement_phase", wraps=resolve_movement_phase) as resolver:
            response = self.ready(1)
            resolver.assert_called_once()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["phase_resolved"])
        self.assertEqual(response.data["resolved_phase_id"], self.phase.pk)
        next_phase = GamePhase.objects.get(pk=response.data["next_phase_id"])
        self.assertEqual((next_phase.phase_type, next_phase.season), ("movement", "fall"))
        self.assertEqual(Order.objects.filter(phase=self.phase, order_type="hold", is_default=True).count(), 2)
        self.assertEqual(self.client.get(self.url).data["ready_count"], 0)
        self.assertEqual(PhaseReadiness.objects.filter(phase=self.phase, is_ready=True).count(), 2)

    def test_last_ready_creates_retreat_from_supported_attack(self):
        attacker = self.unit(0, "BUR")
        supporter = self.unit(0, "RUH")
        self.unit(1, "BEL")
        for payload in ({"unit_id": attacker.pk, "order_type": "move", "target": "BEL"},
                        {"unit_id": supporter.pk, "order_type": "support", "supported_unit_id": attacker.pk, "support_target": "BEL"}):
            response = self.client.post(self.orders_url, payload)
            self.assertEqual(response.status_code, 201, response.data)
        self.ready()
        response = self.ready(1)
        self.assertEqual(GamePhase.objects.get(pk=response.data["next_phase_id"]).phase_type, "retreat")

    def test_fall_skip_or_create_winter_uses_normal_transition(self):
        for balanced in (True, False):
            with self.subTest(balanced=balanced):
                self.phase.season = "fall"
                self.phase.status = "open"
                self.phase.save()
                self.game.phases.exclude(pk=self.phase.pk).delete()
                PhaseReadiness.objects.all().delete()
                Unit.objects.all().delete()
                initialize_supply_centers(self.game)
                for index, codes in enumerate((("PAR", "MAR", "BRE"), ("LON", "EDI", "LVP"), ("MUN", "BER", "KIE"))):
                    for code in codes if balanced else codes[:1]:
                        self.unit(index, code)
                self.ready(0)
                self.ready(1)
                response = self.ready(2)
                next_phase = GamePhase.objects.get(pk=response.data["next_phase_id"])
                self.assertEqual(next_phase.phase_type, "movement" if balanced else "adjustment")
                self.assertEqual(next_phase.season, "spring" if balanced else "winter")

    def test_solo_finish_through_readiness(self):
        self.phase.season = "fall"
        self.phase.save()
        self.unit(0, "PAR")
        initialize_supply_centers(self.game)
        for ownership in self.game.supply_center_ownerships.all()[:18]:
            ownership.owner = self.players[0]
            ownership.save()
        # Include PAR even if it was outside the first 18.
        self.game.supply_center_ownerships.filter(province__code="PAR").update(owner=self.players[0])
        response = self.ready()
        self.assertTrue(response.data["phase_resolved"])
        self.assertEqual(response.data["game_status"], "finished")
        self.assertIsNone(response.data["next_phase_id"])

    def test_adjustment_optional_builds_delta_zero_and_ready_lock_cancel(self):
        self.winter()
        for code in ("BER", "MUN", "KIE"):
            self.unit(2, code)
        self.client.force_authenticate(self.players[2].user)
        self.assertFalse(self.client.get(self.url).data["is_required"])
        self.client.force_authenticate(self.players[0].user)
        url = self.orders_url + "adjustments/"
        build = self.client.post(url, {"order_type": "build", "unit_type": "army", "province": "PAR"})
        self.assertEqual(build.status_code, 201, build.data)
        response = self.ready()
        self.assertEqual((response.data["builds_remaining"], response.data["required_count"]), (2, 2))
        self.assertEqual(self.client.post(url, {"order_type": "build", "unit_type": "army", "province": "MAR"}).status_code, 400)
        self.assertEqual(self.client.delete(f"{url}{build.data['id']}/").status_code, 400)
        self.ready(value=False)
        self.assertEqual(self.client.delete(f"{url}{build.data['id']}/").status_code, 204)
        self.ready()
        with patch("apps.orders.services.adjustments.resolve_adjustment_phase", wraps=resolve_adjustment_phase) as resolver:
            response = self.ready(1)  # Both can explicitly waive every optional build.
            resolver.assert_called_once()
        self.assertTrue(response.data["phase_resolved"])
        self.assertFalse(self.players[0].units.exists())

    def test_adjustment_mandatory_disband_build_results_and_locks(self):
        self.winter()
        units = [self.unit(0, code) for code in ("PAR", "MAR", "BRE", "BUR")]
        response = self.ready()
        self.assertEqual(response.status_code, 400)
        self.assertIn("DISBAND", response.data["detail"])
        url = self.orders_url + "adjustments/"
        order = self.client.post(url, {"order_type": "disband", "unit_id": units[0].pk})
        self.assertEqual(order.status_code, 201, order.data)
        self.assertTrue(self.ready().data["is_ready"])
        self.assertEqual(self.client.post(url, {"order_type": "disband", "unit_id": units[1].pk}).status_code, 400)
        self.assertEqual(self.client.delete(f"{url}{order.data['id']}/").status_code, 400)
        self.client.force_authenticate(self.players[1].user)
        self.assertEqual(self.client.post(url, {"order_type": "build", "unit_type": "fleet", "province": "LON"}).status_code, 201)
        self.ready(1)
        self.assertTrue(self.ready(2).data["phase_resolved"])
        self.assertFalse(Unit.objects.filter(pk=units[0].pk).exists())
        self.assertEqual(self.players[1].units.get().unit_type, "fleet")

    def test_retreat_unsupported_and_auto_completion_ignores_old_readiness(self):
        self.phase.phase_type = "retreat"
        self.phase.save()
        unit = self.unit(0, "BUR", is_dislodged=True)
        PhaseReadiness.objects.create(phase=self.phase, player=self.players[0], is_ready=True)
        self.assertFalse(self.client.get(self.url).data["readiness_supported"])
        self.assertEqual(self.ready().status_code, 400)
        response = self.client.post(self.orders_url + "retreats/", {"unit_id": unit.pk, "order_type": "disband"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["phase_resolved"])

    def test_deadline_resolves_unready_with_missing_holds(self):
        self.unit(0, "PAR")
        self.unit(1, "LON")
        self.ready()
        results = process_expired_phases(now=self.phase.deadline + timedelta(seconds=1))
        self.assertEqual(results[0]["status"], "resolved")
        self.assertEqual(Order.objects.filter(phase=self.phase, is_default=True).count(), 2)

    def test_draw_cancels_ready_phase_no_adjudication_and_terminal_get(self):
        self.unit(0, "PAR")
        self.unit(1, "LON")
        self.ready()
        proposal, _ = propose(self.game.pk, self.players[0].user, [p.pk for p in self.players[:2]])
        vote(self.game.pk, proposal.pk, self.players[1].user, "accept")
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.status, "cancelled")
        self.assertIsNone(self.phase.resolved_orders_snapshot)
        self.assertEqual(self.ready(1).status_code, 400)
        data = self.client.get(self.url).data
        self.assertEqual(data["game_status"], "finished")
        self.assertIsNone(data["phase"])
        self.assertFalse(data["readiness_supported"])

    def test_no_open_phase_cannot_be_mutated(self):
        for phase_status in ("cancelled", "resolved"):
            self.phase.status = phase_status
            self.phase.save()
            self.assertEqual(self.ready().status_code, 404)
        self.assertFalse(PhaseReadiness.objects.exists())

    def test_participant_only_strict_payload_no_creator_override(self):
        self.unit(0, "PAR")
        for data in ({"ready": True, "player_id": self.players[1].pk}, {"ready": True, "phase_id": self.phase.pk},
                     {"ready": "true"}, {"ready": 1}, {}):
            self.assertEqual(self.client.post(self.url, data, format="json").status_code, 400)
        outsider = get_user_model().objects.create_user(username="outsider")
        self.client.force_authenticate(outsider)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {"ready": True}, format="json").status_code, 404)

    def test_manual_disabled_all_endpoints_and_capability(self):
        for endpoint in ("resolve", "resolve-retreat", "resolve-adjustment"):
            self.assertEqual(self.client.post(self.orders_url + endpoint + "/").status_code, 403)
        self.assertFalse(self.client.get(f"/api/games/{self.game.pk}/").data["manual_resolve_allowed"])

    def test_manual_setting_defaults_and_safe_environment_override(self):
        settings_path = Path(__file__).resolve().parents[2] / "config" / "settings.py"
        for debug, override, expected in (("true", None, True), ("false", None, False),
                                          ("true", "false", False), ("false", " YES ", True),
                                          ("false", "0", False)):
            with self.subTest(debug=debug, override=override), patch.dict(os.environ, {
                "DJANGO_DEBUG": debug, "DJANGO_SECRET_KEY": "test-only-readiness-settings-key" * 3,
                "DJANGO_ALLOWED_HOSTS": "game.example", "FRONTEND_BASE_URL": "https://game.example",
                "POSTGRES_DB": "settings_test", "POSTGRES_USER": "settings_test", "POSTGRES_PASSWORD": "test-only",
            }, clear=True):
                os.environ.pop("ALLOW_MANUAL_PHASE_RESOLVE", None)
                if override is not None:
                    os.environ["ALLOW_MANUAL_PHASE_RESOLVE"] = override
                self.assertEqual(runpy.run_path(str(settings_path))["ALLOW_MANUAL_PHASE_RESOLVE"], expected)

    def test_retreat_and_adjustment_deadline_fallback_with_manual_disabled(self):
        self.phase.phase_type = "retreat"
        self.phase.save()
        unit = self.unit(0, "BUR", is_dislodged=True)
        self.assertEqual(process_expired_phases(now=self.phase.deadline)[0]["status"], "resolved")
        self.assertFalse(Unit.objects.filter(pk=unit.pk).exists())
        self.phase = self.game.phases.get(status="open")
        self.winter()
        for code in ("PAR", "MAR", "BRE", "BUR"):
            self.unit(0, code)
        self.assertEqual(process_expired_phases(now=self.phase.deadline)[0]["status"], "resolved")
        self.assertEqual(self.players[0].units.count(), 3)

    @override_settings(ALLOW_MANUAL_PHASE_RESOLVE=True)
    def test_manual_enabled_creator_only_all_endpoints_and_capability(self):
        for phase_type, endpoint, season in (("movement", "resolve", "spring"), ("retreat", "resolve-retreat", "spring"),
                                            ("adjustment", "resolve-adjustment", "winter")):
            self.game.phases.exclude(pk=self.phase.pk).delete()
            self.phase.status = "open"
            self.phase.phase_type = phase_type
            self.phase.season = season
            self.phase.save()
            self.client.force_authenticate(self.players[1].user)
            self.assertFalse(self.client.get(f"/api/games/{self.game.pk}/").data["manual_resolve_allowed"])
            self.assertEqual(self.client.post(self.orders_url + endpoint + "/").status_code, 403)
            self.client.force_authenticate(self.players[0].user)
            self.assertTrue(self.client.get(f"/api/games/{self.game.pk}/").data["manual_resolve_allowed"])
            response = self.client.post(self.orders_url + endpoint + "/")
            self.assertEqual(response.status_code, 200, response.data)


class ReadinessRaceTests(TransactionTestCase):
    def test_ready_and_order_write_serialize_or_fail_without_late_mutation(self):
        game, players, phase = fixture()
        unit = Unit.objects.create(game=game, owner=players[0], unit_type="army", province=Province.objects.get(code="PAR"))
        Unit.objects.create(game=game, owner=players[1], unit_type="army", province=Province.objects.get(code="LON"))
        barrier = Barrier(2)

        def send(ready):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(players[0].user)
                barrier.wait(timeout=10)
                url = f"/api/games/{game.pk}/readiness/" if ready else f"/api/orders/games/{game.pk}/"
                data = {"ready": True} if ready else {"unit_id": unit.pk, "order_type": "hold"}
                return client.post(url, data, format="json").status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(send, (True, False)))
        self.assertIn(results[0], (200, 503))
        self.assertIn(results[1], (201, 400, 503))
        self.assertTrue(results[0] == 200 or results[1] == 201)
        ready = PhaseReadiness.objects.filter(phase=phase, is_ready=True).first()
        order = Order.objects.filter(phase=phase).first()
        if ready and order:
            self.assertLessEqual(order.updated_at, ready.ready_at)
        # A write definitely arriving after Ready is always rejected.
        client = APIClient()
        client.force_authenticate(players[0].user)
        self.assertEqual(client.post(f"/api/games/{game.pk}/readiness/", {"ready": True}, format="json").status_code, 200)
        self.assertEqual(client.post(f"/api/orders/games/{game.pk}/", {"unit_id": unit.pk, "order_type": "move", "target": "BUR"}).status_code, 400)
