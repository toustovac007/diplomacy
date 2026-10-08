from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Game, GamePlayer, GamePhase
from .serializer import GameSerializer

import random

from datetime import timedelta
from django.utils import timezone

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
            .order_by("-created_at")
        )


class PublicGameListView(generics.ListAPIView):
    serializer_class = GameSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Game.objects
            .filter(status="waiting")
            .exclude(players__user=self.request.user)
            .distinct()
            .order_by("-created_at")
        )


class JoinGameView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, game_id):
        game = get_object_or_404(
            Game.objects.select_for_update(),
            id=game_id
        )

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

        GamePlayer.objects.create(
            game=game,
            user=request.user
        )

        serializer = GameSerializer(game)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )


class GameDetailView(generics.RetrieveAPIView):
    serializer_class = GameSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Game.objects
            .filter(players__user=self.request.user)
            .distinct()
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

        deadline = (
                timezone.now()
                + timedelta(minutes=game.turn_duration_minutes)
        )

        create_phase(
            game=game,
            sequence=1,
            year=1901,
            season="spring",
            phase_type="movement",
        )

        serializer = GameSerializer(game)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )