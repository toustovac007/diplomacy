"""One-shot Compose initialization; never reseed an existing map."""
import os

import django
from django.core.management import call_command
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.maps.models import Country, Province, Coast, ProvinceAdjacency  # noqa: E402

call_command("migrate", interactive=False)
with transaction.atomic():
    if not any(model.objects.exists() for model in (Country, Province, Coast, ProvinceAdjacency)):
        call_command("seed_map")
    else:
        print("Existing map data preserved; automatic seeding skipped.")
