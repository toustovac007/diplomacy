from django.core.management.base import BaseCommand
from apps.users.tokens import process_token_refills


class Command(BaseCommand):
    help = "Apply due token minimum refills, respecting each account's 48-hour cooldown."

    def handle(self, *args, **options):
        count = process_token_refills()
        self.stdout.write(f"Doplněné tokenové účty: {count}")
