from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User, UserRole


def give(user, code):
    return UserRole.objects.create(user=user, role=Role.objects.get(code=code))


class SeparationOfDutyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u1", password="Pass#12345")

    def test_accountant_cannot_also_be_approver(self):
        give(self.user, "ACCOUNTANT")
        with self.assertRaises(ValidationError):
            give(self.user, "APPROVER")

    def test_approver_cannot_also_be_admin(self):
        give(self.user, "APPROVER")
        with self.assertRaises(ValidationError):
            give(self.user, "ADMIN")

    def test_compatible_roles_are_allowed(self):
        give(self.user, "ACCOUNTANT")
        give(self.user, "HR_OFFICER")
        self.assertEqual(self.user.roles.count(), 2)

    def test_duplicate_role_is_rejected(self):
        give(self.user, "AUDITOR")
        with self.assertRaises(ValidationError):
            give(self.user, "AUDITOR")


class AuditTrailAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u2", password="Pass#12345")

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(reverse("auditlog:entry_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_user_without_audit_role_is_denied(self):
        give(self.user, "CLAIMANT")
        self.client.force_login(self.user)
        response = self.client.get(reverse("auditlog:entry_list"))
        self.assertEqual(response.status_code, 403)

    def test_auditor_can_open_audit_trail(self):
        give(self.user, "AUDITOR")
        self.client.force_login(self.user)
        response = self.client.get(reverse("auditlog:entry_list"))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_open_audit_trail(self):
        root = User.objects.create_superuser(
            username="root", email="root@example.com", password="Pass#12345"
        )
        self.client.force_login(root)
        response = self.client.get(reverse("auditlog:entry_list"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_login(self):
        self.assertEqual(self.client.get(reverse("accounts:dashboard")).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:dashboard")).status_code, 200)
