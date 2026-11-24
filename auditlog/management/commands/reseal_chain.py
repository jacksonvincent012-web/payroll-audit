"""Management command: re-seal the audit chain after an HMAC key rotation."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from auditlog.models import AuditEntry
from core.chain import GENESIS, entry_hash, verify

DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS auditlog_no_row_mutation ON auditlog_auditentry;
DROP TRIGGER IF EXISTS auditlog_no_truncate ON auditlog_auditentry;
"""

RESTORE_TRIGGERS = """
CREATE TRIGGER auditlog_no_row_mutation
BEFORE UPDATE OR DELETE ON auditlog_auditentry
FOR EACH ROW EXECUTE FUNCTION auditlog_deny_mutation();

CREATE TRIGGER auditlog_no_truncate
BEFORE TRUNCATE ON auditlog_auditentry
FOR EACH STATEMENT EXECUTE FUNCTION auditlog_deny_mutation();
"""


def serialise(entry):
    return {
        "seq": entry.seq,
        "occurred_at": entry.occurred_at.isoformat(),
        "actor_id": entry.actor_id,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "old": entry.old_values,
        "new": entry.new_values,
        "prev_hash": entry.prev_hash,
        "entry_hash": entry.entry_hash,
    }


class Command(BaseCommand):
    help = (
        "One-time migration: recompute every audit hash with the current "
        "AUDIT_HMAC_KEY after a deliberate key rotation."
    )

    def handle(self, *args, **options):
        key = settings.AUDIT_HMAC_KEY.encode("utf-8")
        entries = list(AuditEntry.objects.order_by("seq"))
        ok, reason = verify([serialise(e) for e in entries], key)
        if ok:
            self.stdout.write(self.style.SUCCESS("Chain already intact — nothing to do."))
            return

        self.stdout.write(
            self.style.WARNING(
                f"Chain verifies as broken ({reason}). "
                f"Re-sealing {len(entries)} entries with the current key."
            )
        )

        previous = GENESIS
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(DROP_TRIGGERS)
            for entry in entries:
                entry.prev_hash = previous
                entry.entry_hash = entry_hash(
                    key,
                    entry.seq,
                    entry.occurred_at.isoformat(),
                    entry.actor_id,
                    entry.action,
                    entry.entity_type,
                    entry.entity_id,
                    entry.old_values,
                    entry.new_values,
                    previous,
                )
                entry.save(update_fields=["prev_hash", "entry_hash"])
                previous = entry.entry_hash
            with connection.cursor() as cursor:
                cursor.execute(RESTORE_TRIGGERS)

        refreshed = list(AuditEntry.objects.order_by("seq"))
        ok, reason = verify([serialise(e) for e in refreshed], key)
        if not ok:
            raise CommandError(f"Re-seal failed verification: {reason}")
        self.stdout.write(
            self.style.SUCCESS(f"Re-sealed and verified {len(refreshed)} entries.")
        )
