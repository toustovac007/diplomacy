from rest_framework import serializers

from apps.games.models import GamePhase
from apps.games.serializer import GamePlayerSerializer
from .models import ChatConversation, ChatMessage


class PhaseSerializer(serializers.ModelSerializer):
    season_name = serializers.CharField(source="get_season_display")
    phase_type_name = serializers.CharField(source="get_phase_type_display")

    class Meta:
        model = GamePhase
        fields = ("id", "sequence", "year", "season", "season_name", "phase_type", "phase_type_name")


class MessageSerializer(serializers.ModelSerializer):
    phase = PhaseSerializer(read_only=True)

    class Meta:
        model = ChatMessage
        fields = ("id", "sender", "sender_username", "sender_country", "sender_country_name", "text", "created_at", "phase")
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    participants = GamePlayerSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.IntegerField(read_only=True)

    def get_last_message(self, conversation):
        message = conversation.messages.only("id", "text", "sender_country", "created_at").first()
        if not message:
            return None
        return {"id": message.pk, "text": message.text, "sender_country": message.sender_country,
                "created_at": message.created_at.isoformat()}

    class Meta:
        model = ChatConversation
        fields = ("id", "conversation_type", "title", "participants", "created_at", "updated_at", "last_message", "unread_count")


class CreateConversationSerializer(serializers.Serializer):
    conversation_type = serializers.ChoiceField(choices=["direct", "group"])
    participant_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=6)
    title = serializers.CharField(max_length=100, required=False, allow_blank=True, default="", trim_whitespace=True)

    def validate(self, data):
        ids = data["participant_ids"]
        player = self.context["player"]
        if len(set(ids)) != len(ids) or player.pk in ids:
            raise serializers.ValidationError("Vyber ostatní hráče bez duplicit.")
        expected = len(ids) == 1 if data["conversation_type"] == "direct" else len(ids) >= 2
        if not expected:
            raise serializers.ValidationError("Přímý chat vyžaduje jednoho dalšího hráče, skupina alespoň dva.")
        if player.game.players.filter(pk__in=ids).count() != len(ids):
            raise serializers.ValidationError("Všichni účastníci musí být hráči této hry.")
        return data


class SendMessageSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4000, trim_whitespace=True, allow_blank=False)
