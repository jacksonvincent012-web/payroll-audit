"""Management command: export expense claims with their approval trail to CSV."""

import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from expenses.models import ExpenseClaim


class Command(BaseCommand):
    help = "Export expense claims (with approval steps) to CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default="evidence/claims_export.csv",
            help="Destination CSV path (default: evidence/claims_export.csv).",
        )

    def handle(self, *args, **options):
        claims = (
            ExpenseClaim.objects
            .select_related("claimant", "decided_by")
            .prefetch_related("steps__approver")
            .order_by("created_at")
        )
        if not claims.exists():
            raise CommandError("No expense claims have been recorded yet.")

        rows = []
        for claim in claims:
            steps = "; ".join(
                f"L{step.level}:{step.approver.username}={step.decision}"
                for step in claim.steps.order_by("level")
            )
            rows.append(
                [
                    claim.reference,
                    claim.claimant.username if claim.claimant_id else "",
                    str(claim.amount),
                    claim.category,
                    claim.status,
                    claim.submitted_at.isoformat() if claim.submitted_at else "",
                    claim.decided_at.isoformat() if claim.decided_at else "",
                    claim.decided_by.username if claim.decided_by_id else "",
                    claim.decision_note,
                    steps,
                ]
            )

        path = Path(options["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "reference",
                    "claimant",
                    "amount",
                    "category",
                    "status",
                    "submitted_at",
                    "decided_at",
                    "decided_by",
                    "decision_note",
                    "approval_steps",
                ]
            )
            writer.writerows(rows)

        self.stdout.write(self.style.SUCCESS(f"Exported {len(rows)} claim(s) to {path}"))
