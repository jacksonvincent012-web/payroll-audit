from decimal import Decimal

from django.test import TestCase

from accounts.models import Role, User, UserRole
from auditlog.models import AuditEntry
from expenses.models import Account, Alert, ApprovalStep, ExpenseClaim, LedgerEntry
from expenses.services import (
    ClaimError,
    approve_claim,
    clear_alert,
    create_claim,
    submit_claim,
)


class ExpenseControlTests(TestCase):
    def setUp(self):
        self.claimant = User.objects.create_user(
            username="claimant", password="Pass#12345"
        )
        self.approver1 = User.objects.create_user(
            username="approver1", password="Pass#12345"
        )
        self.approver2 = User.objects.create_user(
            username="approver2", password="Pass#12345"
        )
        for user in (self.approver1, self.approver2):
            UserRole.objects.create(
                user=user, role=Role.objects.get(code="APPROVER")
            )
        Account.objects.get_or_create(
            code="1000", defaults={"name": "Cash", "kind": Account.ASSET}
        )
        Account.objects.get_or_create(
            code="5100", defaults={"name": "Tuition", "kind": Account.EXPENSE}
        )

    def new_claim(self, amount, reference="CLM-CTRL", description="School fees"):
        return create_claim(
            self.claimant,
            reference=reference,
            description=description,
            category=ExpenseClaim.TUITION,
            amount=Decimal(amount),
        )

    def test_low_value_claim_needs_one_approval(self):
        claim = self.new_claim("10000.00")
        submit_claim(self.claimant, claim)
        claim = approve_claim(self.approver1, claim, note="checked")
        self.assertEqual(claim.status, ExpenseClaim.APPROVED)
        self.assertEqual(claim.steps.count(), 1)
        self.assertEqual(claim.ledger.count(), 2)

    def test_high_value_claim_needs_two_approvals(self):
        claim = self.new_claim("150000.00")
        submit_claim(self.claimant, claim)

        self.assertEqual(
            Alert.objects.filter(
                claim=claim, kind=Alert.OVER_LIMIT, severity=Alert.MEDIUM
            ).count(),
            1,
        )

        first = approve_claim(self.approver1, claim, note="first level")
        self.assertEqual(first.status, ExpenseClaim.PENDING_L2)
        self.assertFalse(claim.ledger.exists())

        second = approve_claim(self.approver2, claim, note="second level")
        self.assertEqual(second.status, ExpenseClaim.APPROVED)
        self.assertEqual(claim.steps.count(), 2)
        self.assertEqual(claim.ledger.count(), 2)

        sides = [line.side for line in claim.ledger.all()]
        self.assertIn(LedgerEntry.DEBIT, sides)
        self.assertIn(LedgerEntry.CREDIT, sides)

    def test_same_approver_cannot_decide_twice(self):
        claim = self.new_claim("150000.00")
        submit_claim(self.claimant, claim)
        approve_claim(self.approver1, claim)
        with self.assertRaises(ClaimError):
            approve_claim(self.approver1, claim)

    def test_duplicate_claim_raises_high_alert(self):
        first = self.new_claim("25000.00", "CLM-A", "Workshop transport")
        submit_claim(self.claimant, first)

        second = self.new_claim("25000.00", "CLM-B", "Workshop transport")
        submit_claim(self.claimant, second)

        alert = Alert.objects.get(
            claim=second, kind=Alert.DUPLICATE_CLAIM
        )
        self.assertEqual(alert.severity, Alert.HIGH)
        self.assertTrue(alert.is_open())

    def test_clear_alert_requires_reason_and_is_audited(self):
        claim = self.new_claim("150000.00")
        submit_claim(self.claimant, claim)
        alert = Alert.objects.get(claim=claim, kind=Alert.OVER_LIMIT)

        with self.assertRaises(ClaimError):
            clear_alert(self.approver1, alert, "   ")

        cleared = clear_alert(self.approver1, alert, "Approved by finance policy")
        self.assertEqual(cleared.status, Alert.CLEARED)
        self.assertEqual(cleared.cleared_by, self.approver1)
        self.assertFalse(cleared.is_open())
        self.assertTrue(
            AuditEntry.objects.filter(
                action="ALERT_CLEAR", entity_type="Alert"
            ).exists()
        )

    def test_claimant_cannot_clear_alert(self):
        claim = self.new_claim("150000.00")
        submit_claim(self.claimant, claim)
        alert = Alert.objects.get(claim=claim, kind=Alert.OVER_LIMIT)
        with self.assertRaises(ClaimError):
            clear_alert(self.claimant, alert, "let it go")

    def test_alert_list_view_requires_the_right_role(self):
        self.client.force_login(self.approver1)
        response = self.client.get("/finance/alerts/")
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.claimant)
        response = self.client.get("/finance/alerts/")
        self.assertEqual(response.status_code, 403)
