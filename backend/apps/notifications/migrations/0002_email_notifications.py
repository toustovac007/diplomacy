from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def preserve_deliveries(apps, schema_editor):
    Notification = apps.get_model("notifications", "EmailNotification")
    for row in Notification.objects.using(schema_editor.connection.alias).all().iterator():
        suffix = "started" if row.event_type == "phase_started" else "deadline"
        Notification.objects.using(schema_editor.connection.alias).filter(pk=row.pk).update(
            event_key=f"phase:{row.phase_id}:{suffix}", status="sent", created_at=row.sent_at)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_initial")]
    operations = [
        migrations.RemoveConstraint(model_name="phasenotification", name="unique_phase_notification"),
        migrations.RenameModel(old_name="PhaseNotification", new_name="EmailNotification"),
        migrations.RenameField(model_name="emailnotification", old_name="user", new_name="recipient"),
        migrations.RenameField(model_name="emailnotification", old_name="notification_type", new_name="event_type"),
        migrations.AlterField(model_name="emailnotification", name="recipient", field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE, related_name="email_notifications")),
        migrations.AlterField(model_name="emailnotification", name="phase", field=models.ForeignKey(to="games.gamephase", on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="email_notifications")),
        migrations.AlterField(model_name="emailnotification", name="event_type", field=models.CharField(max_length=30, choices=[(name, name) for name in ("phase_started", "deadline_reminder", "chat_message", "draw_created", "draw_rejected", "draw_cancelled", "game_finished")])),
        migrations.AlterField(model_name="emailnotification", name="sent_at", field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="emailnotification", name="event_key", field=models.CharField(max_length=100, default=""), preserve_default=False),
        migrations.AddField(model_name="emailnotification", name="created_at", field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now), preserve_default=False),
        migrations.AddField(model_name="emailnotification", name="status", field=models.CharField(max_length=10, default="pending", choices=[("pending", "Pending"), ("sending", "Sending"), ("sent", "Sent"), ("failed", "Failed")])),
        migrations.AddField(model_name="emailnotification", name="error", field=models.CharField(max_length=100, blank=True, default="")),
        migrations.RunPython(preserve_deliveries, migrations.RunPython.noop),
        migrations.AddConstraint(model_name="emailnotification", constraint=models.UniqueConstraint(fields=["recipient", "event_type", "event_key"], name="unique_email_event_recipient")),
        migrations.CreateModel(name="NotificationPreference", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("email_phase_started", models.BooleanField(default=True)),
            ("email_deadline_reminder", models.BooleanField(default=True)),
            ("email_chat_message", models.BooleanField(default=True)),
            ("email_draw_events", models.BooleanField(default=True)),
            ("email_game_finished", models.BooleanField(default=True)),
            ("user", models.OneToOneField(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE, related_name="notification_preferences")),
        ]),
    ]
