import uuid

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db import models

from apps.maps.models import Province, Coast


class Game(models.Model):
    STATUS_CHOICES = [
        ("waiting", "Čeká na hráče"),
        ("active", "Probíhá"),
        ("finished", "Dokončena"),
    ]

    name = models.CharField(
        max_length=100,
    )

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_games",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="waiting",
    )

    # Deprecated compatibility field; phase deadlines use the settings below.
    turn_duration_minutes = models.PositiveIntegerField(
        default=1440,
    )

    max_players = models.PositiveIntegerField(
        default=7,
        validators=[MinValueValidator(2), MaxValueValidator(7)],
    )

    is_public = models.BooleanField(default=True)
    invite_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    movement_duration_minutes = models.PositiveIntegerField(default=1440, validators=[MinValueValidator(1), MaxValueValidator(10080)])
    retreat_duration_minutes = models.PositiveIntegerField(default=720, validators=[MinValueValidator(1), MaxValueValidator(10080)])
    adjustment_duration_minutes = models.PositiveIntegerField(default=720, validators=[MinValueValidator(1), MaxValueValidator(10080)])

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    winner = models.ForeignKey(
        "GamePlayer", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="won_games",
    )
    finished_at = models.DateTimeField(null=True, blank=True)
    result_type = models.CharField(max_length=10, choices=[("solo", "Solo victory"), ("draw", "Draw")], null=True, blank=True)
    draw_participants = models.ManyToManyField("GamePlayer", blank=True, related_name="draw_results")

    def clean(self):
        super().clean()
        if self.winner_id and self.winner.game_id != self.pk:
            raise ValidationError({"winner": "Vítěz musí být hráčem této hry."})

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class GamePlayer(models.Model):
    COUNTRY_CHOICES = [
        ("AUS", "Rakousko-Uhersko"),
        ("ENG", "Anglie"),
        ("FRA", "Francie"),
        ("GER", "Německo"),
        ("ITA", "Itálie"),
        ("RUS", "Rusko"),
        ("TUR", "Turecko"),
    ]

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="players",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="game_memberships",
    )

    country = models.CharField(
        max_length=20,
        choices=COUNTRY_CHOICES,
        null=True,
        blank=True,
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["game", "user"],
                name="unique_game_player",
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.game.name}"


class GamePhase(models.Model):
    # None denotes legacy/unavailable history; [] is a complete empty phase.
    resolved_orders_snapshot = models.JSONField(null=True, default=None, blank=True)
    resolved_state_snapshot = models.JSONField(null=True, default=None, blank=True)
    SEASON_CHOICES = [
        ("spring", "Jaro"),
        ("fall", "Podzim"),
        ("winter", "Zima"),
    ]

    PHASE_TYPE_CHOICES = [
        ("movement", "Pohyby"),
        ("retreat", "Ústupy"),
        ("adjustment", "Úpravy jednotek"),
    ]

    STATUS_CHOICES = [
        ("open", "Probíhá"),
        ("resolved", "Vyhodnocena"),
        ("cancelled", "Ukončena dohodou"),
    ]

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="phases",
    )

    sequence = models.PositiveIntegerField()

    year = models.PositiveIntegerField(
        default=1901,
    )

    season = models.CharField(
        max_length=10,
        choices=SEASON_CHOICES,
    )

    phase_type = models.CharField(
        max_length=20,
        choices=PHASE_TYPE_CHOICES,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open",
    )

    deadline = models.DateTimeField()

    started_at = models.DateTimeField(
        auto_now_add=True,
    )

    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["sequence"]

        constraints = [
            models.UniqueConstraint(
                fields=["game", "sequence"],
                name="unique_game_phase_sequence",
            )
        ]

    def __str__(self):
        return (
            f"{self.game.name} - "
            f"{self.get_season_display()} {self.year} "
            f"({self.get_phase_type_display()})"
        )


class DrawProposal(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="draw_proposals")
    proposer = models.ForeignKey(GamePlayer, on_delete=models.PROTECT, related_name="proposed_draws")
    status = models.CharField(max_length=10, default="open", choices=[
        ("open", "Open"), ("accepted", "Accepted"), ("rejected", "Rejected"), ("cancelled", "Cancelled")])
    participants = models.ManyToManyField(GamePlayer, related_name="proposed_draw_results")
    voters = models.ManyToManyField(GamePlayer, through="DrawVote", related_name="draw_proposals_to_vote")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["game"], condition=models.Q(status="open"), name="one_open_draw_per_game")]


class DrawVote(models.Model):
    # A row is an immutable voter snapshot; null vote means pending.
    proposal = models.ForeignKey(DrawProposal, on_delete=models.CASCADE, related_name="votes")
    player = models.ForeignKey(GamePlayer, on_delete=models.PROTECT, related_name="draw_votes")
    vote = models.CharField(max_length=10, choices=[("accept", "Accept"), ("reject", "Reject")], null=True, blank=True)
    voted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["proposal", "player"], name="unique_draw_vote")]


class Unit(models.Model):
    UNIT_TYPE_CHOICES = [
        ("army", "Armáda"),
        ("fleet", "Flotila"),
    ]

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="units",
    )

    owner = models.ForeignKey(
        GamePlayer,
        on_delete=models.CASCADE,
        related_name="units",
    )

    unit_type = models.CharField(
        max_length=10,
        choices=UNIT_TYPE_CHOICES,
    )

    province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        related_name="game_units",
    )

    coast = models.ForeignKey(
        Coast,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="game_units",
    )
    is_dislodged = models.BooleanField(
        default=False,
    )

    dislodged_from = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    dislodged_by_origin = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    def clean(self):
        # ---------------------------------
        # Jedna jednotka na jednu provincii
        # ---------------------------------

        if self.game_id and self.province_id and not self.is_dislodged:
            occupied = Unit.objects.filter(
                game_id=self.game_id,
                province_id=self.province_id,
                is_dislodged=False,
            )

            if self.pk:
                occupied = occupied.exclude(pk=self.pk)

            if occupied.exists():
                raise ValidationError(
                    "V této provincii už je jiná aktivní jednotka."
                )


        # ---------------------------------
        # Vlastník musí být ze stejné hry
        # ---------------------------------

        if (
            self.owner_id
            and self.game_id
            and self.owner.game_id != self.game_id
        ):
            raise ValidationError(
                "Vlastník jednotky nepatří do této hry."
            )

        if not self.province_id:
            return

        # ---------------------------------
        # ARMÁDA
        # ---------------------------------

        if self.unit_type == "army":
            if self.province.province_type == "sea":
                raise ValidationError(
                    "Armáda nemůže být v mořské provincii."
                )

            if self.coast_id is not None:
                raise ValidationError(
                    "Armáda nepoužívá konkrétní pobřeží."
                )

        # ---------------------------------
        # FLOTILA
        # ---------------------------------

        if self.unit_type == "fleet":
            if self.province.province_type == "inland":
                raise ValidationError(
                    "Flotila nemůže být ve vnitrozemské provincii."
                )

            if (
                self.coast_id is not None
                and self.coast.province_id != self.province_id
            ):
                raise ValidationError(
                    "Pobřeží nepatří do provincie jednotky."
                )

            # Spain, Bulgaria a St. Petersburg mají
            # více než jedno pobřeží.
            if (
                self.province.coasts.count() > 1
                and self.coast_id is None
            ):
                raise ValidationError(
                    "Flotila v provincii s více pobřežími "
                    "musí mít určené konkrétní pobřeží."
                )

    def save(self, *args, **kwargs):
        self.full_clean()

        super().save(*args, **kwargs)

    def __str__(self):
        if self.unit_type == "army":
            unit_letter = "A"
        else:
            unit_letter = "F"

        location = self.province.code

        if self.coast:
            location += f"/{self.coast.code}"

        return (
            f"{unit_letter} {location} "
            f"({self.owner.get_country_display()})"
        )


class SupplyCenterOwnership(models.Model):
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="supply_center_ownerships",
    )

    province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        related_name="+",
    )

    owner = models.ForeignKey(
        GamePlayer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_supply_centers",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["game", "province"],
                name="unique_supply_center_per_game",
            )
        ]

    def __str__(self):
        owner = (
            self.owner.country
            if self.owner
            else "neutral"
        )

        return (
            f"{self.game.name}: "
            f"{self.province.code} -> {owner}"
        )


class PhaseReadiness(models.Model):
    phase = models.ForeignKey(GamePhase, on_delete=models.CASCADE, related_name="readiness")
    player = models.ForeignKey(GamePlayer, on_delete=models.CASCADE, related_name="phase_readiness")
    is_ready = models.BooleanField(default=False)
    ready_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["phase", "player"], name="unique_phase_player_readiness")]
