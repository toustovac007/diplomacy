from django.shortcuts import render

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.shortcuts import get_object_or_404

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.games.models import Game, GamePhase, GamePlayer

from .models import AdjustmentOrder, Order
from .services.adjudication import (
    AdjudicationError,
    resolve_movement_phase,
)
from .services.adjustments import (
    AdjustmentError,
    resolve_adjustment_phase,
)

from .serializers import (
    OrderSerializer,
    RetreatOrderSerializer,
    AdjustmentOrderSerializer,
)

from .services.retreat import (
    RetreatError,
    resolve_retreat_phase,
)



class OrderListCreateView(generics.ListCreateAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_game(self):
        return get_object_or_404(
            Game,
            id=self.kwargs["game_id"],
            players__user=self.request.user,
            status="active",
        )

    def get_phase(self):
        game = self.get_game()

        return get_object_or_404(
            GamePhase,
            game=game,
            status="open",
        )

    def get_queryset(self):
        phase = self.get_phase()

        return (
            Order.objects
            .filter(
                phase=phase,
                unit__owner__user=self.request.user,
            )
            .select_related(
                "unit",
                "origin_province",
                "origin_coast",
                "target_province",
                "target_coast",
            )
            .order_by("unit_id")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()

        game = self.get_game()
        phase = self.get_phase()

        context["game"] = game
        context["phase"] = phase

        return context

class ResolvePhaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, game_id):
        game = get_object_or_404(
            Game,
            id=game_id,
            players__user=request.user,
            status="active",
        )

        if game.creator_id != request.user.id:
            return Response(
                {
                    "detail":
                        "Fázi může ručně vyhodnotit pouze zakladatel hry."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        phase = get_object_or_404(
            GamePhase,
            game=game,
            status="open",
        )

        try:
            resolve_movement_phase(phase)

        except AdjudicationError as error:
            return Response(
                {
                    "detail": str(error)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        orders = (
            Order.objects
            .filter(phase=phase)
            .select_related(
                "unit",
                "origin_province",
                "origin_coast",
                "target_province",
                "target_coast",
            )
            .order_by("unit_id")
        )

        serializer = OrderSerializer(
            orders,
            many=True,
        )

        return Response(
            {
                "phase_id": phase.id,
                "status": "resolved",
                "orders": serializer.data,
            }
        )

class RetreatOrderListCreateView(generics.ListCreateAPIView):
    serializer_class = RetreatOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_game(self):
        return get_object_or_404(
            Game,
            id=self.kwargs["game_id"],
            players__user=self.request.user,
            status="active",
        )

    def get_phase(self):
        game = self.get_game()

        return get_object_or_404(
            GamePhase,
            game=game,
            status="open",
            phase_type="retreat",
        )

    def get_queryset(self):
        phase = self.get_phase()

        return (
            Order.objects
            .filter(
                phase=phase,
                unit__owner__user=self.request.user,
            )
            .select_related(
                "unit",
                "origin_province",
                "origin_coast",
                "target_province",
                "target_coast",
            )
            .order_by("unit_id")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()

        context["game"] = self.get_game()
        context["phase"] = self.get_phase()

        return context


class ResolveRetreatPhaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, game_id):
        game = get_object_or_404(
            Game,
            id=game_id,
            players__user=request.user,
            status="active",
        )

        if game.creator_id != request.user.id:
            return Response(
                {
                    "detail":
                        "Retreat fázi může ručně vyhodnotit "
                        "pouze zakladatel hry."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        phase = get_object_or_404(
            GamePhase,
            game=game,
            status="open",
            phase_type="retreat",
        )

        try:
            resolve_retreat_phase(phase)

        except RetreatError as error:
            return Response(
                {
                    "detail": str(error)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        orders = (
            Order.objects
            .filter(phase=phase)
            .select_related(
                "unit",
                "origin_province",
                "target_province",
            )
            .order_by("unit_id")
        )

        serializer = RetreatOrderSerializer(
            orders,
            many=True,
        )

        return Response(
            {
                "phase_id": phase.id,
                "status": "resolved",
                "orders": serializer.data,
            }
        )

class AdjustmentOrderListCreateView(
    generics.ListCreateAPIView
):
    serializer_class = AdjustmentOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_game(self):
        return get_object_or_404(
            Game,
            id=self.kwargs["game_id"],
            players__user=self.request.user,
            status="active",
        )

    def get_player(self):
        game = self.get_game()

        return get_object_or_404(
            GamePlayer,
            game=game,
            user=self.request.user,
        )

    def get_phase(self):
        game = self.get_game()

        return get_object_or_404(
            GamePhase,
            game=game,
            status="open",
            phase_type="adjustment",
            season="winter",
        )

    def get_queryset(self):
        return (
            AdjustmentOrder.objects
            .filter(
                phase=self.get_phase(),
                player=self.get_player(),
            )
            .select_related(
                "province",
                "coast",
                "unit",
                "unit__province",
            )
            .order_by("id")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()

        context["game"] = self.get_game()
        context["phase"] = self.get_phase()
        context["player"] = self.get_player()

        return context

class ResolveAdjustmentPhaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, game_id):
        game = get_object_or_404(
            Game,
            id=game_id,
            players__user=request.user,
            status="active",
        )

        if game.creator_id != request.user.id:
            return Response(
                {
                    "detail":
                        "Adjustment fázi může ručně "
                        "vyhodnotit pouze zakladatel hry."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        phase = get_object_or_404(
            GamePhase,
            game=game,
            status="open",
            phase_type="adjustment",
            season="winter",
        )

        try:
            resolve_adjustment_phase(
                phase
            )

        except AdjustmentError as error:
            return Response(
                {
                    "detail": str(error)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "phase_id": phase.id,
                "status": "resolved",
            }
        )