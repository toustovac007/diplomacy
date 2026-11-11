from django.core.exceptions import ValidationError
from django.db import models


class ChatConversation(models.Model):
    game = models.ForeignKey("games.Game", on_delete=models.CASCADE, related_name="chat_conversations")
    conversation_type = models.CharField(max_length=10, choices=[("direct", "Direct"), ("group", "Group")])
    title = models.CharField(max_length=100, blank=True, default="")
    created_by = models.ForeignKey("games.GamePlayer", null=True, on_delete=models.SET_NULL, related_name="created_chats")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    direct_key = models.CharField(max_length=50, null=True, blank=True, editable=False)
    participants = models.ManyToManyField("games.GamePlayer", through="ChatMembership", related_name="chats")

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["game", "direct_key"], name="unique_direct_chat_pair"),
            models.CheckConstraint(condition=(
                models.Q(conversation_type="direct", direct_key__isnull=False)
                | models.Q(conversation_type="group", direct_key__isnull=True)
            ), name="chat_type_matches_direct_key"),
        ]

    def clean(self):
        super().clean()
        if self.created_by_id and self.created_by.game_id != self.game_id:
            raise ValidationError("Zakladatel musí být hráčem této hry.")


class ChatMembership(models.Model):
    conversation = models.ForeignKey(ChatConversation, on_delete=models.CASCADE, related_name="memberships")
    player = models.ForeignKey("games.GamePlayer", on_delete=models.CASCADE, related_name="chat_memberships")
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "player"], name="unique_chat_membership")]

    def clean(self):
        super().clean()
        if self.player.game_id != self.conversation.game_id:
            raise ValidationError("Účastník musí být hráčem stejné hry.")


class ChatMessage(models.Model):
    conversation = models.ForeignKey(ChatConversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey("games.GamePlayer", null=True, on_delete=models.SET_NULL, related_name="chat_messages")
    text = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)
    phase = models.ForeignKey("games.GamePhase", null=True, blank=True, on_delete=models.SET_NULL, related_name="chat_messages")
    sender_username = models.CharField(max_length=150, editable=False)
    sender_country = models.CharField(max_length=20, blank=True, editable=False)
    sender_country_name = models.CharField(max_length=100, blank=True, editable=False)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["conversation", "-id"], name="chat_message_history")]
