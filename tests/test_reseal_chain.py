"""Tests for the audit chain re-seal management command."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from auditlog.models import AuditEntry
from core import checkpoint, chain
from core.chain import GENESIS, entry_hash, verify


class ResealChainTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="auditor-2", password="Pass#12345"
        )
        self.key = "ci-only-audit-hmac-key"

    def _entry(self, seq, prev_hash, action="LOGIN"):
        occurred_at = timezone.now()
        return AuditEntry.objects.create(
            seq=seq,
            actor=self.user,
            action=action,
            entity_type="USER",
            entity_id=self.user.username,
            old_values=None,
            new_values={"action": action},
            prev_hash=prev_hash,
            entry_hash=entry_hash(
                self.key.encode("utf-8"),
                seq,
                occurred_at.isoformat(),
                self.user.id,
                action,
                "USER",
                self.user.username,
                None,
                {"action": action},
                prev_hash,
            ),
            occurred_at=occurred_at,
        )

    @override_settings(AUDIT_HMAC_KEY="ci-only-audit-hmac-key")
    def test_intact_chain_is_reported_healthy(self):
        self._entry(1, GENESIS)
        out = StringIO()
        call_command("reseal_chain", stdout=out)
        self.assertIn("Chain already intact", out.getvalue())

    @override_settings(AUDIT_HMAC_KEY="ci-only-audit-hmac-key")
    def test_broken_chain_is_resealed_and_verifies(self):
        self._entry(1, GENESIS)
        self._entry(2, "c" * 64)

        out = StringIO()
        call_command("reseal_chain", stdout=out)
        self.assertIn("Re-sealed and verified", out.getvalue())

        entries = [
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
            for e in AuditEntry.objects.order_by("seq")
        ]
        ok, reason = verify(entries, self.key.encode("utf-8"))
        self.assertTrue(ok, reason)
        self.assertIsNone(reason)
