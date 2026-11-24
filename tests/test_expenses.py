from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, User, UserRole
from auditlog.models import AuditEntry
from expenses.models import Account, ExpenseClaim, LedgerEntry
from expenses.services import (
    ClaimError,
    approve_claim,
    create_claim,
    post_to_ledger,
    reject_claim,
    submit_claim,
)


def make_user(username):
    return User.objects.create_user(username=username, password="Pass#12345")


def give_role(user, code):
    return UserRole.objects.create(user=user, role=Role.objects.get(code=code))


def seed_accounts():
    Account.objects.get_or_create(
        code="1000", defaults={"name": "Cash", "kind": Account.ASSET}
    )
    for code, name in (
        ("5100", "Tuition"),
        ("5200", "Transport"),
        ("5300", "Salary"),
        ("5400", "Supplies"),
        ("5900", "Other"),
    ):
        Account.objects.get_or_create(
            code=code, defaults={"name": name, "kind": Account.EXPENSE}
        )


class ExpenseServiceTests(TestCase):
    def setUp(self):
        self.claimant = make_user("claimant")
        self.approver = make_user("approver")
        give_role(self.approver, "APPROVER")
        seed_accounts()

    def new_claim(self, **overrides):
        fields = {
            "reference": "CLM-900",
            "description": "Tuition for a student",
            "category": ExpenseClaim.TUITION,
            "amount": Decimal("15000.00"),
        }
        fields.update(overrides)
        return create_claim(self.claimant, **fields)

    def test_create_starts_as_draft(self):
        claim = self.new_claim()
        self.assertEqual(claim.status, ExpenseClaim.DRAFT)
        self.assertIsNone(claim.submitted_at)

    def test_submit_moves_to_submitted(self):
        claim = submit_claim(self.claimant, self.new_claim())
        self.assertEqual(claim.status, ExpenseClaim.SUBMITTED)
        self.assertIsNotNone(claim.submitted_at)

    def test_only_claimant_can_submit(self):
        claim = self.new_claim()
        with self.assertRaises(ClaimError):
            submit_claim(self.approver, claim)

    def test_approve_moves_to_approved(self):
        claim = self.new_claim()
        submit_claim(self.claimant, claim)
        claim = approve_claim(self.approver, claim, note="checked")
        self.assertEqual(claim.status, ExpenseClaim.APPROVED)
        self.assertEqual(claim.decided_by, self.approver)
        self.assertIsNotNone(claim.decided_at)
        self.assertEqual(claim.decision_note, "checked")

    def test_reject_moves_to_rejected(self):
        claim = self.new_claim()
        submit_claim(self.claimant, claim)
        claim = reject_claim(self.approver, claim, note="missing receipt")
        self.assertEqual(claim.status, ExpenseClaim.REJECTED)
        self.assertEqual(claim.decided_by, self.approver)

    def test_claimant_cannot_decide_own_claim(self):
        give_role(self.claimant, "APPROVER")
        claim = self.new_claim()
        submit_claim(self.claimant, claim)
        with self.assertRaises(ClaimError):
            approve_claim(self.claimant, claim)

    def test_non_approver_cannot_decide(self):
        outsider = make_user("outsider")
        claim = self.new_claim()
        submit_claim(self.claimant, claim)
        with self.assertRaises(ClaimError):
            approve_claim(outsider, claim)

    def test_cannot_approve_a_draft(self):
        claim = self.new_claim()
        with self.assertRaises(ClaimError):
            approve_claim(self.approver, claim)

    def test_cannot_decide_twice(self):
        claim = self.new_claim()
        submit_claim(self.claimant, claim)
        approve_claim(self.approver, claim)
        with self.assertRaises(ClaimError):
            approve_claim(self.approver, claim)

    def test_approval_posts_balanced_ledger(self):
        claim = self.new_claim()
        submit_claim(self.claimant, claim)
        approve_claim(self.approver, claim)
        lines = claim.ledger.all()
        self.assertEqual(lines.count(), 2)
        debits = sum(
            line.amount for line in lines if line.side == LedgerEntry.DEBIT
        )
        credits = sum(
            line.amount for line in lines if line.side == LedgerEntry.CREDIT
        )
        self.assertEqual(debits, Decimal("15000.00"))
        self.assertEqual(debits, credits)
        self.assertEqual(
            lines.get(side=LedgerEntry.DEBIT).account.code, "5100"
        )
        self.assertEqual(
            lines.get(side=LedgerEntry.CREDIT).account.code, "1000"
        )

    def test_ledger_is_not_posted_twice(self):
        claim = self.new_claim()
        submit_claim(self.claimant, claim)
        approve_claim(self.approver, claim)
        with self.assertRaises(ClaimError):
            post_to_ledger(claim)

    def test_audit_entries_written_in_order(self):
        claim = self.new_claim()
        submit_claim(self.claimant, claim)
        approve_claim(self.approver, claim)
        actions = list(
            AuditEntry.objects.order_by("seq").values_list("action", flat=True)
        )
        self.assertEqual(actions, ["CREATE", "SUBMIT", "APPROVE"])
        last = AuditEntry.objects.order_by("-seq").first()
        self.assertEqual(last.entity_type, "ExpenseClaim")
        self.assertEqual(last.entity_id, "CLM-900")


class ClaimViewTests(TestCase):
    def setUp(self):
        self.claimant = make_user("claimant")
        self.approver = make_user("approver")
        give_role(self.approver, "APPROVER")
        seed_accounts()
        self.claim = create_claim(
            self.claimant,
            reference="CLM-901",
            description="Transport to a workshop",
            category=ExpenseClaim.TRANSPORT,
            amount=Decimal("2500.00"),
        )
        submit_claim(self.claimant, self.claim)

    def test_claimant_cannot_open_claim_list(self):
        self.client.force_login(self.claimant)
        response = self.client.get(reverse("expenses:claim_list"))
        self.assertEqual(response.status_code, 403)

    def test_approver_can_open_claim_list(self):
        self.client.force_login(self.approver)
        response = self.client.get(reverse("expenses:claim_list"))
        self.assertEqual(response.status_code, 200)

    def test_approver_approves_via_view(self):
        self.client.force_login(self.approver)
        response = self.client.post(
            reverse("expenses:decide_claim", args=[self.claim.pk]),
            {"action": "APPROVE", "note": "ok"},
        )
        self.assertEqual(response.status_code, 302)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ExpenseClaim.APPROVED)

    def test_self_approval_via_view_is_refused(self):
        give_role(self.claimant, "APPROVER")
        self.client.force_login(self.claimant)
        response = self.client.post(
            reverse("expenses:decide_claim", args=[self.claim.pk]),
            {"action": "APPROVE"},
        )
        self.assertEqual(response.status_code, 302)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, ExpenseClaim.SUBMITTED)
