"""Tests for the export_ledger management command."""

import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from expenses.models import Account, ExpenseClaim, LedgerEntry


class ExportLedgerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="auditor-4", password="Pass#12345"
        )
        self.account = Account.objects.create(
            code="5100", name="Tuition", kind="EXPENSE"
        )

    def _claim(self, reference, amount):
        return ExpenseClaim.objects.create(
            claimant=self.user,
            reference=reference,
            description="School fees",
            category="TUITION",
            amount=amount,
            status=ExpenseClaim.APPROVED,
        )

    def test_empty_ledger_raises_command_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesMessage(CommandError, "No ledger entries"):
                call_command(
                    "export_ledger", "--path", str(Path(folder) / "ledger.csv")
                )

    def test_export_writes_one_row_per_entry(self):
        claim = self._claim("CLM-2026-0002", Decimal("100.00"))
        LedgerEntry.objects.create(
            claim=claim,
            account=self.account,
            side="DEBIT",
            amount=Decimal("100.00"),
            posted_at=timezone.now(),
        )
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "ledger.csv")
            out = StringIO()
            call_command("export_ledger", "--path", target, stdout=out)
            self.assertIn("Exported 1 ledger entries", out.getvalue())
            text = Path(target).read_text(encoding="utf-8")
            self.assertIn("CLM-2026-0002", text)
            self.assertIn("5100", text)
