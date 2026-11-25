from decimal import Decimal

from django.test import TestCase

from accounts.models import Role, User, UserRole
from expenses.models import Account, ExpenseClaim
from expenses.services import create_claim, submit_claim


def make_user(username, code=None):
    user = User.objects.create_user(username=username, password="Pass#12345")
    if code:
        UserRole.objects.create(user=user, role=Role.objects.get(code=code))
    return user


class EmployeeSearchTests(TestCase):
    def setUp(self):
        self.hr = make_user("hr", "HR_OFFICER")
        self.client.force_login(self.hr)

    def test_search_narrows_the_register(self):
        from employees.services import create_employee

        create_employee(
            self.hr,
            staff_no="E100",
            first_name="Ann",
            last_name="Njeri",
            national_id="10000001",
            department="Finance",
            job_title="Clerk",
            gross_salary="30000.00",
        )
        create_employee(
            self.hr,
            staff_no="E200",
            first_name="Peter",
            last_name="Otieno",
            national_id="10000002",
            department="Stores",
            job_title="Storekeeper",
            gross_salary="25000.00",
        )
        response = self.client.get("/employees/?q=Peter")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "E200")
        self.assertNotContains(response, "E100")


class ClaimFeedbackTests(TestCase):
    def setUp(self):
        self.claimant = make_user("claimant")
        self.approver = make_user("approver", "APPROVER")
        Account.objects.get_or_create(
            code="1000", defaults={"name": "Cash", "kind": Account.ASSET}
        )
        Account.objects.get_or_create(
            code="5100", defaults={"name": "Tuition", "kind": Account.EXPENSE}
        )
        self.claim = create_claim(
            self.claimant,
            reference="CLM-UI",
            description="School fees",
            category=ExpenseClaim.TUITION,
            amount=Decimal("5000.00"),
        )
        submit_claim(self.claimant, self.claim)
        self.client.force_login(self.approver)

    def test_approve_shows_success_message(self):
        response = self.client.post(
            f"/finance/claims/{self.claim.pk}/decide/",
            {"action": "APPROVE", "note": "checked"},
            follow=True,
        )
        self.assertContains(response, "CLM-UI approved")

    def test_self_approval_shows_error_message(self):
        UserRole.objects.create(
            user=self.claimant, role=Role.objects.get(code="APPROVER")
        )
        self.client.force_login(self.claimant)
        response = self.client.post(
            f"/finance/claims/{self.claim.pk}/decide/",
            {"action": "APPROVE"},
            follow=True,
        )
        self.assertContains(response, "cannot decide their own claim")

    def test_claim_search_filters_by_reference(self):
        response = self.client.get("/finance/claims/?q=CLM-UI")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CLM-UI")
