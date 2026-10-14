from django.db import transaction
from rest_framework import serializers

from .models import Game, GamePlayer, GamePhase, Unit

from apps.games.models import (
    Game,
    GamePlayer,
    GamePhase,
    Unit,
    SupplyCenterOwnership,
)


class GamePlayerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        source="user.username",
        read_only=True
    )

    country_name = serializers.CharField(
        source="get_country_display",
        read_only=True
    )

    class Meta:
        model = GamePlayer
        fields = (
            "id",
            "username",
            "country",
            "country_name",
            "joined_at",
        )




class GamePhaseSerializer(serializers.ModelSerializer):
    season_name = serializers.CharField(
        source="get_season_display",
        read_only=True
    )

    phase_type_name = serializers.CharField(
        source="get_phase_type_display",
        read_only=True
    )

    class Meta:
        model = GamePhase
        fields = (
            "id",
            "sequence",
            "year",
            "season",
            "season_name",
            "phase_type",
            "phase_type_name",
            "status",
            "deadline",
            "started_at",
            "resolved_at",
        )


class UnitSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(
        source="owner.user.username",
        read_only=True,
    )

    country = serializers.CharField(
        source="owner.country",
        read_only=True,
    )

    country_name = serializers.CharField(
        source="owner.get_country_display",
        read_only=True,
    )

    province = serializers.CharField(
        source="province.code",
        read_only=True,
    )

    province_name = serializers.CharField(
        source="province.name",
        read_only=True,
    )

    province_code = serializers.CharField(
        source="province.code",
        read_only=True,
    )

    coast = serializers.CharField(
        source="coast.code",
        read_only=True,
        allow_null=True,
    )

    unit_type_name = serializers.CharField(
        source="get_unit_type_display",
        read_only=True,
    )

    class Meta:
        model = Unit
        fields = (
            "id",
            "owner_username",
            "country",
            "country_name",
            "unit_type",
            "unit_type_name",
            "province",
            "province_name",
            "province_code",
            "coast",
        )


class SupplyCenterOwnershipSerializer(serializers.ModelSerializer):
    province_code = serializers.CharField(
        source="province.code",
        read_only=True,
    )

    province_name = serializers.CharField(
        source="province.name",
        read_only=True,
    )

    owner_country = serializers.SerializerMethodField()

    def get_owner_country(self, obj):
        if obj.owner_id is None:
            return None

        return obj.owner.country

    class Meta:
        model = SupplyCenterOwnership

        fields = (
            "province_code",
            "province_name",
            "owner_country",
        )


class GameSerializer(serializers.ModelSerializer):
    creator = serializers.CharField(
        source="creator.username",
        read_only=True
    )

    players = GamePlayerSerializer(
        many=True,
        read_only=True
    )

    units = UnitSerializer(
        many=True,
        read_only=True,
    )

    supply_centers = SupplyCenterOwnershipSerializer(
        source="supply_center_ownerships",
        many=True,
        read_only=True,
    )

    current_phase = serializers.SerializerMethodField()

    class Meta:
        model = Game
        fields = (
            "id",
            "name",
            "creator",
            "status",
            "turn_duration_minutes",
            "max_players",
            "created_at",
            "players",
            "units",
            "supply_centers",
            "current_phase",
        )

        read_only_fields = (
            "id",
            "creator",
            "status",
            "created_at",
            "players",
        )

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user

        game = Game.objects.create(
            creator=user,
            **validated_data
        )

        GamePlayer.objects.create(
            game=game,
            user=user
        )

        return game

    def get_current_phase(self, obj):
        phase = (
            obj.phases
            .filter(status="open")
            .order_by("-sequence")
            .first()
        )

        if phase is None:
            return None

        return GamePhaseSerializer(phase).data

