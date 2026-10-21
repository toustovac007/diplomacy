from django.db import transaction
from rest_framework import serializers

from .models import Game, GamePlayer, GamePhase, Unit
from .services.supply_centers import get_supply_center_count

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
    province_type = serializers.CharField(source="province.province_type", read_only=True)
    is_dislodged = serializers.BooleanField(read_only=True)

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
            "is_dislodged",
            "province",
            "province_name",
            "province_code",
            "province_type",
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
    turn_duration_minutes = serializers.IntegerField(min_value=1, max_value=10080, required=False)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request and request.user.is_authenticated and instance.players.filter(user=request.user).exists():
            data["invite_code"] = str(instance.invite_code)
        return data

    winner = GamePlayerSerializer(read_only=True)
    result_type = serializers.CharField(read_only=True, allow_null=True)
    draw_participants = GamePlayerSerializer(many=True, read_only=True)
    finished_at = serializers.DateTimeField(read_only=True)
    winner_supply_center_count = serializers.SerializerMethodField()

    def get_winner_supply_center_count(self, obj):
        return get_supply_center_count(obj.winner) if obj.winner_id else None

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
            "is_public",
            "movement_duration_minutes",
            "retreat_duration_minutes",
            "adjustment_duration_minutes",
            "created_at",
            "players",
            "units",
            "supply_centers",
            "current_phase",
            "winner",
            "winner_supply_center_count",
            "finished_at",
            "result_type",
            "draw_participants",
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
        # Legacy API clients may still submit one duration; deadlines use only
        # the three phase settings after creation.
        legacy_duration = validated_data.get("turn_duration_minutes")
        if legacy_duration is not None:
            for phase_type in ("movement", "retreat", "adjustment"):
                validated_data.setdefault(f"{phase_type}_duration_minutes", legacy_duration)

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


class PublicGameSerializer(serializers.ModelSerializer):
    creator = serializers.CharField(source="creator.username", read_only=True)
    players = GamePlayerSerializer(many=True, read_only=True)

    class Meta:
        model = Game
        fields = ("id", "name", "creator", "status", "players", "max_players", "is_public",
                  "movement_duration_minutes", "retreat_duration_minutes", "adjustment_duration_minutes")


class JoinByCodeSerializer(serializers.Serializer):
    invite_code = serializers.UUIDField()

