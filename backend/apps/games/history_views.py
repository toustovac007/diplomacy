from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Game
from .serializer import GamePhaseSerializer


def history_phase(phase):
    return {
        **GamePhaseSerializer(phase).data,
        "orders_available": phase.resolved_orders_snapshot is not None,
        "state_available": phase.resolved_state_snapshot is not None,
    }


class GameHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, game_id, phase_id=None):
        game = get_object_or_404(
            Game, pk=game_id, players__user=request.user,
            status__in=["active", "finished"],
        )
        phases = game.phases.filter(status="resolved").order_by("sequence")
        if phase_id is None:
            return Response({"phases": [history_phase(phase) for phase in phases]})
        phase = get_object_or_404(phases, pk=phase_id)
        return Response({
            "phase": history_phase(phase),
            "orders": phase.resolved_orders_snapshot,
            "state": phase.resolved_state_snapshot,
            "orders_available": phase.resolved_orders_snapshot is not None,
            "state_available": phase.resolved_state_snapshot is not None,
        })
