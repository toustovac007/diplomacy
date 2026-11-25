from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Game, GamePlayer, GamePhase
from .serializer import GameSerializer, PublicGameSerializer, JoinByCodeSerializer
from apps.users.tokens import reserve_stake
from .services.lifecycle import cancel_waiting_game
from .services.phase_lock import phase_transaction

import random


from .services.game_setup import create_starting_units

from apps.games.services.supply_centers import (
    initialize_supply_centers,
)

from .services.phase_manager import (
    create_phase,
)

class GameListCreateView(generics.ListCreateAPIView):
    serializer_class = GameSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Game.objects
            .filter(players__user=self.request.user)
            .distinct()
            .prefetch_related("players__user", "players__token_reservation")
            .order_by("-created_at")
        )


class PublicGameListView(generics.ListAPIView):
    serializer_class = PublicGameSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Game.objects
            .filter(status="waiting", is_public=True)
            .exclude(players__user=self.request.user)
            .distinct()
            .prefetch_related("players__user", "players__token_reservation")
            .order_by("-created_at")
        )


class JoinGameView(APIView):
    permission_classes = [IsAuthenticated]

    def get_game(self, request, game_id):
        return get_object_or_404(
            Game.objects.select_for_update(),
            id=game_id, is_public=True,
        )

    @transaction.atomic
    def post(self, request, game_id=None):
        game = self.get_game(request, game_id)

        if game.status != "waiting":
            return Response(
                {"detail": "Do této hry už se nelze připojit."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if GamePlayer.objects.filter(
            game=game,
            user=request.user
        ).exists():
            return Response(
                {"detail": "V této hře už jsi."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if game.players.count() >= game.max_players:
            return Response(
                {"detail": "Hra je plná."},
                status=status.HTTP_400_BAD_REQUEST
            )

        player = GamePlayer.objects.create(
            game=game,
            user=request.user
        )
        reserve_stake(game, player)

        serializer = GameSerializer(game, context={"request": request})

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


class JoinByCodeView(JoinGameView):
    def get_game(self, request, game_id):
        serializer = JoinByCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return get_object_or_404(Game.objects.select_for_update(), **serializer.validated_data)


class GameDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = GameSerializer
    permission_classes = [IsAuthenticated]

    @phase_transaction
    def destroy(self, request, *args, **kwargs):
        cancel_waiting_game(kwargs["pk"], actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_queryset(self):
        return (
            Game.objects
            .filter(players__user=self.request.user)
            .distinct()
            .prefetch_related("players__user", "players__token_reservation")
        )


class StartGameView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, game_id):
        game = get_object_or_404(
            Game.objects.select_for_update(),
            id=game_id
        )

        if game.creator != request.user:
            return Response(
                {
                    "detail": "Hru může spustit pouze její zakladatel."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if game.status != "waiting":
            return Response(
                {
                    "detail": "Tuto hru už nelze spustit."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        players = list(
            game.players.select_for_update().all()
        )

        if len(players) < 2:
            return Response(
                {
                    "detail": "Pro spuštění hry jsou potřeba alespoň 2 hráči."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(players) > game.max_players:
            return Response({"detail": "Počet hráčů přesahuje kapacitu hry."}, status=status.HTTP_400_BAD_REQUEST)

        available_countries = [
            country[0]
            for country in GamePlayer.COUNTRY_CHOICES
        ]

        assigned_countries = random.sample(
            available_countries,
            len(players)
        )

        for player, country in zip(
            players,
            assigned_countries
        ):
            player.country = country
            player.save(update_fields=["country"])

        game.status = "active"
        game.save(update_fields=["status"])

        create_starting_units(game)

        initialize_supply_centers(game)

        create_phase(
            game=game,
            sequence=1,
            year=1901,
            season="spring",
            phase_type="movement",
        )

        serializer = GameSerializer(game, context={"request": request})

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )
