from django.core.management.base import BaseCommand, CommandError

from auditlog.models import AuditEntry
from core.checkpoint import checkpoint_status, save_checkpoint


class Command(BaseCommand):
    help = "Export the current chain head as an external checkpoint."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            help="Override the checkpoint file path for this run.",
        )

    def handle(self, *args, **options):
        last = AuditEntry.objects.order_by("-seq").first()
        if last is None:
            raise CommandError("the audit chain is empty")
        target = save_checkpoint(last.seq, last.entry_hash, path=options.get("path"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Checkpoint written: seq {last.seq}, hash {last.entry_hash[:16]} -> {target}"
            )
        )
        self.stdout.write(checkpoint_status(str(target)))
