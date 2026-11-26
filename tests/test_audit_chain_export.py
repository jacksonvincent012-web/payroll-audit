"""Tests for the full audit chain JSON export command."""

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from auditlog.models import AuditEntry
from core.chain import GENESIS, entry_hash


class ExportAuditChainTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="auditor-3", password="Pass#12345"
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

    def test_empty_chain_raises_command_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesMessage(CommandError, "the audit chain is empty"):
                call_command(
                    "export_audit_chain", "--path", str(Path(folder) / "chain.json")
                )

    def test_export_writes_genesis_and_entries(self):
        self._entry(1, GENESIS)
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "chain.json")
            out = StringIO()
            call_command("export_audit_chain", "--path", target, stdout=out)
            self.assertIn("Exported 1 entry/entries", out.getvalue())
            data = json.loads(Path(target).read_text(encoding="utf-8"))
            self.assertEqual(data["genesis"], GENESIS)
            self.assertEqual(len(data["entries"]), 1)
            self.assertEqual(data["entries"][0]["seq"], 1)
            self.assertEqual(data["entries"][0]["action"], "LOGIN")
