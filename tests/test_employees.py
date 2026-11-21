from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User, UserRole
from auditlog.models import AuditEntry
from employees.services import create_employee, update_employee

FIELDS = {
    "staff_no": "MKU-100",
    "first_name": "Ann",
    "last_name": "Njeri",
    "national_id": "11112222",
    "department": "Finance",
    "job_title": "Clerk",
    "gross_salary": "30000.00",
}


class EmployeeServiceTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="hr", password="Pass#12345")

    def test_create_writes_one_audit_entry(self):
        employee = create_employee(self.actor, **FIELDS)
        entries = AuditEntry.objects.all()
        self.assertEqual(entries.count(), 1)
        entry = entries.get()
        self.assertEqual(entry.action, "CREATE")
        self.assertEqual(entry.entity_type, "Employee")
        self.assertEqual(entry.entity_id, "MKU-100")
        self.assertEqual(entry.new_values["gross_salary"], "30000.00")
        self.assertIsNone(entry.old_values)
        self.assertTrue(employee.pk)

    def test_update_records_old_and_new(self):
        employee = create_employee(self.actor, **FIELDS)
        update_employee(self.actor, employee, gross_salary="35000.00")
        entry = AuditEntry.objects.order_by("-seq").first()
        self.assertEqual(entry.action, "UPDATE")
        self.assertEqual(entry.old_values["gross_salary"], "30000.00")
        self.assertEqual(entry.new_values["gross_salary"], "35000.00")

    def test_noop_update_writes_nothing(self):
        employee = create_employee(self.actor, **FIELDS)
        before = AuditEntry.objects.count()
        update_employee(self.actor, employee, gross_salary="30000.00")
        self.assertEqual(AuditEntry.objects.count(), before)

    def test_staff_no_cannot_change(self):
        employee = create_employee(self.actor, **FIELDS)
        with self.assertRaises(ValueError):
            update_employee(self.actor, employee, staff_no="MKU-999")

    def test_unknown_field_is_refused(self):
        employee = create_employee(self.actor, **FIELDS)
        with self.assertRaises(ValueError):
            update_employee(self.actor, employee, gross_salar="99999.00")

    def test_negative_salary_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_employee(self.actor, **{**FIELDS, "gross_salary": "-1.00"})


class EmployeeAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="worker", password="Pass#12345")

    def login_with(self, code):
        UserRole.objects.create(user=self.user, role=Role.objects.get(code=code))
        self.client.force_login(self.user)

    def test_claimant_cannot_open_form(self):
        self.login_with("CLAIMANT")
        response = self.client.get(reverse("employees:employee_create"))
        self.assertEqual(response.status_code, 403)

    def test_auditor_can_view_but_not_edit(self):
        self.login_with("AUDITOR")
        self.assertEqual(
            self.client.get(reverse("employees:employee_list")).status_code, 200
        )
        self.assertEqual(
            self.client.get(reverse("employees:employee_create")).status_code, 403
        )

    def test_hr_officer_can_open_form(self):
        self.login_with("HR_OFFICER")
        response = self.client.get(reverse("employees:employee_create"))
        self.assertEqual(response.status_code, 200)
