import importlib
import tempfile
from pathlib import Path

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from accounts.models import User
from auditlog.models import AuditEntry
from auditlog.services import record
from core.checkpoint import load_checkpoint
from core.chain import verify
from django.conf import settings
from employees.forms import EmployeeForm

EMPLOYEE = {
    "staff_no": "MKU-SEC",
    "first_name": "Ann",
    "last_name": "Njeri",
    "national_id": "12345678",
    "department": "Finance",
    "job_title": "Clerk",
    "gross_salary": "30000.00",
}


class ProductionSettingsTests(SimpleTestCase):
    def test_secure_deployment_defaults(self):
        prod = importlib.import_module("config.settings_production")
        self.assertFalse(prod.DEBUG)
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.CSRF_COOKIE_SECURE)
        self.assertTrue(prod.SESSION_COOKIE_HTTPONLY)
        self.assertTrue(prod.SECURE_SSL_REDIRECT)
        self.assertEqual(prod.SECURE_HSTS_SECONDS, 31_536_000)
        self.assertTrue(prod.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(prod.X_FRAME_OPTIONS, "DENY")


class UploadValidationTests(TestCase):
    def form_with(self, name, content, content_type):
        upload = SimpleUploadedFile(name, content, content_type=content_type)
        return EmployeeForm(data=EMPLOYEE, files={"video": upload})

    def test_rejects_executable_upload(self):
        form = self.form_with("malware.exe", b"MZ\x90\x00", "application/octet-stream")
        self.assertFalse(form.is_valid())
        self.assertIn("video", form.errors)

    def test_rejects_video_extension_with_text_content_type(self):
        form = self.form_with("clip.mp4", b"not a video", "text/plain")
        self.assertFalse(form.is_valid())
        self.assertIn("video", form.errors)

    def test_accepts_a_real_mp4(self):
        form = self.form_with("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")
        self.assertTrue(form.is_valid(), form.errors)


class LoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="limited", password="Pass#12345")

    def test_failed_logins_are_limited(self):
        for _ in range(5):
            self.assertFalse(self.client.login(username="limited", password="wrong"))
        self.assertFalse(self.client.login(username="limited", password="Pass#12345"))

    def test_success_resets_the_counter(self):
        self.assertFalse(self.client.login(username="limited", password="wrong"))
        self.assertTrue(self.client.login(username="limited", password="Pass#12345"))
        cache.clear()
        self.assertTrue(self.client.login(username="limited", password="Pass#12345"))


class CheckpointTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="audit", password="Pass#12345")

    def test_export_writes_a_readable_checkpoint(self):
        record(self.actor, "CREATE", "Employee", "E1", new={"name": "Ann"})
        last = AuditEntry.objects.order_by("-seq").first()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "chain.json"
            call_command("export_checkpoint", "--path", str(path))
            self.assertTrue(path.exists())
            self.assertEqual(load_checkpoint(str(path)), (last.seq, last.entry_hash))

    def test_checkpoint_detects_a_truncated_chain(self):
        entries = []
        for i in range(1, 4):
            record(self.actor, "CREATE", "Employee", f"E{i}", new={"n": i})
            entries.append(AuditEntry.objects.order_by("-seq").first())
        checkpoint = load_checkpoint(str(self._export(entries[-1])))
        self.assertIsNotNone(checkpoint)

        serialised = [
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
        ok, reason = verify(
            serialised[:2], settings.AUDIT_HMAC_KEY.encode(), checkpoint=checkpoint
        )
        self.assertFalse(ok)
        self.assertIn("truncat", reason.lower())

    def _export(self, entry):
        path = Path(tempfile.mkdtemp(prefix="checkpoint-")) / "chain.json"
        call_command("export_checkpoint", "--path", str(path))
        return path
