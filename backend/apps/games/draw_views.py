from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Game, DrawProposal, DrawVote
from .serializer import GamePlayerSerializer
from .services import draws


class DrawVoteSerializer(serializers.ModelSerializer):
    player = GamePlayerSerializer(read_only=True)

    class Meta:
        model = DrawVote
        fields = ("player", "vote", "voted_at")


class DrawProposalSerializer(serializers.ModelSerializer):
    proposer = GamePlayerSerializer(read_only=True)
    participants = GamePlayerSerializer(many=True, read_only=True)
    voters = DrawVoteSerializer(source="votes", many=True, read_only=True)

    class Meta:
        model = DrawProposal
        fields = ("id", "status", "proposer", "participants", "voters", "created_at", "resolved_at")


class ProposalInput(serializers.Serializer):
    participant_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=2, max_length=7)


class VoteInput(serializers.Serializer):
    vote = serializers.ChoiceField(choices=["accept", "reject"])

    def validate(self, data):
        if set(self.initial_data) - {"vote"}:
            raise serializers.ValidationError("Hlasováním nelze měnit účastníky ani hlasující návrhu.")
        return data


def result(proposal, game):
    return {"proposal": DrawProposalSerializer(proposal).data, "game_status": game.status}


class CurrentDrawView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, game_id):
        game = get_object_or_404(Game, pk=game_id, players__user=request.user)
        proposal = game.draw_proposals.filter(status="open").first()
        return Response({
            "proposal": DrawProposalSerializer(proposal).data if proposal else None,
            "game_status": game.status,
            "surviving_players": GamePlayerSerializer(draws.surviving_players(game), many=True).data,
        })


class CreateDrawView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, game_id):
        data = ProposalInput(data=request.data)
        data.is_valid(raise_exception=True)
        proposal, game = draws.propose(game_id, request.user, **data.validated_data)
        return Response(result(proposal, game), status=201)


class VoteDrawView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, game_id, proposal_id):
        data = VoteInput(data=request.data)
        data.is_valid(raise_exception=True)
        proposal, game = draws.vote(game_id, proposal_id, request.user, data.validated_data["vote"])
        return Response(result(proposal, game))


class CancelDrawView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, game_id, proposal_id):
        proposal, game = draws.cancel(game_id, proposal_id, request.user)
        return Response(result(proposal, game))
