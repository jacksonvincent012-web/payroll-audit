import shutil
import tempfile
from pathlib import Path

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.models import Role, User, UserRole
from core.emailing import is_configured, missing_settings
from employees.services import create_employee

SMTP_UNCONFIGURED = dict(
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="",
    EMAIL_HOST_USER="",
    EMAIL_HOST_PASSWORD="",
)

SMTP_LOCAL = dict(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    EMAIL_HOST="smtp.example.test",
    EMAIL_HOST_USER="bot@example.test",
    EMAIL_HOST_PASSWORD="secret",
    DEFAULT_FROM_EMAIL="payroll-audit@example.test",
)

EMPLOYEE_FIELDS = {
    "staff_no": "MKU-777",
    "first_name": "Mary",
    "last_name": "Wanjiku",
    "national_id": "99887766",
    "department": "Finance",
    "job_title": "Accountant",
    "gross_salary": "45000.00",
}


def video_file():
    return SimpleUploadedFile(
        "verification.mp4",
        b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64,
        content_type="video/mp4",
    )


class MediaMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="payroll-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        cls.addClassCleanup(cls._media_override.disable)
        cls.addClassCleanup(shutil.rmtree, cls._media_root, True)


@override_settings(**SMTP_UNCONFIGURED)
class ConfigurationCheckTests(TestCase):
    def test_missing_settings_reports_blank_credentials(self):
        self.assertEqual(
            set(missing_settings()),
            {"EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"},
        )

    def test_unconfigured_smtp_is_not_ready(self):
        self.assertFalse(is_configured())

    @override_settings(**SMTP_LOCAL)
    def test_local_backend_is_ready(self):
        self.assertTrue(is_configured())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_console_backend_needs_no_credentials(self):
        self.assertEqual(missing_settings(), [])
        self.assertTrue(is_configured())


@override_settings(**SMTP_UNCONFIGURED)
class SendTestEmailCommandTests(TestCase):
    def test_refuses_to_send_without_credentials(self):
        with self.assertRaises(CommandError) as caught:
            call_command("send_test_email", "boss@example.test")
        self.assertIn("EMAIL_HOST", str(caught.exception))

    @override_settings(**SMTP_LOCAL)
    def test_sends_one_message(self):
        call_command("send_test_email", "boss@example.test")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["boss@example.test"])
        self.assertIn("SMTP test", message.subject)
        self.assertEqual(message.from_email, "payroll-audit@example.test")


@override_settings(**SMTP_LOCAL)
class VerificationEmailTests(MediaMixin, TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(
            username="hr", password="Pass#12345", email="hr@example.test"
        )
        self.approver = User.objects.create_user(
            username="approver", password="Pass#12345", email="approver@example.test"
        )
        UserRole.objects.create(
            user=self.approver, role=Role.objects.get(code="APPROVER")
        )

    def test_video_employee_notifies_approver_with_attachment(self):
        employee = create_employee(
            self.actor, **EMPLOYEE_FIELDS, video=video_file()
        )
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["approver@example.test"])
        self.assertIn("MKU-777", message.subject)
        self.assertEqual(len(message.attachments), 1)
        name, content, mime = message.attachments[0]
        self.assertTrue(name.endswith(".mp4"))
        self.assertEqual(mime, "video/mp4")

    def test_employee_without_video_sends_no_email(self):
        create_employee(self.actor, **EMPLOYEE_FIELDS)
        self.assertEqual(mail.outbox, [])

    def test_approver_without_email_is_skipped(self):
        self.approver.email = ""
        self.approver.save()
        create_employee(self.actor, **EMPLOYEE_FIELDS, video=video_file())
        self.assertEqual(mail.outbox, [])


@override_settings(**SMTP_UNCONFIGURED)
class UnconfiguredVerificationTests(MediaMixin, TestCase):
    def test_missing_smtp_is_skipped_without_breaking_the_save(self):
        actor = User.objects.create_user(username="hr", password="Pass#12345")
        approver = User.objects.create_user(
            username="approver", password="Pass#12345", email="approver@example.test"
        )
        UserRole.objects.create(
            user=approver, role=Role.objects.get(code="APPROVER")
        )

        employee = create_employee(actor, **EMPLOYEE_FIELDS, video=video_file())

        self.assertEqual(employee.staff_no, "MKU-777")
        self.assertTrue(Path(employee.video.path).exists())
        self.assertFalse(is_configured())
