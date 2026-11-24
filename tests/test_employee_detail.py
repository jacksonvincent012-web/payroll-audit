import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role, User, UserRole
from auditlog.models import AuditEntry
from employees.services import create_employee

FIELDS = {
    "staff_no": "MKU-501",
    "first_name": "Peter",
    "last_name": "Otieno",
    "national_id": "55556666",
    "department": "Stores",
    "job_title": "Storekeeper",
    "gross_salary": "32000.00",
}


def make_user(username, *role_codes):
    user = User.objects.create_user(username=username, password="Pass#12345")
    for code in role_codes:
        UserRole.objects.create(user=user, role=Role.objects.get(code=code))
    return user


def video_file():
    return SimpleUploadedFile(
        "capture.mp4",
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


class EmployeeDetailTests(MediaMixin, TestCase):
    def setUp(self):
        self.hr = make_user("hr", "HR_OFFICER")
        self.auditor = make_user("auditor", "AUDITOR")
        self.accountant = make_user("accountant", "ACCOUNTANT")
        self.outsider = make_user("outsider")
        self.employee = create_employee(
            self.hr, **FIELDS, video=video_file()
        )

    def detail_url(self, employee=None):
        employee = employee or self.employee
        return reverse("employees:employee_detail", args=[employee.pk])

    def test_hr_officer_sees_the_video_player(self):
        self.client.force_login(self.hr)
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<video")
        self.assertContains(response, "MKU-501")
        self.assertContains(response, "Edit employee")

    def test_auditor_can_view_record_and_audit_links(self):
        self.client.force_login(self.auditor)
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<video")
        entry = AuditEntry.objects.get(
            entity_type="Employee", entity_id="MKU-501"
        )
        self.assertContains(
            response, reverse("auditlog:entry_detail", args=[entry.pk])
        )
        self.assertContains(response, "CREATE")

    def test_accountant_sees_record_but_not_the_video(self):
        self.client.force_login(self.accountant)
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<video")
        self.assertContains(response, "Your role cannot watch it")

    def test_user_without_a_role_is_refused(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.detail_url()).status_code, 403)

    def test_anonymous_user_is_sent_to_login(self):
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_audit_history_lists_the_creation_entry(self):
        self.client.force_login(self.hr)
        response = self.client.get(self.detail_url())
        self.assertContains(response, "CREATE")
        self.assertContains(response, self.hr.username)


class EmployeeVideoTests(MediaMixin, TestCase):
    def setUp(self):
        self.hr = make_user("hr", "HR_OFFICER")
        self.accountant = make_user("accountant", "ACCOUNTANT")
        self.employee = create_employee(self.hr, **FIELDS, video=video_file())

    def test_video_streams_inline_as_video(self):
        self.client.force_login(self.hr)
        response = self.client.get(
            reverse("employees:employee_video", args=[self.employee.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("video/"))
        self.assertIn("inline", response["Content-Disposition"])
        self.assertNotIn("attachment", response["Content-Disposition"])
        response.close()

    def test_role_without_permission_cannot_fetch_the_video(self):
        self.client.force_login(self.accountant)
        response = self.client.get(
            reverse("employees:employee_video", args=[self.employee.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_missing_video_returns_404(self):
        plain = create_employee(
            self.hr,
            **{**FIELDS, "staff_no": "MKU-502", "national_id": "77778888"},
        )
        self.client.force_login(self.hr)
        response = self.client.get(
            reverse("employees:employee_video", args=[plain.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_record_without_video_says_so(self):
        plain = create_employee(
            self.hr,
            **{**FIELDS, "staff_no": "MKU-503", "national_id": "88889999"},
        )
        self.client.force_login(self.hr)
        response = self.client.get(
            reverse("employees:employee_detail", args=[plain.pk])
        )
        self.assertContains(response, "No verification video on file")
