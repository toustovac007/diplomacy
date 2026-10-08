from django.db import models
from apps.games.models import (
    GamePhase,
    GamePlayer,
    Unit,
)

from apps.maps.models import (
    Province,
    Coast,
)

class Order(models.Model):
    ORDER_TYPE_CHOICES = [
        ("hold", "Držet pozici"),
        ("move", "Pohyb"),
        ("support", "Podpora"),
        ("retreat", "Ústup"),
        ("disband", "Rozpuštění"),
    ]
    RESULT_CHOICES = [
        ("pending", "Čeká na vyhodnocení"),
        ("success", "Úspěch"),
        ("failed", "Neúspěch"),
    ]

    phase = models.ForeignKey(
        GamePhase,
        on_delete=models.CASCADE,
        related_name="orders",
    )

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="orders",
    )

    order_type = models.CharField(
        max_length=20,
        choices=ORDER_TYPE_CHOICES,
    )

    # Pozice jednotky, která rozkaz vydala.
    origin_province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        related_name="+",
    )

    origin_coast = models.ForeignKey(
        Coast,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    # MOVE
    target_province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    target_coast = models.ForeignKey(
        Coast,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    # SUPPORT
    supported_unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="received_support_orders",
    )

    # Pozice podporované jednotky v době zadání rozkazu.
    supported_origin_province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    supported_origin_coast = models.ForeignKey(
        Coast,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    # Provincie, do které podpora směřuje.
    #
    # SUPPORT HOLD:
    # support_target_province == supported_origin_province
    #
    # SUPPORT MOVE:
    # support_target_province == cíl podporovaného pohybu
    support_target_province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    support_target_coast = models.ForeignKey(
        Coast,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    result = models.CharField(
        max_length=10,
        choices=RESULT_CHOICES,
        default="pending",
    )

    result_reason = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    is_default = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["phase", "unit"],
                name="unique_order_per_unit_phase",
            )
        ]

    def __str__(self):
        unit_letter = (
            "A"
            if self.unit.unit_type == "army"
            else "F"
        )

        origin = self.origin_province.code

        if self.origin_coast:
            origin += f"/{self.origin_coast.code}"

        if self.order_type == "hold":
            return f"{unit_letter} {origin} HOLD"

        if self.order_type == "move":
            target = (
                self.target_province.code
                if self.target_province
                else "?"
            )

            if self.target_coast:
                target += f"/{self.target_coast.code}"

            return f"{unit_letter} {origin} -> {target}"

        if self.order_type == "support":
            if not self.supported_unit:
                return f"{unit_letter} {origin} SUPPORT ?"

            supported_letter = (
                "A"
                if self.supported_unit.unit_type == "army"
                else "F"
            )

            supported_origin = (
                self.supported_origin_province.code
                if self.supported_origin_province
                else "?"
            )

            support_target = (
                self.support_target_province.code
                if self.support_target_province
                else "?"
            )

            if self.support_target_coast:
                support_target += (
                    f"/{self.support_target_coast.code}"
                )

            if (
                self.supported_origin_province_id
                == self.support_target_province_id
            ):
                return (
                    f"{unit_letter} {origin} S "
                    f"{supported_letter} "
                    f"{supported_origin} HOLD"
                )

            return (
                f"{unit_letter} {origin} S "
                f"{supported_letter} "
                f"{supported_origin} -> "
                f"{support_target}"
            )

        return f"{unit_letter} {origin} {self.order_type}"


class AdjustmentOrder(models.Model):
    ORDER_TYPE_CHOICES = [
        ("build", "Postavit"),
        ("disband", "Rozpustit"),
    ]

    UNIT_TYPE_CHOICES = [
        ("army", "Armáda"),
        ("fleet", "Flotila"),
    ]

    RESULT_CHOICES = [
        ("pending", "Čeká na vyhodnocení"),
        ("success", "Úspěch"),
        ("failed", "Neúspěch"),
    ]

    phase = models.ForeignKey(
        GamePhase,
        on_delete=models.CASCADE,
        related_name="adjustment_orders",
    )

    player = models.ForeignKey(
        GamePlayer,
        on_delete=models.CASCADE,
        related_name="adjustment_orders",
    )

    order_type = models.CharField(
        max_length=10,
        choices=ORDER_TYPE_CHOICES,
    )

    # Používá BUILD
    unit_type = models.CharField(
        max_length=10,
        choices=UNIT_TYPE_CHOICES,
        null=True,
        blank=True,
    )

    # Používá BUILD
    province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    # Např. STP/nc nebo STP/sc
    coast = models.ForeignKey(
        Coast,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    # Používá DISBAND
    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="adjustment_orders",
    )

    result = models.CharField(
        max_length=10,
        choices=RESULT_CHOICES,
        default="pending",
    )

    result_reason = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    is_default = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["phase", "unit"],
                name="unique_adjustment_unit_per_phase",
            ),
            models.UniqueConstraint(
                fields=["phase", "province"],
                name="unique_adjustment_province_per_phase",
            ),
        ]

    def __str__(self):
        if self.order_type == "build":
            return (
                f"BUILD {self.unit_type} "
                f"{self.province}"
            )

        return f"DISBAND {self.unit}"