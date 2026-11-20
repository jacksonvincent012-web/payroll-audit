from django.conf import settings
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from accounts.models import User
from auditlog.models import AuditEntry
from auditlog.services import record
from core.chain import GENESIS, verify

KEY = settings.AUDIT_HMAC_KEY.encode()


def serialise(entries):
    return [
        {
            "seq": e.seq,
            "occurred_at": e.occurred_at.isoformat(),
            "actor_id": e.actor_id,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "old": e.old_values,
            "new": e.new_values,
            "prev_hash": e.prev_hash,
            "entry_hash": e.entry_hash,
        }
        for e in entries
    ]


class AuditRecordTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="writer", password="Pass#12345")
        record(self.user, "CREATE", "Employee", "E001", new={"salary": "50000.00"})
        record(
            self.user,
            "UPDATE",
            "Employee",
            "E001",
            old={"salary": "50000.00"},
            new={"salary": "60000.00"},
        )

    def test_sequence_and_links(self):
        first, second = AuditEntry.objects.order_by("seq")
        self.assertEqual(first.seq, 1)
        self.assertEqual(second.seq, 2)
        self.assertEqual(first.prev_hash, GENESIS)
        self.assertEqual(second.prev_hash, first.entry_hash)

    def test_recorded_chain_verifies(self):
        ok, reason = verify(serialise(AuditEntry.objects.order_by("seq")), KEY)
        self.assertTrue(ok, reason)

    def test_wrong_key_does_not_verify(self):
        ok, reason = verify(serialise(AuditEntry.objects.order_by("seq")), b"nope")
        self.assertFalse(ok)
        self.assertIn("seq 1", reason)

    def test_actor_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.user.delete()

    def test_entry_hash_is_unique(self):
        existing = AuditEntry.objects.get(seq=1)
        with self.assertRaises(IntegrityError):
            AuditEntry.objects.create(
                seq=99,
                actor=self.user,
                action="CREATE",
                entity_type="Employee",
                entity_id="E999",
                prev_hash="0" * 64,
                entry_hash=existing.entry_hash,
            )


class AppendOnlyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="writer", password="Pass#12345")
        record(self.user, "CREATE", "Employee", "E001", new={"salary": "50000.00"})
        record(self.user, "CREATE", "Employee", "E002", new={"salary": "40000.00"})

    def test_update_is_blocked_by_database(self):
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                AuditEntry.objects.filter(seq=1).update(action="TAMPERED")
        self.assertEqual(AuditEntry.objects.get(seq=1).action, "CREATE")

    def test_delete_is_blocked_by_database(self):
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                AuditEntry.objects.filter(seq=1).delete()
        self.assertEqual(AuditEntry.objects.count(), 2)

    def test_truncate_is_blocked_by_database(self):
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("TRUNCATE auditlog_auditentry")
        self.assertEqual(AuditEntry.objects.count(), 2)

    def test_changed_stored_values_are_detected(self):
        # Simulates a row whose stored values no longer match the signed hash,
        # e.g. a doctored backup restored by someone with table-owner rights.
        entries = serialise(AuditEntry.objects.order_by("seq"))
        entries[1]["new"] = {"salary": "1.00"}

        ok, reason = verify(entries, KEY)
        self.assertFalse(ok)
        self.assertIn("seq 2", reason)
