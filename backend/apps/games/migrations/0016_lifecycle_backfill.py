from django.db import migrations
from django.db.models import Exists, OuterRef


def backfill(apps, schema_editor):
    Phase = apps.get_model("games", "GamePhase")
    Order = apps.get_model("orders", "Order")
    Adjustment = apps.get_model("orders", "AdjustmentOrder")
    # Preserve orders already submitted before deployment; automatic orders do not count.
    submitted = set(Order.objects.filter(phase__status="open", is_default=False).values_list("phase_id", flat=True))
    submitted.update(Adjustment.objects.filter(phase__status="open", is_default=False).values_list("phase_id", flat=True))
    Phase.objects.filter(pk__in=submitted).update(has_submitted_orders=True)

    Game = apps.get_model("games", "Game")
    Stake = apps.get_model("games", "GameStake")
    User = apps.get_model("users", "User")
    Entry = apps.get_model("users", "TokenEntry")
    Center = apps.get_model("games", "SupplyCenterOwnership")
    Unit = apps.get_model("games", "Unit")
    # Return existing eliminated unranked stakes once, retaining their paid-out receipt.
    for game in Game.objects.select_for_update().filter(status="active", scoring="unranked").order_by("pk"):
        stakes = list(Stake.objects.filter(player__game=game, status="locked").annotate(
            centers=Exists(Center.objects.filter(game=game, owner_id=OuterRef("player_id"))),
            units=Exists(Unit.objects.filter(game=game, owner_id=OuterRef("player_id"))),
        ).filter(centers=False, units=False).select_related("player"))
        users = {user.pk: user for user in User.objects.select_for_update().filter(
            pk__in=[stake.player.user_id for stake in stakes]).order_by("pk")}
        for stake in stakes:
            user = users[stake.player.user_id]
            user.tokens_available += stake.amount
            user.save(update_fields=["tokens_available"])
            stake.status, stake.payout = "refunded", stake.amount
            stake.save(update_fields=["status", "payout"])
            Entry.objects.create(user=user, game=game, kind="refund",
                available_delta=stake.amount, frozen_delta=-stake.amount)


class Migration(migrations.Migration):
    dependencies = [
        ("games", "0015_game_inactive_phase_count_game_termination_reason_and_more"),
        ("users", "0006_alter_tokenentry_kind"),
        ("orders", "0006_convoy_orders"),
    ]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
