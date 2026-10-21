from django.core.management.base import BaseCommand
from apps.notifications.services import process_deadline_reminders

from apps.games.services.deadlines import (
    process_expired_phases,
)


class Command(BaseCommand):
    help = (
        "Vyhodnotí všechny otevřené herní fáze, "
        "kterým vypršel deadline."
    )

    def handle(self, *args, **options):
        results = process_expired_phases()
        reminders = process_deadline_reminders()
        self.stdout.write(f"Odeslané deadline připomínky: {reminders}")

        if not results:
            self.stdout.write(
                self.style.SUCCESS(
                    "Žádné prošlé fáze."
                )
            )

            return

        resolved_count = 0
        error_count = 0

        for result in results:
            if result["status"] == "resolved":
                resolved_count += 1

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Phase {result['phase_id']} "
                        f"({result['phase_type']}) "
                        f"vyhodnocena."
                    )
                )

            else:
                error_count += 1

                self.stdout.write(
                    self.style.ERROR(
                        f"Phase {result['phase_id']}: "
                        f"{result.get('detail')}"
                    )
                )

        self.stdout.write(
            ""
        )

        self.stdout.write(
            f"Vyhodnoceno: {resolved_count}"
        )

        self.stdout.write(
            f"Chyby: {error_count}"
        )
