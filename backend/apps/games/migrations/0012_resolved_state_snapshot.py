from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("games", "0011_draw_voting")]

    operations = [
        migrations.AddField(
            model_name="gamephase",
            name="resolved_state_snapshot",
            field=models.JSONField(null=True, default=None, blank=True),
        ),
    ]
