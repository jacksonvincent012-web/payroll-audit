from decimal import Decimal

from django.test import TestCase

from accounts.models import Role, User, UserRole
from expenses.models import Account, ExpenseClaim
from expenses.services import approve_claim, create_claim, submit_claim


def seed_accounts():
    Account.objects.get_or_create(
        code="1000", defaults={"name": "Cash", "kind": Account.ASSET}
    )
    Account.objects.get_or_create(
        code="5100", defaults={"name": "Tuition", "kind": Account.EXPENSE}
    )


class DashboardMoneyTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="boss", password="Pass#12345"
        )
        self.claimant = User.objects.create_user(
            username="claimant", password="Pass#12345"
        )
        self.approver = User.objects.create_user(
            username="approver", password="Pass#12345"
        )
        UserRole.objects.create(
            user=self.approver, role=Role.objects.get(code="APPROVER")
        )
        seed_accounts()

        claim = create_claim(
            self.claimant,
            reference="CLM-DASH",
            description="School fees",
            category=ExpenseClaim.TUITION,
            amount=Decimal("10000.00"),
        )
        submit_claim(self.claimant, claim)
        approve_claim(self.approver, claim)

    def test_superuser_sees_the_money_summary(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Financial summary")
        self.assertContains(response, "Money at a glance")
        self.assertContains(response, "Debited (KES)")
        self.assertContains(response, "Credited (KES)")
        self.assertContains(response, "Difference (must be 0.00)")
        self.assertContains(response, "10000.00")
        self.assertContains(response, "Breakdown")
        self.assertContains(response, "Balanced")
        self.assertContains(response, "<svg")
        self.assertContains(response, "Approved amount by category")
        self.assertContains(response, "100.0%")

    def test_superuser_can_switch_breakdown_via_dropdown(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/?view=reconciliation")
        self.assertContains(response, "Reconciliation")
        self.assertContains(response, "Debits vs credits")
        self.assertContains(response, "Approved claims vs posted claims")
        self.assertContains(response, "Reconciliation checks")
        self.assertContains(response, "<svg")

        response = self.client.get("/?view=account")
        self.assertContains(response, "5100")
        self.assertContains(response, "Tuition")
        self.assertContains(response, "Debited amount by account")
        self.assertContains(response, "<svg")

    def test_other_roles_get_a_slicer_instead_of_money(self):
        self.client.force_login(self.approver)
        response = self.client.get("/")
        self.assertContains(response, "Slicer")
        self.assertContains(response, "All entities")
        self.assertNotContains(response, "Financial summary")
        self.assertNotContains(response, "Debited (KES)")
        self.assertNotContains(response, "Approved amount by category")

    def test_entity_slicer_remembers_the_selection(self):
        self.client.force_login(self.approver)
        response = self.client.get("/?entity=ExpenseClaim")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="ExpenseClaim" selected')
