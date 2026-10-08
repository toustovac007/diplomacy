from django.core.management.base import BaseCommand

from apps.games.services.deadlines import (
    process_expired_phases,
)

from apps.notifications.services import (
    process_deadline_reminders,
)


class Command(BaseCommand):
    help = (
        "Zpracuje prošlé herní fáze "
        "a odešle čekající deadline notifikace."
    )

    def handle(self, *args, **options):
        deadline_results = process_expired_phases()

        resolved = sum(
            1
            for result in deadline_results
            if result["status"] == "resolved"
        )

        errors = sum(
            1
            for result in deadline_results
            if result["status"] == "error"
        )

        reminders = process_deadline_reminders()

        self.stdout.write(
            self.style.SUCCESS(
                f"Vyhodnocené fáze: {resolved}"
            )
        )

        self.stdout.write(
            f"Chyby při vyhodnocení: {errors}"
        )

        self.stdout.write(
            f"Odeslané remindery: {reminders}"
        )