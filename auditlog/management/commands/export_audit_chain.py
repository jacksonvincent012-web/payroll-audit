"""Management command: export the full audit chain to a JSON file."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from auditlog.management.commands.reseal_chain import serialise
from auditlog.models import AuditEntry
from core.chain import GENESIS


class Command(BaseCommand):
    help = "Export the full audit chain (genesis + entries) as JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default="evidence/audit_chain.json",
            help="Destination JSON path (default: evidence/audit_chain.json).",
        )

    def handle(self, *args, **options):
        entries = list(AuditEntry.objects.order_by("seq"))
        if not entries:
            raise CommandError("the audit chain is empty")
        payload = {"genesis": GENESIS, "entries": [serialise(e) for e in entries]}
        path = Path(options["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(f"Exported {len(entries)} entry/entries to {path}")
        )
