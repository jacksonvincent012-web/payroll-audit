import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from accounts.models import SUSResponse


class Command(BaseCommand):
    help = "Export SUS responses to CSV for the Chapter 5 evidence pack."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default="evidence/uat_results.csv",
            help="Destination CSV path (default: evidence/uat_results.csv).",
        )

    def handle(self, *args, **options):
        responses = SUSResponse.objects.select_related("participant").order_by(
            "completed_at"
        )
        if not responses.exists():
            raise CommandError("No SUS responses have been recorded yet.")

        path = Path(options["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        header = [
            "participant",
            "role_tested",
            *[f"q{i}" for i in range(1, 11)],
            "score",
            "comment",
            "completed_at",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for response in responses:
                writer.writerow(
                    [
                        response.participant.code,
                        response.participant.role_tested,
                        *[getattr(response, f"q{i}") for i in range(1, 11)],
                        response.score,
                        response.comment,
                        response.completed_at.isoformat(),
                    ]
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {responses.count()} response(s) to {path}"
            )
        )
