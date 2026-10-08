from django.core.management.base import BaseCommand

from apps.notifications.services import (
    process_deadline_reminders,
)


class Command(BaseCommand):
    help = (
        "Odešle čekající e-mailové "
        "notifikace hráčům."
    )

    def handle(self, *args, **options):
        sent = process_deadline_reminders()

        self.stdout.write(
            self.style.SUCCESS(
                f"Odesláno notifikací: {sent}"
            )
        )