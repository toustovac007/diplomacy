from django.db import models


class Country(models.Model):
    code = models.CharField(
        max_length=3,
        unique=True,
    )

    name = models.CharField(
        max_length=50,
        unique=True,
    )

    def __str__(self):
        return self.name


class Province(models.Model):
    TYPE_CHOICES = [
        ("inland", "Vnitrozemí"),
        ("coastal", "Pobřeží"),
        ("sea", "Moře"),
    ]

    code = models.CharField(
        max_length=3,
        unique=True,
    )

    name = models.CharField(
        max_length=50,
        unique=True,
    )

    province_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
    )

    is_supply_center = models.BooleanField(
        default=False,
    )

    home_country = models.ForeignKey(
        Country,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="home_provinces",
    )

    def __str__(self):
        return self.name


class Coast(models.Model):
    COAST_CHOICES = [
        ("nc", "Severní pobřeží"),
        ("sc", "Jižní pobřeží"),
        ("ec", "Východní pobřeží"),
    ]

    province = models.ForeignKey(
        Province,
        on_delete=models.CASCADE,
        related_name="coasts",
    )

    code = models.CharField(
        max_length=2,
        choices=COAST_CHOICES,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["province", "code"],
                name="unique_province_coast",
            )
        ]

    def __str__(self):
        return f"{self.province.name} ({self.code.upper()})"


class ProvinceAdjacency(models.Model):
    from_province = models.ForeignKey(
        Province,
        on_delete=models.CASCADE,
        related_name="outgoing_adjacencies",
    )

    to_province = models.ForeignKey(
        Province,
        on_delete=models.CASCADE,
        related_name="incoming_adjacencies",
    )

    army_allowed = models.BooleanField(
        default=False,
    )

    fleet_allowed = models.BooleanField(
        default=False,
    )

    from_coast = models.ForeignKey(
        Coast,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )

    to_coast = models.ForeignKey(
        Coast,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self):
        return (
            f"{self.from_province.code} -> "
            f"{self.to_province.code}"
        )