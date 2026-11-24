from django.core.management.base import BaseCommand, CommandError

from core.emailing import missing_settings, send_test_message


class Command(BaseCommand):
    help = "Send a test email to confirm the SMTP settings work."

    def add_arguments(self, parser):
        parser.add_argument(
            "recipient",
            help="Address that should receive the test message.",
        )

    def handle(self, *args, **options):
        missing = missing_settings()
        if missing:
            raise CommandError(
                "Email is not configured. Still blank in .env: "
                + ", ".join(missing)
            )

        recipient = options["recipient"]
        sent = send_test_message(recipient)
        self.stdout.write(
            self.style.SUCCESS(f"Sent {sent} message(s) to {recipient}")
        )
