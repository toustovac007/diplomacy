from rest_framework import serializers

from apps.games.models import Unit
from apps.maps.models import Province, Coast
from apps.maps.rules import (
    can_unit_move,
    can_unit_support_to,
)

from .models import Order

from .services.retreat import (
    can_unit_retreat,
)

from apps.games.models import Unit
from apps.maps.models import Province, Coast

from apps.orders.models import (
    Order,
    AdjustmentOrder,
)

from apps.orders.services.adjustments import (
    can_build_unit,
    get_adjustment_delta,
)

class OrderSerializer(serializers.ModelSerializer):
    unit_id = serializers.IntegerField(
        write_only=True
    )

    saved_unit_id = serializers.IntegerField(
        source="unit.id",
        read_only=True,
    )



    # MOVE
    target = serializers.CharField(
        write_only=True,
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    target_coast_code = serializers.CharField(
        write_only=True,
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    # SUPPORT
    supported_unit_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )

    support_target = serializers.CharField(
        write_only=True,
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    support_target_coast_code = serializers.CharField(
        write_only=True,
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    # -------------------------
    # Read-only informace
    # -------------------------

    unit_type = serializers.CharField(
        source="unit.unit_type",
        read_only=True,
    )

    origin = serializers.CharField(
        source="origin_province.code",
        read_only=True,
    )

    origin_coast_code = serializers.CharField(
        source="origin_coast.code",
        read_only=True,
        allow_null=True,
    )

    target_code = serializers.CharField(
        source="target_province.code",
        read_only=True,
        allow_null=True,
    )

    saved_target_coast = serializers.CharField(
        source="target_coast.code",
        read_only=True,
        allow_null=True,
    )

    supported_origin = serializers.CharField(
        source="supported_origin_province.code",
        read_only=True,
        allow_null=True,
    )

    supported_origin_coast_code = serializers.CharField(
        source="supported_origin_coast.code",
        read_only=True,
        allow_null=True,
    )

    support_target_code = serializers.CharField(
        source="support_target_province.code",
        read_only=True,
        allow_null=True,
    )

    saved_support_target_coast = serializers.CharField(
        source="support_target_coast.code",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Order

        fields = (
            "id",
            "unit_id",
            "saved_unit_id",
            "unit_type",
            "order_type",

            "origin",
            "origin_coast_code",

            "target",
            "target_code",
            "target_coast_code",
            "saved_target_coast",

            "supported_unit_id",
            "supported_origin",
            "supported_origin_coast_code",

            "support_target",
            "support_target_code",
            "support_target_coast_code",
            "saved_support_target_coast",

            "result",
            "result_reason",
            "is_default",

            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "result",
            "result_reason",
            "is_default",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        request = self.context["request"]
        game = self.context["game"]
        phase = self.context["phase"]

        unit_id = attrs["unit_id"]
        order_type = attrs["order_type"]

        try:
            unit = (
                Unit.objects
                .select_related(
                    "owner__user",
                    "province",
                    "coast",
                )
                .get(
                    id=unit_id,
                    game=game,
                )
            )

        except Unit.DoesNotExist:
            raise serializers.ValidationError(
                {
                    "unit_id":
                        "Tato jednotka v této hře neexistuje."
                }
            )

        if unit.owner.user_id != request.user.id:
            raise serializers.ValidationError(
                {
                    "unit_id":
                        "Tato jednotka ti nepatří."
                }
            )

        if phase.phase_type != "movement":
            raise serializers.ValidationError(
                "V této fázi nelze zadávat "
                "pohybové rozkazy."
            )

        if phase.status != "open":
            raise serializers.ValidationError(
                "Tato fáze už není otevřená."
            )

        # Výchozí hodnoty pro create()
        attrs["_unit"] = unit

        attrs["_target_province"] = None
        attrs["_target_coast"] = None

        attrs["_supported_unit"] = None
        attrs["_supported_origin_province"] = None
        attrs["_supported_origin_coast"] = None
        attrs["_support_target_province"] = None
        attrs["_support_target_coast"] = None

        target_code = attrs.get("target")
        target_coast_code = attrs.get(
            "target_coast_code"
        )

        supported_unit_id = attrs.get(
            "supported_unit_id"
        )

        support_target_code = attrs.get(
            "support_target"
        )

        support_target_coast_code = attrs.get(
            "support_target_coast_code"
        )

        # =========================
        # HOLD
        # =========================

        if order_type == "hold":
            if target_code:
                raise serializers.ValidationError(
                    {
                        "target":
                            "Rozkaz HOLD nemá cílovou provincii."
                    }
                )

            if supported_unit_id:
                raise serializers.ValidationError(
                    {
                        "supported_unit_id":
                            "Rozkaz HOLD nikoho nepodporuje."
                    }
                )

            return attrs

        # =========================
        # MOVE
        # =========================

        if order_type == "move":
            if not target_code:
                raise serializers.ValidationError(
                    {
                        "target":
                            "Rozkaz MOVE potřebuje "
                            "cílovou provincii."
                    }
                )

            if supported_unit_id:
                raise serializers.ValidationError(
                    {
                        "supported_unit_id":
                            "Rozkaz MOVE nemůže obsahovat "
                            "podporovanou jednotku."
                    }
                )

            try:
                target_province = Province.objects.get(
                    code=target_code.upper()
                )

            except Province.DoesNotExist:
                raise serializers.ValidationError(
                    {
                        "target":
                            "Cílová provincie neexistuje."
                    }
                )

            target_coast = None

            if target_coast_code:
                try:
                    target_coast = Coast.objects.get(
                        province=target_province,
                        code=target_coast_code.lower(),
                    )

                except Coast.DoesNotExist:
                    raise serializers.ValidationError(
                        {
                            "target_coast_code":
                                "Toto pobřeží neexistuje."
                        }
                    )

            if not can_unit_move(
                unit,
                target_province,
                target_coast,
            ):
                raise serializers.ValidationError(
                    {
                        "target":
                            "Tato jednotka se do cílové "
                            "provincie nemůže přesunout."
                    }
                )

            attrs["_target_province"] = (
                target_province
            )

            attrs["_target_coast"] = (
                target_coast
            )

            return attrs

        # =========================
        # SUPPORT
        # =========================

        if order_type == "support":
            if target_code:
                raise serializers.ValidationError(
                    {
                        "target":
                            "Pro SUPPORT použij "
                            "support_target."
                    }
                )

            if not supported_unit_id:
                raise serializers.ValidationError(
                    {
                        "supported_unit_id":
                            "Rozkaz SUPPORT musí určit "
                            "podporovanou jednotku."
                    }
                )

            try:
                supported_unit = (
                    Unit.objects
                    .select_related(
                        "owner",
                        "province",
                        "coast",
                    )
                    .get(
                        id=supported_unit_id,
                        game=game,
                    )
                )

            except Unit.DoesNotExist:
                raise serializers.ValidationError(
                    {
                        "supported_unit_id":
                            "Podporovaná jednotka "
                            "v této hře neexistuje."
                    }
                )

            if supported_unit.id == unit.id:
                raise serializers.ValidationError(
                    {
                        "supported_unit_id":
                            "Jednotka nemůže podporovat "
                            "sama sebe."
                    }
                )

            # -------------------------
            # SUPPORT HOLD
            # -------------------------

            if not support_target_code:
                support_target_province = (
                    supported_unit.province
                )

                support_target_coast = (
                    supported_unit.coast
                )

            # -------------------------
            # SUPPORT MOVE
            # -------------------------

            else:
                try:
                    support_target_province = (
                        Province.objects.get(
                            code=
                            support_target_code.upper()
                        )
                    )

                except Province.DoesNotExist:
                    raise serializers.ValidationError(
                        {
                            "support_target":
                                "Cílová provincie podpory "
                                "neexistuje."
                        }
                    )

                support_target_coast = None

                if support_target_coast_code:
                    try:
                        support_target_coast = (
                            Coast.objects.get(
                                province=
                                support_target_province,
                                code=
                                support_target_coast_code.lower(),
                            )
                        )

                    except Coast.DoesNotExist:
                        raise serializers.ValidationError(
                            {
                                "support_target_coast_code":
                                    "Toto pobřeží "
                                    "neexistuje."
                            }
                        )

                # Podporovaný pohyb musí být
                # sám o sobě legální.
                if not can_unit_move(
                    supported_unit,
                    support_target_province,
                    support_target_coast,
                ):
                    raise serializers.ValidationError(
                        {
                            "support_target":
                                "Podporovaná jednotka "
                                "se do této provincie "
                                "nemůže přesunout."
                        }
                    )

            # Supporting unit musí být schopna
            # do podporované provincie dosáhnout.

            if not can_unit_support_to(
                unit,
                support_target_province,
                support_target_coast,
            ):
                raise serializers.ValidationError(
                    {
                        "support_target":
                            "Tato jednotka nemůže "
                            "podporovat akci v této "
                            "provincii."
                    }
                )

            attrs["_supported_unit"] = (
                supported_unit
            )

            attrs["_supported_origin_province"] = (
                supported_unit.province
            )

            attrs["_supported_origin_coast"] = (
                supported_unit.coast
            )

            attrs["_support_target_province"] = (
                support_target_province
            )

            attrs["_support_target_coast"] = (
                support_target_coast
            )

            return attrs

        raise serializers.ValidationError(
            {
                "order_type":
                    "Neznámý typ rozkazu."
            }
        )

    def create(self, validated_data):
        unit = validated_data.pop(
            "_unit"
        )

        target_province = validated_data.pop(
            "_target_province"
        )

        target_coast = validated_data.pop(
            "_target_coast"
        )

        supported_unit = validated_data.pop(
            "_supported_unit"
        )

        supported_origin_province = (
            validated_data.pop(
                "_supported_origin_province"
            )
        )

        supported_origin_coast = (
            validated_data.pop(
                "_supported_origin_coast"
            )
        )

        support_target_province = (
            validated_data.pop(
                "_support_target_province"
            )
        )

        support_target_coast = (
            validated_data.pop(
                "_support_target_coast"
            )
        )

        validated_data.pop(
            "unit_id",
            None,
        )

        validated_data.pop(
            "target",
            None,
        )

        validated_data.pop(
            "target_coast_code",
            None,
        )

        validated_data.pop(
            "supported_unit_id",
            None,
        )

        validated_data.pop(
            "support_target",
            None,
        )

        validated_data.pop(
            "support_target_coast_code",
            None,
        )

        phase = self.context["phase"]

        order, created = (
            Order.objects.update_or_create(
                phase=phase,
                unit=unit,
                defaults={
                    "order_type":
                        validated_data["order_type"],

                    "origin_province":
                        unit.province,

                    "origin_coast":
                        unit.coast,

                    "target_province":
                        target_province,

                    "target_coast":
                        target_coast,

                    "supported_unit":
                        supported_unit,

                    "supported_origin_province":
                        supported_origin_province,

                    "supported_origin_coast":
                        supported_origin_coast,

                    "support_target_province":
                        support_target_province,

                    "support_target_coast":
                        support_target_coast,

                    "result":
                        "pending",

                    "result_reason":
                        "",

                    "is_default":
                        False,
                }
            )
        )

        return order


class RetreatOrderSerializer(serializers.ModelSerializer):
    unit_id = serializers.IntegerField(
        write_only=True
    )

    target = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    target_coast_code = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    origin = serializers.CharField(
        source="origin_province.code",
        read_only=True,
    )

    target_code = serializers.CharField(
        source="target_province.code",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Order

        fields = (
            "id",
            "unit_id",
            "order_type",
            "origin",
            "target",
            "target_code",
            "target_coast_code",
            "result",
            "result_reason",
            "is_default",
        )

        read_only_fields = (
            "id",
            "result",
            "result_reason",
            "is_default",
        )

    def validate(self, attrs):
        request = self.context["request"]
        game = self.context["game"]
        phase = self.context["phase"]

        if phase.phase_type != "retreat":
            raise serializers.ValidationError(
                "Aktuální fáze není Retreat."
            )

        try:
            unit = Unit.objects.get(
                id=attrs["unit_id"],
                game=game,
                owner__user=request.user,
                is_dislodged=True,
            )

        except Unit.DoesNotExist:
            raise serializers.ValidationError(
                {
                    "unit_id":
                        "Tato vytlačená jednotka "
                        "neexistuje nebo ti nepatří."
                }
            )

        order_type = attrs["order_type"]

        if order_type not in (
            "retreat",
            "disband",
        ):
            raise serializers.ValidationError(
                {
                    "order_type":
                        "V Retreat fázi lze použít "
                        "jen RETREAT nebo DISBAND."
                }
            )

        attrs["_unit"] = unit
        attrs["_target_province"] = None
        attrs["_target_coast"] = None

        if order_type == "disband":
            if attrs.get("target"):
                raise serializers.ValidationError(
                    {
                        "target":
                            "DISBAND nemá cílovou provincii."
                    }
                )

            return attrs

        target_code = attrs.get("target")

        if not target_code:
            raise serializers.ValidationError(
                {
                    "target":
                        "RETREAT potřebuje cílovou provincii."
                }
            )

        try:
            target_province = Province.objects.get(
                code=target_code.upper()
            )

        except Province.DoesNotExist:
            raise serializers.ValidationError(
                {
                    "target":
                        "Cílová provincie neexistuje."
                }
            )

        target_coast = None

        coast_code = attrs.get(
            "target_coast_code"
        )

        if coast_code:
            try:
                target_coast = Coast.objects.get(
                    province=target_province,
                    code=coast_code.lower(),
                )

            except Coast.DoesNotExist:
                raise serializers.ValidationError(
                    {
                        "target_coast_code":
                            "Toto pobřeží neexistuje."
                    }
                )


        if not can_unit_retreat(
            unit,
            phase,
            target_province,
            target_coast,
        ):
            raise serializers.ValidationError(
                {
                    "target":
                        "Do této provincie jednotka "
                        "nemůže ustoupit."
                }
            )

        attrs["_target_province"] = (
            target_province
        )

        attrs["_target_coast"] = (
            target_coast
        )

        return attrs

    def create(self, validated_data):
        unit = validated_data.pop("_unit")

        target_province = validated_data.pop(
            "_target_province"
        )

        target_coast = validated_data.pop(
            "_target_coast"
        )

        validated_data.pop(
            "unit_id",
            None,
        )

        validated_data.pop(
            "target",
            None,
        )

        validated_data.pop(
            "target_coast_code",
            None,
        )

        phase = self.context["phase"]

        order, created = Order.objects.update_or_create(
            phase=phase,
            unit=unit,
            defaults={
                "order_type":
                    validated_data["order_type"],

                "origin_province":
                    unit.dislodged_from
                    or unit.province,

                "origin_coast":
                    unit.coast,

                "target_province":
                    target_province,

                "target_coast":
                    target_coast,

                "supported_unit":
                    None,

                "supported_origin_province":
                    None,

                "supported_origin_coast":
                    None,

                "support_target_province":
                    None,

                "support_target_coast":
                    None,

                "result":
                    "pending",

                "result_reason":
                    "",

                "is_default":
                    False,
            },
        )

        return order

class AdjustmentOrderSerializer(serializers.ModelSerializer):
    province = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    province_code = serializers.CharField(
        source="province.code",
        read_only=True,
        allow_null=True,
    )

    coast_code = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    saved_coast_code = serializers.CharField(
        source="coast.code",
        read_only=True,
        allow_null=True,
    )

    unit_id = serializers.IntegerField(
        write_only=True,
        required=False,
        allow_null=True,
    )

    saved_unit_id = serializers.IntegerField(
        source="unit.id",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = AdjustmentOrder

        fields = (
            "id",
            "order_type",
            "unit_type",
            "province",
            "province_code",
            "coast_code",
            "saved_coast_code",
            "unit_id",
            "saved_unit_id",
            "result",
            "result_reason",
            "is_default",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "result",
            "result_reason",
            "is_default",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        game = self.context["game"]
        phase = self.context["phase"]
        player = self.context["player"]

        if phase.phase_type != "adjustment":
            raise serializers.ValidationError(
                "Aktuální fáze není Adjustment."
            )

        if phase.season != "winter":
            raise serializers.ValidationError(
                "Adjustment lze zadávat pouze ve Winter fázi."
            )

        if phase.status != "open":
            raise serializers.ValidationError(
                "Tato fáze už není otevřená."
            )

        order_type = attrs.get("order_type")
        delta = get_adjustment_delta(player)

        attrs["_province"] = None
        attrs["_coast"] = None
        attrs["_unit"] = None

        # ==================================
        # BUILD
        # ==================================

        if order_type == "build":
            if delta <= 0:
                raise serializers.ValidationError(
                    {
                        "order_type":
                            "Tento hráč nemá právo stavět jednotku."
                    }
                )

            unit_type = attrs.get("unit_type")

            if unit_type not in (
                "army",
                "fleet",
            ):
                raise serializers.ValidationError(
                    {
                        "unit_type":
                            "BUILD vyžaduje army nebo fleet."
                    }
                )

            province_code = attrs.get(
                "province"
            )

            if not province_code:
                raise serializers.ValidationError(
                    {
                        "province":
                            "BUILD vyžaduje provincii."
                    }
                )

            try:
                province = Province.objects.get(
                    code=province_code.upper()
                )

            except Province.DoesNotExist:
                raise serializers.ValidationError(
                    {
                        "province":
                            "Tato provincie neexistuje."
                    }
                )

            coast = None

            coast_code = attrs.get(
                "coast_code"
            )

            if coast_code:
                try:
                    coast = Coast.objects.get(
                        province=province,
                        code=coast_code.lower(),
                    )

                except Coast.DoesNotExist:
                    raise serializers.ValidationError(
                        {
                            "coast_code":
                                "Toto pobřeží v dané provincii "
                                "neexistuje."
                        }
                    )

            if not can_build_unit(
                player=player,
                province=province,
                unit_type=unit_type,
                coast=coast,
            ):
                raise serializers.ValidationError(
                    "Tento BUILD není povolen."
                )

            existing_builds = (
                AdjustmentOrder.objects
                .filter(
                    phase=phase,
                    player=player,
                    order_type="build",
                )
                .count()
            )

            if existing_builds >= delta:
                raise serializers.ValidationError(
                    {
                        "order_type":
                            f"Můžeš zadat maximálně "
                            f"{delta} BUILD rozkazů."
                    }
                )

            if AdjustmentOrder.objects.filter(
                phase=phase,
                province=province,
            ).exists():
                raise serializers.ValidationError(
                    {
                        "province":
                            "V této provincii už BUILD rozkaz existuje."
                    }
                )

            attrs["_province"] = province
            attrs["_coast"] = coast

            return attrs

        # ==================================
        # DISBAND
        # ==================================

        if order_type == "disband":
            if delta >= 0:
                raise serializers.ValidationError(
                    {
                        "order_type":
                            "Tento hráč nemusí rozpouštět jednotky."
                    }
                )

            unit_id = attrs.get(
                "unit_id"
            )

            if not unit_id:
                raise serializers.ValidationError(
                    {
                        "unit_id":
                            "DISBAND vyžaduje jednotku."
                    }
                )

            try:
                unit = Unit.objects.get(
                    id=unit_id,
                    game=game,
                    owner=player,
                    is_dislodged=False,
                )

            except Unit.DoesNotExist:
                raise serializers.ValidationError(
                    {
                        "unit_id":
                            "Tato jednotka neexistuje "
                            "nebo ti nepatří."
                    }
                )

            required = abs(delta)

            existing_disbands = (
                AdjustmentOrder.objects
                .filter(
                    phase=phase,
                    player=player,
                    order_type="disband",
                )
                .count()
            )

            if existing_disbands >= required:
                raise serializers.ValidationError(
                    {
                        "order_type":
                            f"Musíš rozpustit přesně "
                            f"{required} jednotek."
                    }
                )

            if AdjustmentOrder.objects.filter(
                phase=phase,
                unit=unit,
            ).exists():
                raise serializers.ValidationError(
                    {
                        "unit_id":
                            "Pro tuto jednotku už DISBAND existuje."
                    }
                )

            attrs["_unit"] = unit

            return attrs

        raise serializers.ValidationError(
            {
                "order_type":
                    "Povolené jsou pouze BUILD a DISBAND."
            }
        )

    def create(self, validated_data):
        player = self.context["player"]
        phase = self.context["phase"]

        province = validated_data.pop(
            "_province",
            None,
        )

        coast = validated_data.pop(
            "_coast",
            None,
        )

        unit = validated_data.pop(
            "_unit",
            None,
        )

        validated_data.pop(
            "province",
            None,
        )

        validated_data.pop(
            "coast_code",
            None,
        )

        validated_data.pop(
            "unit_id",
            None,
        )

        order_type = validated_data[
            "order_type"
        ]

        if order_type == "build":
            return AdjustmentOrder.objects.create(
                phase=phase,
                player=player,
                order_type="build",
                unit_type=validated_data["unit_type"],
                province=province,
                coast=coast,
                unit=None,
            )

        return AdjustmentOrder.objects.create(
            phase=phase,
            player=player,
            order_type="disband",
            unit=unit,
            unit_type=None,
            province=None,
            coast=None,
        )