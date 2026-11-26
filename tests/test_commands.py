"""Tests for the Django management commands that ship with the audit tools."""

import tempfile
from pathlib import Path
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from accounts.models import User
from core import checkpoint
from auditlog.models import AuditEntry


class ExportCheckpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="auditor-1", password="Pass#12345")

    def test_empty_chain_raises_command_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesMessage(
                CommandError, "the audit chain is empty"
            ):
                call_command(
                    "export_checkpoint", "--path", str(Path(folder) / "cp.json")
                )

    def test_export_writes_signed_checkpoint_for_head(self):
        AuditEntry.objects.create(
            seq=1,
            actor=self.user,
            action="LOGIN",
            entity_type="USER",
            entity_id="auditor-1",
            old_values=None,
            new_values={},
            prev_hash="a" * 64,
            entry_hash="b" * 64,
        )
        with tempfile.TemporaryDirectory() as folder:
            target = str(Path(folder) / "cp.json")
            out = StringIO()
            call_command("export_checkpoint", "--path", target, stdout=out)
            self.assertIn("Checkpoint written: seq 1", out.getvalue())
            assert checkpoint.load_checkpoint(target) == (1, "b" * 64)
            assert checkpoint.checkpoint_status(target) == "Signed checkpoint seq 1 — valid"


class SendTestEmailTests(SimpleTestCase):
    def test_unconfigured_email_raises_command_error(self):
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
            EMAIL_HOST="",
            EMAIL_HOST_USER="",
            EMAIL_HOST_PASSWORD="",
        ):
            with self.assertRaisesMessage(CommandError, "Email is not configured"):
                call_command("send_test_email", "user@example.test")

    def test_configured_email_sends_via_local_backend(self):
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
            EMAIL_HOST="smtp.example.test",
            EMAIL_HOST_USER="bot@example.test",
            EMAIL_HOST_PASSWORD="secret",
            DEFAULT_FROM_EMAIL="payroll-audit@example.test",
        ):
            call_command("send_test_email", "user@example.test")
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].subject, "Payroll Audit - SMTP test")
            self.assertEqual(mail.outbox[0].to, ["user@example.test"])
            self.assertEqual(mail.outbox[0].from_email, "payroll-audit@example.test")
