from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Game, GamePhase, GamePlayer
from .services.phase_lock import lock_game, phase_transaction
from .services.readiness import readiness_status, set_ready


class PhaseReadinessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, game_id):
        game = get_object_or_404(Game, pk=game_id, players__user=request.user)
        player = get_object_or_404(GamePlayer, game=game, user=request.user)
        phase = game.phases.filter(status="open").first() if game.status == "active" else None
        # Finished games return a terminal status so other tabs can stop polling.
        return Response(readiness_status(game, phase, player))

    @phase_transaction
    def post(self, request, game_id):
        if not isinstance(request.data, dict) or set(request.data) != {"ready"} or type(request.data["ready"]) is not bool:
            raise ValidationError({"detail": "Pošli pouze ready: true nebo false."})
        game = lock_game(game_id)
        player = get_object_or_404(GamePlayer, game=game, user=request.user)
        if game.status != "active":
            raise ValidationError({"detail": "Hra již není aktivní."})
        phase = get_object_or_404(GamePhase.objects.select_for_update(), game=game, status="open")
        phase.game = game
        return Response(set_ready(game, phase, player, request.data["ready"]))
