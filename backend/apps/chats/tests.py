from datetime import timedelta
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.test import TransactionTestCase
from rest_framework.test import APITestCase

from apps.games.models import Game, GamePlayer, GamePhase
from .models import ChatConversation, ChatMembership, ChatMessage


class ChatTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = [get_user_model().objects.create_user(username=f"chat{i}", email=f"chat{i}@example.test") for i in range(5)]
        cls.game = Game.objects.create(name="Diplomacy", creator=cls.users[0], status="active")
        cls.players = [GamePlayer.objects.create(game=cls.game, user=user, country=country)
                       for user, country in zip(cls.users[:4], ["ENG", "FRA", "GER", "ITA"])]
        cls.other_game = Game.objects.create(name="Elsewhere", creator=cls.users[0], status="active")
        cls.foreign = GamePlayer.objects.create(game=cls.other_game, user=cls.users[0], country="RUS")
        cls.phase = GamePhase.objects.create(game=cls.game, sequence=1, year=1901, season="spring",
                                            phase_type="movement", deadline=timezone.now() + timedelta(days=1))

    def setUp(self):
        self.client.force_authenticate(self.users[1])
        self.base = f"/api/games/{self.game.pk}/chats/"

    def create(self, ids=None, kind="direct", **extra):
        return self.client.post(self.base, {"conversation_type": kind,
            "participant_ids": ids if ids is not None else [self.players[2].pk], **extra}, format="json")

    def conversation(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def messages_url(self, cid):
        return f"{self.base}{cid}/messages/"

    def send(self, cid, text="  Podpoříš mě?  ", **extra):
        return self.client.post(self.messages_url(cid), {"text": text, **extra}, format="json")

    def test_direct_contains_exact_pair_and_reverse_is_idempotent(self):
        cid = self.conversation()
        self.assertSetEqual(set(ChatMembership.objects.filter(conversation_id=cid).values_list("player_id", flat=True)),
                            {self.players[1].pk, self.players[2].pk})
        self.client.force_authenticate(self.users[2])
        response = self.create([self.players[1].pk])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], cid)
        self.assertEqual(ChatConversation.objects.count(), 1)

    def test_database_prevents_duplicate_pair_and_membership(self):
        cid = self.conversation()
        conversation = ChatConversation.objects.get(pk=cid)
        self.assertEqual(conversation.direct_key, ":".join(map(str, sorted([self.players[1].pk, self.players[2].pk]))))
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChatConversation.objects.create(game=self.game, conversation_type="direct", direct_key=conversation.direct_key,
                                            created_by=self.players[2])
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChatMembership.objects.create(conversation=conversation, player=self.players[1])

    def test_invalid_participants(self):
        for ids in ([], [self.players[1].pk], [self.foreign.pk], [99999], [self.players[2].pk, self.players[3].pk],
                    [self.players[2].pk, self.players[2].pk]):
            with self.subTest(ids=ids):
                self.assertEqual(self.create(ids).status_code, 400)
        self.assertEqual(ChatConversation.objects.count(), 0)

    def test_group_membership_title_and_multiple_groups(self):
        ids = [self.players[0].pk, self.players[2].pk]
        response = self.create(ids, "group", title="  Severní aliance  ")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["title"], "Severní aliance")
        self.assertEqual(len(response.data["participants"]), 3)
        self.assertIsNone(ChatConversation.objects.get(pk=response.data["id"]).direct_key)
        self.assertEqual(self.create(ids, "group", title="  ").status_code, 201)
        self.assertEqual(ChatConversation.objects.count(), 2)

    def test_group_rejects_too_few_duplicates_self_foreign_and_long_title(self):
        for ids in ([self.players[2].pk], [self.players[2].pk, self.players[2].pk],
                    [self.players[1].pk, self.players[2].pk], [self.foreign.pk, self.players[2].pk]):
            self.assertEqual(self.create(ids, "group").status_code, 400)
        self.assertEqual(self.create([self.players[0].pk, self.players[2].pk], "group", title="x" * 101).status_code, 400)

    def test_creator_winner_and_outsiders_cannot_access_private_chat(self):
        cid = self.conversation()
        self.send(cid)
        self.game.winner = self.players[0]
        self.game.save(update_fields=["winner"])
        for user in (self.users[0], self.users[3], self.users[4]):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user)
                listing = self.client.get(self.base)
                if user == self.users[4]:
                    self.assertEqual(listing.status_code, 404)
                else:
                    self.assertEqual(listing.data, [])
                self.assertEqual(self.client.get(f"{self.base}{cid}/").status_code, 404)
                self.assertEqual(self.client.get(self.messages_url(cid)).status_code, 404)
                self.assertEqual(self.send(cid).status_code, 404)
                self.assertEqual(self.client.post(f"{self.base}{cid}/read/").status_code, 404)

    def test_other_game_route_cannot_expose_conversation(self):
        cid = self.conversation()
        self.client.force_authenticate(self.users[0])
        foreign_base = f"/api/games/{self.other_game.pk}/chats/{cid}/"
        for path in (foreign_base, foreign_base + "messages/"):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post(foreign_base + "messages/", {"text": "x"}).status_code, 404)
        self.assertEqual(self.client.post(foreign_base + "read/").status_code, 404)

    def test_send_uses_authenticated_player_and_snapshots_phase(self):
        cid = self.conversation()
        response = self.send(cid, sender=self.players[0].pk, phase=999, sender_username="forged")
        self.assertEqual(response.status_code, 201, response.data)
        message = ChatMessage.objects.get()
        self.assertEqual(message.sender, self.players[1])
        self.assertEqual(message.text, "Podpoříš mě?")
        self.assertEqual((message.sender_username, message.sender_country, message.sender_country_name), ("chat1", "FRA", "Francie"))
        self.assertEqual(message.phase, self.phase)
        self.assertEqual(response.data["phase"]["season_name"], "Jaro")
        self.assertEqual(ChatConversation.objects.get(pk=cid).updated_at, message.created_at)

    def test_empty_and_overlong_messages_rejected(self):
        cid = self.conversation()
        for text in ("", " \n\t ", "x" * 4001):
            self.assertEqual(self.send(cid, text).status_code, 400)
        self.assertEqual(self.send(cid, "x" * 4000).status_code, 201)

    def test_html_and_newlines_stored_as_plain_text(self):
        cid = self.conversation()
        text = '<script>alert("x")</script>\nDruhý řádek'
        self.assertEqual(self.send(cid, text).data["text"], text)

    def test_waiting_cannot_create_or_send(self):
        cid = self.conversation()
        self.game.status = "waiting"
        self.game.save(update_fields=["status"])
        self.assertEqual(self.create().status_code, 400)
        self.assertEqual(self.send(cid).status_code, 404)

    def test_finished_history_read_and_mark_allowed_writes_denied(self):
        cid = self.conversation()
        self.send(cid)
        self.game.status = "finished"
        self.game.save(update_fields=["status"])
        self.assertEqual(self.client.get(self.base).data[0]["id"], cid)
        self.assertEqual(self.client.get(f"{self.base}{cid}/").status_code, 200)
        self.assertEqual(len(self.client.get(self.messages_url(cid)).data["results"]), 1)
        self.assertEqual(self.client.post(f"{self.base}{cid}/read/").status_code, 204)
        self.assertEqual(self.send(cid).status_code, 400)
        self.assertEqual(self.create().status_code, 400)

    def test_eliminated_player_can_chat(self):
        self.assertFalse(self.game.units.exists())
        cid = self.conversation()
        self.assertEqual(self.send(cid).status_code, 201)

    def test_list_last_message_activity_and_unread(self):
        cid = self.conversation()
        other = self.create([self.players[0].pk]).data["id"]
        self.send(cid, "First")
        self.assertEqual(self.client.get(self.base).data[0]["unread_count"], 0)
        self.client.force_authenticate(self.users[2])
        listing = self.client.get(self.base).data
        self.assertEqual([row["id"] for row in listing], [cid])
        self.assertEqual(listing[0]["unread_count"], 1)
        self.assertEqual(listing[0]["last_message"]["text"], "First")
        self.assertNotIn("messages", listing[0])
        self.send(cid, "Reply")
        self.assertEqual(self.client.get(self.base).data[0]["unread_count"], 1)
        self.client.post(f"{self.base}{cid}/read/")
        self.assertEqual(self.client.get(self.base).data[0]["unread_count"], 0)
        self.client.force_authenticate(self.users[1])
        self.assertEqual([row["id"] for row in self.client.get(self.base).data], [cid, other])
        self.assertEqual(self.client.get(self.base).data[0]["unread_count"], 1)
        self.send(cid, "New")
        self.client.force_authenticate(self.users[2])
        self.assertEqual(self.client.get(self.base).data[0]["unread_count"], 1)

    def test_cursor_pagination_newest_first_stable_when_new_message_arrives(self):
        from urllib.parse import urlsplit
        cid = self.conversation()
        ChatMessage.objects.bulk_create([ChatMessage(conversation_id=cid, sender=self.players[1], text=str(i),
            sender_username="chat1", sender_country="FRA", sender_country_name="Francie") for i in range(55)])
        first = self.client.get(self.messages_url(cid)).data
        self.assertEqual(len(first["results"]), 50)
        self.assertEqual(first["results"][0]["text"], "54")
        self.send(cid, "New")
        url = urlsplit(first["next"])
        second = self.client.get(url.path + "?" + url.query).data
        self.assertEqual([m["text"] for m in second["results"]], ["4", "3", "2", "1", "0"])
        self.assertIsNone(second["next"])

    def test_phase_changes_and_sender_removal_keep_history(self):
        cid = self.conversation()
        self.send(cid, "Spring")
        self.phase.status = "resolved"
        self.phase.save(update_fields=["status"])
        fall = GamePhase.objects.create(game=self.game, sequence=2, year=1901, season="fall", phase_type="movement",
                                       deadline=timezone.now() + timedelta(days=1))
        self.send(cid, "Fall")
        self.users[1].username = "renamed"
        self.users[1].save(update_fields=["username"])
        self.players[1].delete()
        self.client.force_authenticate(self.users[2])
        messages = self.client.get(self.messages_url(cid)).data["results"]
        self.assertEqual([m["phase"]["id"] for m in messages], [fall.pk, self.phase.pk])
        self.assertEqual([m["sender_username"] for m in messages], ["chat1", "chat1"])
        self.assertIsNone(messages[0]["sender"])
        fall.delete()
        self.assertIsNone(self.client.get(self.messages_url(cid)).data["results"][0]["phase"])

    def test_immutable_api_and_no_leak_through_game_serializer(self):
        cid = self.conversation()
        mid = self.send(cid).data["id"]
        self.assertEqual(self.client.patch(f"{self.base}{cid}/", {"participant_ids": [self.players[0].pk]}).status_code, 405)
        self.assertEqual(self.client.delete(f"{self.base}{cid}/").status_code, 405)
        self.assertEqual(self.client.patch(self.messages_url(cid), {"text": "edit"}).status_code, 405)
        self.assertEqual(self.client.delete(self.messages_url(cid)).status_code, 405)
        self.assertEqual(self.client.delete(f"{self.messages_url(cid)}{mid}/").status_code, 404)
        self.client.force_authenticate(self.users[0])
        data = self.client.get(f"/api/games/{self.game.pk}/").data
        self.assertFalse({"chats", "chat_conversations", "messages", "memberships"} & data.keys())

    def test_unauthenticated_access_denied(self):
        cid = self.conversation()
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.base).status_code, 401)
        self.assertEqual(self.client.get(self.messages_url(cid)).status_code, 401)


class ConcurrentDirectChatTests(TransactionTestCase):
    def test_simultaneous_reverse_creations_return_one_complete_conversation(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections
        from .services import create_conversation
        users = [get_user_model().objects.create_user(username=f"parallel{i}", email=f"parallel{i}@example.test") for i in range(2)]
        game = Game.objects.create(name="Concurrent", creator=users[0], status="active")
        players = [GamePlayer.objects.create(game=game, user=user, country=country) for user, country in zip(users, ["FRA", "ENG"])]
        barrier = Barrier(2)

        def create(index):
            try:
                barrier.wait(timeout=5)
                conversation, created = create_conversation(players[index], "direct", [players[1 - index].pk])
                return conversation.pk, created
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(create, [0, 1]))
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(created for _, created in results), [False, True])
        self.assertEqual(ChatConversation.objects.count(), 1)
        self.assertEqual(ChatMembership.objects.count(), 2)
