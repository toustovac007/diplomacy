from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.games.models import Game, GamePlayer, GamePhase, Unit, SupplyCenterOwnership
from apps.maps.models import Province
from apps.games.services.phase_manager import create_phase, create_next_after_movement, create_next_after_retreat
from apps.games.services.victory import finish_game
from apps.games.services import draws
from apps.chats.services import create_conversation, send_message
from .models import EmailNotification, NotificationPreference
from .services import (send_phase_started_notifications, process_deadline_reminders, send_chat_message_notifications,
                       send_draw_notifications, send_game_finished_notifications, deadline_reminder_minutes)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", FRONTEND_BASE_URL="")
class NotificationTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_map", verbosity=0)
        cls.users = [get_user_model().objects.create_user(username=f"notify{i}", email=f"notify{i}@example.test") for i in range(4)]
        cls.game = Game.objects.create(name="Notification test", creator=cls.users[0], status="active")
        cls.players = [GamePlayer.objects.create(game=cls.game, user=user, country=country)
                       for user, country in zip(cls.users, ["ENG", "FRA", "GER", "ITA"])]
        for player, code in zip(cls.players[1:], ["PAR", "BUR", "ROM"]):
            Unit.objects.create(game=cls.game, owner=player, unit_type="army", province=Province.objects.get(code=code))
        cls.phase = GamePhase.objects.create(game=cls.game, sequence=1, year=1901, season="spring", phase_type="movement",
                                            deadline=timezone.now() + timedelta(days=1))

    def disable(self, user, field):
        preference, _ = NotificationPreference.objects.get_or_create(user=user)
        setattr(preference, field, False)
        preference.save(update_fields=[field])

    def recipients(self):
        return {message.to[0] for message in mail.outbox}

    def deadline(self, minutes, duration=1440):
        self.game.movement_duration_minutes = duration
        self.game.save(update_fields=["movement_duration_minutes"])
        self.phase.deadline = timezone.now() + timedelta(minutes=minutes)
        self.phase.save(update_fields=["deadline"])

    def direct(self):
        return create_conversation(self.players[1], "direct", [self.players[2].pk])[0]

    def proposal(self):
        return draws.propose(self.game.pk, self.users[1], [self.players[1].pk, self.players[2].pk])[0]

    def test_preference_defaults_lazy_and_own_api(self):
        self.assertEqual(NotificationPreference.objects.count(), 0)
        self.client.force_authenticate(self.users[0])
        data = self.client.get("/api/notifications/preferences/").data
        self.assertEqual(len(data), 5)
        self.assertTrue(all(data.values()))
        self.assertEqual(NotificationPreference.objects.count(), 1)
        response = self.client.patch("/api/notifications/preferences/", {"email_chat_message": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["email_chat_message"])
        self.client.force_authenticate(self.users[1])
        self.assertTrue(self.client.get("/api/notifications/preferences/").data["email_chat_message"])
        self.assertEqual(self.client.patch("/api/notifications/preferences/", {"user": self.users[0].pk}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/notifications/preferences/{self.users[0].pk}/", {}).status_code, 404)
        response = self.client.put("/api/notifications/preferences/", {key: False for key in data}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any(response.data.values()))
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/notifications/preferences/").status_code, 401)

    def test_phase_started_email_is_sent_once(self):
        send_phase_started_notifications(self.phase.pk)
        send_phase_started_notifications(self.phase.pk)
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(EmailNotification.objects.filter(event_type="phase_started", status="sent").count(), 4)
        with self.assertRaises(IntegrityError), transaction.atomic():
            EmailNotification.objects.create(recipient=self.users[0], event_type="phase_started", event_key=f"phase:{self.phase.pk}:started")

    def test_blank_invalid_email_and_disabled_phase_preference(self):
        for user, email in zip(self.users, ["", "invalid", "bad\r\n@example.test"]):
            user.email = email
            user.save(update_fields=["email"])
        self.disable(self.users[3], "email_phase_started")
        with self.captureOnCommitCallbacks(execute=True):
            phase = create_phase(self.game, 2, 1901, "fall", "movement")
        self.assertTrue(GamePhase.objects.filter(pk=phase.pk).exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_create_phase_registers_one_callback_and_correct_context(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            phase = create_phase(self.game, 2, 1901, "fall", "movement")
            self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(mail.outbox), 4)
        self.assertIn("Podzim 1901", mail.outbox[0].subject)
        self.assertIn("Notification test", mail.outbox[0].body)
        self.assertIn(timezone.localtime(phase.deadline).strftime("%H:%M"), mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, "text/html")
        self.assertNotIn(str(self.game.invite_code), mail.outbox[0].body)

    def test_phase_rollback_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                create_phase(self.game, 2, 1901, "fall", "movement")
                raise RuntimeError("rollback")
        self.assertEqual(len(mail.outbox), 0)

    def test_first_spring_start_uses_same_hook(self):
        game = Game.objects.create(name="New lobby", creator=self.users[0])
        for user in self.users[:2]:
            GamePlayer.objects.create(game=game, user=user)
        self.client.force_authenticate(self.users[0])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/api/games/{game.pk}/start/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(all("Jaro 1901" in message.subject for message in mail.outbox))

    def test_skipped_retreat_only_sends_next_movement(self):
        with self.captureOnCommitCallbacks(execute=True):
            phase = create_next_after_movement(self.phase, False)
        self.assertEqual(phase.phase_type, "movement")
        self.assertEqual(len(mail.outbox), 4)
        self.assertTrue(all("Pohyby" in message.body and "Ústupy" not in message.body for message in mail.outbox))

    def test_skipped_winter_only_sends_spring(self):
        self.phase.season = "fall"
        with patch("apps.games.services.phase_manager.get_adjustment_delta", return_value=0):
            with self.captureOnCommitCallbacks(execute=True):
                phase = create_next_after_retreat(self.phase)
        self.assertEqual(phase.season, "spring")
        self.assertEqual(len(mail.outbox), 4)
        self.assertTrue(all("Jaro 1902" in message.subject for message in mail.outbox))

    def test_real_retreat_and_adjustment_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            retreat = create_next_after_movement(self.phase, True)
        self.assertEqual(retreat.phase_type, "retreat")
        self.assertTrue(all("Ústupy" in message.body for message in mail.outbox))
        mail.outbox.clear()
        retreat.season = "fall"
        with self.captureOnCommitCallbacks(execute=True):
            winter = create_next_after_retreat(retreat)
        self.assertEqual(winter.phase_type, "adjustment")
        self.assertEqual(len(mail.outbox), 4)
        self.assertTrue(all("Úpravy jednotek" in message.body for message in mail.outbox))

    def test_deadline_reminder_is_sent_once(self):
        self.deadline(60)
        self.assertEqual(process_deadline_reminders(), 4)
        self.assertEqual(process_deadline_reminders(), 0)
        self.assertEqual(EmailNotification.objects.filter(event_type="deadline_reminder").count(), 4)

    def test_one_hour_phase_threshold_and_duration_selection(self):
        self.deadline(60, duration=60)
        self.assertEqual(process_deadline_reminders(), 0)
        self.deadline(16, duration=60)
        self.assertEqual(process_deadline_reminders(), 0)
        self.deadline(15, duration=60)
        self.assertEqual(process_deadline_reminders(), 4)
        self.game.retreat_duration_minutes = 60
        self.assertEqual(deadline_reminder_minutes(self.game, "retreat"), 15)
        self.assertEqual(deadline_reminder_minutes(self.game, "adjustment"), 60)

    def test_reminders_skip_resolved_cancelled_finished_expired_and_distant(self):
        for status in ["resolved", "cancelled"]:
            self.deadline(10)
            self.phase.status = status
            self.phase.save(update_fields=["status"])
            self.assertEqual(process_deadline_reminders(), 0)
        self.phase.status = "open"
        self.phase.save(update_fields=["status"])
        self.game.status = "finished"
        self.game.save(update_fields=["status"])
        self.assertEqual(process_deadline_reminders(), 0)
        self.game.status = "active"
        self.game.save(update_fields=["status"])
        for remaining in (-1, 61):
            self.deadline(remaining)
            self.assertEqual(process_deadline_reminders(), 0)

    def test_disabled_deadline_preference(self):
        self.deadline(30)
        self.disable(self.users[0], "email_deadline_reminder")
        self.assertEqual(process_deadline_reminders(), 3)
        self.assertNotIn(self.users[0].email, self.recipients())

    def test_smtp_failure_is_recorded_sanitized_and_not_retried(self):
        with patch("apps.notifications.services.EmailMultiAlternatives.send", side_effect=RuntimeError("SMTP password=SECRET")) as send:
            with self.assertLogs("apps.notifications.services", level="ERROR") as logs:
                send_phase_started_notifications(self.phase.pk)
            send_phase_started_notifications(self.phase.pk)
        self.assertEqual(send.call_count, 4)
        self.assertEqual(EmailNotification.objects.filter(status="failed", error="RuntimeError").count(), 4)
        self.assertNotIn("SECRET", " ".join(logs.output))

    def test_deadline_command_resolves_even_if_email_fails(self):
        self.deadline(-1)
        output = StringIO()
        with patch("apps.notifications.services.EmailMultiAlternatives.send", side_effect=RuntimeError("SMTP down")):
            with self.captureOnCommitCallbacks(execute=True):
                call_command("process_deadlines", stdout=output)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.status, "resolved")
        self.assertIn("Vyhodnoceno: 1", output.getvalue())
        self.assertIn("deadline připomínky", output.getvalue())
        self.assertTrue(EmailNotification.objects.filter(status="failed").exists())

    def test_chat_direct_privacy_sender_excluded_and_deduplicated(self):
        conversation = self.direct()
        with self.captureOnCommitCallbacks(execute=True):
            message = send_message(conversation, self.players[1], "Secret diplomacy")
        self.assertEqual(self.recipients(), {self.users[2].email})
        send_chat_message_notifications(message.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(self.users[0].email, self.recipients())

    def test_group_notifies_all_other_members_and_honors_preference(self):
        conversation = create_conversation(self.players[1], "group", [self.players[2].pk, self.players[3].pk], "Alliance")[0]
        with self.captureOnCommitCallbacks(execute=True):
            send_message(conversation, self.players[1], "Group")
        self.assertEqual(self.recipients(), {self.users[2].email, self.users[3].email})
        mail.outbox.clear()
        self.disable(self.users[2], "email_chat_message")
        with self.captureOnCommitCallbacks(execute=True):
            send_message(conversation, self.players[1], "Another")
        self.assertEqual(self.recipients(), {self.users[3].email})

    def test_chat_rollback_no_email(self):
        conversation = self.direct()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                send_message(conversation, self.players[1], "Rollback")
                raise RuntimeError()
        self.assertEqual(len(mail.outbox), 0)

    def test_chat_html_escaped_plain_text_intact_and_optional_url(self):
        conversation = self.direct()
        text = '<script>alert("x")</script>\nSecond line'
        with override_settings(FRONTEND_BASE_URL="https://diplomacy.example/"):
            with self.captureOnCommitCallbacks(execute=True):
                send_message(conversation, self.players[1], text)
        email = mail.outbox[0]
        self.assertIn(text, email.body)
        self.assertNotIn("<script>", email.alternatives[0].content)
        self.assertIn("&lt;script&gt;", email.alternatives[0].content)
        self.assertIn(f"https://diplomacy.example/games/{self.game.pk}", email.body)
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            send_message(conversation, self.players[1], "No URL")
        self.assertNotIn("href=", mail.outbox[0].alternatives[0].content)

    def test_created_draw_only_other_snapshotted_voters(self):
        with self.captureOnCommitCallbacks(execute=True):
            proposal = self.proposal()
        self.assertEqual(self.recipients(), {self.users[2].email, self.users[3].email})
        self.assertIn("jednomyslný", mail.outbox[0].body)
        send_draw_notifications(proposal.pk, "draw_created")
        self.assertEqual(len(mail.outbox), 2)

    def test_draw_disabled_preference(self):
        self.disable(self.users[2], "email_draw_events")
        with self.captureOnCommitCallbacks(execute=True):
            self.proposal()
        self.assertEqual(self.recipients(), {self.users[3].email})

    def test_rejected_and_cancelled_draw_notifies_voters(self):
        proposal = self.proposal()
        with self.captureOnCommitCallbacks(execute=True):
            draws.vote(self.game.pk, proposal.pk, self.users[2], "reject")
        self.assertEqual(self.recipients(), {u.email for u in self.users[1:]})
        self.assertTrue(all("zamítnut" in m.subject for m in mail.outbox))
        mail.outbox.clear()
        proposal = self.proposal()
        with self.captureOnCommitCallbacks(execute=True):
            draws.cancel(self.game.pk, proposal.pk, self.users[1])
        self.assertEqual(len(mail.outbox), 3)
        self.assertTrue(all("zrušen" in m.subject for m in mail.outbox))

    def test_accepted_draw_only_one_final_email_per_player(self):
        proposal = self.proposal()
        with self.captureOnCommitCallbacks(execute=True):
            draws.vote(self.game.pk, proposal.pk, self.users[2], "accept")
            draws.vote(self.game.pk, proposal.pk, self.users[3], "accept")
        self.assertEqual(len(mail.outbox), 4)
        self.assertEqual(self.recipients(), {u.email for u in self.users})
        self.assertTrue(all("dohodou" in m.subject and "Francie" in m.body and "Německo" in m.body for m in mail.outbox))
        self.assertEqual(process_deadline_reminders(), 0)
        self.assertEqual(send_phase_started_notifications(self.phase.pk), 0)
        self.assertSetEqual(set(EmailNotification.objects.values_list("event_type", flat=True)), {"game_finished"})

    def test_solo_finish_all_players_once_with_winner(self):
        with self.captureOnCommitCallbacks(execute=True):
            finish_game(self.game, self.players[1])
        send_game_finished_notifications(self.game.pk)
        self.assertEqual(len(mail.outbox), 4)
        self.assertTrue(all("vítěz Francie" in m.subject for m in mail.outbox))
        self.assertTrue(all("notify1" in m.body for m in mail.outbox))

    def test_fall_solo_transition_sends_finish_not_phantom_phase(self):
        self.phase.season = "fall"
        with patch("apps.games.services.phase_manager.find_solo_winner", return_value=self.players[1]):
            with self.captureOnCommitCallbacks(execute=True):
                result = create_next_after_retreat(self.phase)
        self.assertIsNone(result)
        self.assertEqual(len(mail.outbox), 4)
        self.assertFalse(EmailNotification.objects.filter(event_type="phase_started").exists())

    def test_finish_preference_and_blank_address(self):
        self.disable(self.users[1], "email_game_finished")
        self.users[2].email = ""
        self.users[2].save(update_fields=["email"])
        with self.captureOnCommitCallbacks(execute=True):
            finish_game(self.game, self.players[1])
        self.assertEqual(self.recipients(), {self.users[0].email, self.users[3].email})

    def test_finish_and_draw_rollback_no_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                finish_game(self.game, self.players[1])
                raise RuntimeError()
        self.assertEqual(len(mail.outbox), 0)
        self.game.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                self.proposal()
                raise RuntimeError()
        self.assertEqual(len(mail.outbox), 0)

    def test_smtp_failure_does_not_undo_chat_draw_or_finish(self):
        conversation = self.direct()
        with patch("apps.notifications.services.EmailMultiAlternatives.send", side_effect=RuntimeError("failure")):
            with self.captureOnCommitCallbacks(execute=True):
                message = send_message(conversation, self.players[1], "Saved despite SMTP")
            self.assertTrue(conversation.messages.filter(pk=message.pk).exists())
            with self.captureOnCommitCallbacks(execute=True):
                proposal = self.proposal()
            with self.captureOnCommitCallbacks(execute=True):
                draws.vote(self.game.pk, proposal.pk, self.users[2], "accept")
                draws.vote(self.game.pk, proposal.pk, self.users[3], "accept")
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, "finished")
        self.assertTrue(EmailNotification.objects.filter(status="failed").exists())

    def test_final_draw_vote_rollback_sends_no_final_result(self):
        proposal = self.proposal()
        draws.vote(self.game.pk, proposal.pk, self.users[2], "accept")
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                draws.vote(self.game.pk, proposal.pk, self.users[3], "accept")
                raise RuntimeError("rollback after finish")
        self.game.refresh_from_db()
        proposal.refresh_from_db()
        self.assertEqual(self.game.status, "active")
        self.assertEqual(proposal.status, "open")
        self.assertEqual(len(mail.outbox), 0)


class NotificationMigrationTests(TransactionTestCase):
    def test_legacy_deliveries_preserved_and_suppress_replay(self):
        from django.conf import settings
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        before = [("notifications", "0001_initial"), ("games", "0011_draw_voting")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            user = apps.get_model(settings.AUTH_USER_MODEL).objects.create(username="legacyemail", email="legacy@example.test")
            game = apps.get_model("games", "Game").objects.create(name="Legacy", creator_id=user.pk, status="active")
            apps.get_model("games", "GamePlayer").objects.create(game_id=game.pk, user_id=user.pk, country="FRA")
            phase = apps.get_model("games", "GamePhase").objects.create(game_id=game.pk, sequence=1, year=1901,
                season="spring", phase_type="movement", deadline=timezone.now() + timedelta(hours=1))
            legacy = apps.get_model("notifications", "PhaseNotification")
            for event in ("phase_started", "deadline_reminder"):
                legacy.objects.create(phase_id=phase.pk, user_id=user.pk, notification_type=event)
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(EmailNotification.objects.filter(status="sent").count(), 2)
            self.assertEqual(send_phase_started_notifications(phase.pk), 0)
            self.assertEqual(process_deadline_reminders(), 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
