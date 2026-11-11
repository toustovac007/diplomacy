from django.db.models import Count, F, Q, Prefetch
from django.shortcuts import get_object_or_404
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.games.models import GamePlayer
from .models import ChatConversation
from .serializers import ConversationSerializer, CreateConversationSerializer, MessageSerializer, SendMessageSerializer
from .services import create_conversation, send_message, mark_read


class ChatPagination(CursorPagination):
    page_size = 50
    ordering = "-id"


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    def player(self, request, game_id):
        return get_object_or_404(GamePlayer.objects.select_related("game", "user"), game_id=game_id, user=request.user)

    def conversations(self, player):
        # Membership is the only access grant, including for game creators/winners.
        return ChatConversation.objects.filter(game_id=player.game_id, memberships__player=player).annotate(
            unread_count=Count("messages", filter=(
                (Q(memberships__last_read_at__isnull=True) | Q(messages__created_at__gt=F("memberships__last_read_at")))
                & ~Q(messages__sender=player)
            )),
        ).prefetch_related(Prefetch("participants", queryset=GamePlayer.objects.select_related("user")))

    def conversation(self, player, conversation_id):
        return get_object_or_404(self.conversations(player), pk=conversation_id, game__status__in=["active", "finished"])


class ConversationList(ChatView):
    def get(self, request, game_id):
        player = self.player(request, game_id)
        conversations = self.conversations(player).filter(game__status__in=["active", "finished"])
        return Response(ConversationSerializer(conversations, many=True).data)

    def post(self, request, game_id):
        player = self.player(request, game_id)
        serializer = CreateConversationSerializer(data=request.data, context={"player": player})
        serializer.is_valid(raise_exception=True)
        conversation, created = create_conversation(player, **serializer.validated_data)
        return Response(ConversationSerializer(self.conversation(player, conversation.pk)).data, status=201 if created else 200)


class ConversationDetail(ChatView):
    def get(self, request, game_id, conversation_id):
        return Response(ConversationSerializer(self.conversation(self.player(request, game_id), conversation_id)).data)


class Messages(ChatView):
    def get(self, request, game_id, conversation_id):
        conversation = self.conversation(self.player(request, game_id), conversation_id)
        paginator = ChatPagination()
        messages = paginator.paginate_queryset(conversation.messages.select_related("phase"), request, view=self)
        return paginator.get_paginated_response(MessageSerializer(messages, many=True).data)

    def post(self, request, game_id, conversation_id):
        player = self.player(request, game_id)
        conversation = self.conversation(player, conversation_id)
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = send_message(conversation, player, **serializer.validated_data)
        return Response(MessageSerializer(message).data, status=201)


class ReadConversation(ChatView):
    def post(self, request, game_id, conversation_id):
        player = self.player(request, game_id)
        conversation = self.conversation(player, conversation_id)
        mark_read(conversation, player)
        return Response(status=204)
