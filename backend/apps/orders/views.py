from django.conf import settings
from apps.games.services.phase_lock import lock_game, lock_phase, phase_transaction
from apps.games.services.readiness import ensure_player_orders_editable
from .services.adjustments import get_remaining_adjustments
from django.shortcuts import render
from django.db import transaction
from django.utils import timezone

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
    get_adjustment_delta,
    get_build_count,
    get_disband_count,
    get_buildable_home_centers,
    can_build_unit,
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



class EditableOrdersMixin:
    @phase_transaction
    def create(self, request, *args, **kwargs):
        game = lock_game(kwargs["game_id"])
        phase = lock_phase(self.get_phase())
        player = get_object_or_404(GamePlayer, game=game, user=request.user)
        ensure_player_orders_editable(phase, player)
        return super().create(request, *args, **kwargs)


class PreviousResolvedOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, game_id):
        game = get_object_or_404(Game, pk=game_id, players__user=request.user,
                                 status__in=["active", "finished"])
        phases = game.phases.filter(status="resolved")
        if game.status == "active":
            current = game.phases.filter(status="open").order_by("-sequence").first()
            phases = phases.filter(sequence__lt=current.sequence) if current else phases.none()
        phase = phases.order_by("-sequence").first()
        if phase is None or phase.resolved_orders_snapshot is None:
            return Response({"phase": None, "orders": [], "history_available": False})
        return Response({
            "phase": {
                "id": phase.pk, "sequence": phase.sequence, "year": phase.year,
                "season": phase.season, "season_name": phase.get_season_display(),
                "phase_type": phase.phase_type, "phase_type_name": phase.get_phase_type_display(),
                "resolved_at": phase.resolved_at,
            },
            "orders": phase.resolved_orders_snapshot, "history_available": True,
        })


class OrderListCreateView(EditableOrdersMixin, generics.ListCreateAPIView):
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
        if not settings.ALLOW_MANUAL_PHASE_RESOLVE:
            return Response({"detail": "Ruční vyhodnocení fáze není povoleno."}, status=403)
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

    @phase_transaction
    def create(self, request, *args, **kwargs):
        lock_game(kwargs["game_id"])
        # Serialize submissions with each other and with manual/deadline
        # resolution. Recheck status after acquiring the phase lock.
        phase = get_object_or_404(
            GamePhase.objects.select_for_update(),
            pk=self.get_phase().pk,
            status="open",
        )
        context = self.get_serializer_context()
        context["phase"] = phase
        serializer = self.get_serializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # DISBAND (or a retreat collision) deletes the unit and its orders.
        # Return the saved decision snapshot, not a deleted model instance.
        data = dict(serializer.data)
        dislodged_ids = set(
            phase.game.units.filter(is_dislodged=True).values_list("id", flat=True)
        )
        decided_ids = set(
            Order.objects.filter(
                phase=phase, unit_id__in=dislodged_ids,
                order_type__in=("retreat", "disband"),
            ).values_list("unit_id", flat=True)
        )
        complete = bool(dislodged_ids) and decided_ids == dislodged_ids
        if complete:
            resolve_retreat_phase(phase)
        data["phase_resolved"] = complete
        return Response(data, status=status.HTTP_201_CREATED)

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
        if not settings.ALLOW_MANUAL_PHASE_RESOLVE:
            return Response({"detail": "Ruční vyhodnocení fáze není povoleno."}, status=403)
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
    EditableOrdersMixin, generics.ListCreateAPIView
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

class AdjustmentStatusView(AdjustmentOrderListCreateView):
    http_method_names = ["get", "head", "options"]

    def get(self, request, *args, **kwargs):
        phase = self.get_phase()
        player = self.get_player()
        orders = self.get_queryset()
        build_count = get_build_count(player)
        disband_count = get_disband_count(player)
        unit_count = player.units.filter(is_dislodged=False).count()
        delta = get_adjustment_delta(player)
        centers = []
        reserved = orders.filter(order_type="build").values_list("province_id", flat=True)
        for province in get_buildable_home_centers(player).exclude(id__in=reserved).prefetch_related("coasts"):
            coasts = list(province.coasts.all())
            fleet_coasts = [coast.code for coast in coasts if can_build_unit(player, province, "fleet", coast)]
            centers.append({
                "code": province.code, "name": province.name,
                "province_type": province.province_type,
                "coast_codes": [coast.code for coast in coasts],
                "army_allowed": can_build_unit(player, province, "army"),
                "fleet_allowed": bool(fleet_coasts) or can_build_unit(player, province, "fleet"),
                "fleet_coast_codes": fleet_coasts,
            })
        return Response({
            "phase_id": phase.id, "delta": delta,
            "supply_center_count": unit_count + delta, "unit_count": unit_count,
            "build_count": build_count, "disband_count": disband_count,
            **get_remaining_adjustments(phase, player),
            "buildable_home_centers": centers,
        })


class AdjustmentOrderCancelView(AdjustmentOrderListCreateView):
    http_method_names = ["delete", "options"]

    @phase_transaction
    def delete(self, request, *args, **kwargs):
        lock_game(kwargs["game_id"])
        # Use the same phase lock as resolution, then recheck its status.
        phase = get_object_or_404(
            GamePhase.objects.select_for_update(), pk=self.get_phase().pk,
            status="open", deadline__gt=timezone.now(),
        )
        ensure_player_orders_editable(phase, self.get_player())
        order = get_object_or_404(
            AdjustmentOrder, pk=kwargs["order_id"], phase=phase,
            player=self.get_player(),
        )
        order.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResolveAdjustmentPhaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, game_id):
        if not settings.ALLOW_MANUAL_PHASE_RESOLVE:
            return Response({"detail": "Ruční vyhodnocení fáze není povoleno."}, status=403)
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
