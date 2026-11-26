"""Management command: export the double-entry ledger to CSV."""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from expenses.models import Account, ExpenseClaim, LedgerEntry


class Command(BaseCommand):
    help = "Export the double-entry ledger to CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default="evidence/ledger_export.csv",
            help="Destination CSV path (default: evidence/ledger_export.csv).",
        )

    def handle(self, *args, **options):
        entries = (
            LedgerEntry.objects.select_related("claim", "account").order_by("posted_at")
        )
        if not entries.exists():
            raise CommandError("No ledger entries have been recorded yet.")

        rows = []
        for entry in entries:
            rows.append(
                [
                    entry.claim.reference if entry.claim_id else "",
                    entry.account.code,
                    entry.side,
                    str(entry.amount),
                    entry.posted_at.isoformat(),
                ]
            )

        path = Path(options["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["claim", "account", "side", "amount", "posted_at"])
            writer.writerows(rows)

        self.stdout.write(
            self.style.SUCCESS(f"Exported {len(rows)} ledger entries to {path}")
        )
