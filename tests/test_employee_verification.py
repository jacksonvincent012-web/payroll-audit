from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User, UserRole
from employees.models import (
    AttendanceImport,
    AttendanceRecord,
    Employee,
    PayrollEntry,
)
from employees.services import create_employee, import_attendance, import_payroll
from expenses.models import Alert


def make_user(username, code=None):
    user = User.objects.create_user(username=username, password="Pass#12345")
    if code:
        UserRole.objects.create(user=user, role=Role.objects.get(code=code))
    return user


def employee_fields(**overrides):
    fields = {
        "staff_no": "E001",
        "first_name": "Ann",
        "last_name": "Njeri",
        "national_id": "11112222",
        "department": "Finance",
        "job_title": "Clerk",
        "gross_salary": "30000.00",
    }
    fields.update(overrides)
    return fields


def csv_upload(name, text):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


class DuplicateDetectionTests(TestCase):
    def setUp(self):
        self.hr = make_user("hr", "HR_OFFICER")

    def test_normalised_bank_duplicate_raises_high_alert(self):
        create_employee(
            self.hr,
            **employee_fields(bank_account="012-345-6789"),
        )
        second = create_employee(
            self.hr,
            **employee_fields(
                staff_no="E002",
                national_id="22223333",
                bank_account="0123456789 ",
            ),
        )
        alert = Alert.objects.get(employee=second, kind=Alert.DUPLICATE_BANK)
        self.assertEqual(alert.severity, Alert.HIGH)

    def test_normalised_phone_duplicate_raises_low_alert(self):
        create_employee(self.hr, **employee_fields(phone="+254712345678"))
        second = create_employee(
            self.hr,
            **employee_fields(
                staff_no="E003", national_id="33334444", phone="0712 345 678"
            ),
        )
        alert = Alert.objects.get(employee=second, kind=Alert.DUPLICATE_PHONE)
        self.assertEqual(alert.severity, Alert.LOW)

    def test_same_check_does_not_raise_twice(self):
        create_employee(self.hr, **employee_fields(bank_account="999888777"))
        second = create_employee(
            self.hr,
            **employee_fields(
                staff_no="E004", national_id="44445555", bank_account="999888777"
            ),
        )
        second.save()
        self.assertEqual(
            Alert.objects.filter(
                employee=second, kind=Alert.DUPLICATE_BANK
            ).count(),
            1,
        )


class ImportAndPayrollTests(TestCase):
    def setUp(self):
        self.hr = make_user("hr", "HR_OFFICER")
        self.employee = create_employee(
            self.hr, **employee_fields(is_active=False)
        )

    def test_attendance_import_records_file_hash(self):
        upload = csv_upload(
            "attendance.csv",
            "staff_no,date,hours\nE001,2026-11-03,8\nE001,2026-11-04,7.5\n",
        )
        batch = import_attendance(self.hr, upload)
        self.assertEqual(batch.row_count, 2)
        self.assertEqual(len(batch.file_hash), 64)
        self.assertEqual(AttendanceRecord.objects.filter(batch=batch).count(), 2)

    def test_payroll_import_raises_inactive_and_missing_attendance(self):
        upload = csv_upload(
            "payroll.csv", "staff_no,gross_salary\nE001,45000.00\n"
        )
        count = import_payroll(self.hr, upload, "2026-11")
        self.assertEqual(count, 1)
        self.assertEqual(PayrollEntry.objects.count(), 1)
        self.assertTrue(
            Alert.objects.filter(
                employee=self.employee, kind=Alert.INACTIVE_ON_PAYROLL
            ).exists()
        )
        self.assertTrue(
            Alert.objects.filter(
                employee=self.employee, kind=Alert.MISSING_ATTENDANCE
            ).exists()
        )

    def test_attendance_present_suppresses_missing_alert(self):
        attendance = csv_upload(
            "a.csv", "staff_no,date\nE001,2026-11-05\n"
        )
        import_attendance(self.hr, attendance)
        payroll = csv_upload("p.csv", "staff_no,gross_salary\nE001,45000\n")
        import_payroll(self.hr, payroll, "2026-11")
        self.assertFalse(
            Alert.objects.filter(
                employee=self.employee, kind=Alert.MISSING_ATTENDANCE
            ).exists()
        )


class VerificationAlertViewTests(TestCase):
    def setUp(self):
        self.hr = make_user("hr", "HR_OFFICER")
        self.approver = make_user("approver", "APPROVER")
        self.claimant = make_user("claimant")
        self.employee = create_employee(
            self.hr, **employee_fields(bank_account="123123123")
        )
        create_employee(
            self.hr,
            **employee_fields(
                staff_no="E009", national_id="99990000", bank_account="123123123"
            ),
        )

    def test_hr_can_open_verification_alerts(self):
        self.client.force_login(self.hr)
        response = self.client.get(reverse("employees:verification_alerts"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shared bank account")

    def test_user_without_role_is_denied(self):
        self.client.force_login(self.claimant)
        response = self.client.get(reverse("employees:verification_alerts"))
        self.assertEqual(response.status_code, 403)

    def test_clearing_requires_a_reason(self):
        alert = Alert.objects.filter(kind=Alert.DUPLICATE_BANK).first()
        self.assertIsNotNone(alert)
        self.client.force_login(self.approver)
        response = self.client.post(
            reverse("employees:verification_alerts"),
            {"alert_id": alert.pk, "reason": "   "},
        )
        self.assertEqual(response.status_code, 302)
        alert.refresh_from_db()
        self.assertTrue(alert.is_open())

    def test_import_pages_are_role_gated(self):
        self.client.force_login(self.hr)
        self.assertEqual(
            self.client.get(reverse("employees:attendance_import")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("employees:payroll_import")).status_code, 200
        )
        self.client.force_login(self.claimant)
        self.assertEqual(
            self.client.get(reverse("employees:attendance_import")).status_code, 403
        )
