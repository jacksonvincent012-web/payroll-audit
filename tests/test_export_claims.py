"""Tests for the export_claims management command."""

import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from expenses.models import ExpenseClaim


class ExportClaimsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="claimant-1", password="Pass#12345"
        )

    def _claim(self, reference, amount, status, category="TRANSPORT"):
        return ExpenseClaim.objects.create(
            claimant=self.user,
            reference=reference,
            description="Transport to hospital",
            category=category,
            amount=amount,
            status=status,
        )

    def test_empty_claims_raise_command_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesMessage(CommandError, "No expense claims"):
                call_command(
                    "export_claims", "--path", str(Path(folder) / "claims.csv")
                )

    def test_export_writes_one_row_per_claim(self):
        self._claim("CLM-2026-0001", Decimal("100.00"), ExpenseClaim.APPROVED)
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "claims.csv")
            out = StringIO()
            call_command("export_claims", "--path", target, stdout=out)
            self.assertIn("Exported 1 claim(s) to", out.getvalue())
            text = Path(target).read_text(encoding="utf-8")
            self.assertIn("CLM-2026-0001", text)
            self.assertIn("TRANSPORT", text)
            self.assertIn("APPROVED", text)
            rows = text.strip().splitlines()
            self.assertEqual(len(rows), 2)  # header + one claim
