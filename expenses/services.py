from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from auditlog.services import record
from expenses.models import Account, ExpenseClaim, LedgerEntry

CASH_CODE = "1000"

ALLOWED = {
    ExpenseClaim.DRAFT: {ExpenseClaim.SUBMITTED},
    ExpenseClaim.SUBMITTED: {ExpenseClaim.APPROVED, ExpenseClaim.REJECTED},
}


class ClaimError(Exception):
    """Raised when a claim operation is not permitted."""


@transaction.atomic
def create_claim(actor, **fields):
    claim = ExpenseClaim(claimant=actor, **fields)
    claim.full_clean()
    claim.save()

    record(actor, "CREATE", "ExpenseClaim", claim.reference, new=claim.snapshot())
    return claim


@transaction.atomic
def submit_claim(actor, claim):
    if claim.claimant_id != actor.pk:
        raise ClaimError("only the claimant can submit this claim")
    return _transition(actor, claim, ExpenseClaim.SUBMITTED, "SUBMIT")


@transaction.atomic
def approve_claim(actor, claim, note=""):
    _require_decider(actor, claim)
    return _transition(actor, claim, ExpenseClaim.APPROVED, "APPROVE", note)


@transaction.atomic
def reject_claim(actor, claim, note=""):
    _require_decider(actor, claim)
    return _transition(actor, claim, ExpenseClaim.REJECTED, "REJECT", note)


def _require_decider(actor, claim):
    if claim.claimant_id == actor.pk:
        raise ClaimError("a claimant cannot decide their own claim")
    if not actor.is_superuser and not actor.has_role("APPROVER"):
        raise ClaimError("only an approver can decide claims")


def _transition(actor, claim, new_status, action, note=""):
    if new_status not in ALLOWED.get(claim.status, set()):
        raise ClaimError(f"cannot go from {claim.status} to {new_status}")

    before = claim.snapshot()

    claim.status = new_status
    if new_status == ExpenseClaim.SUBMITTED:
        claim.submitted_at = timezone.now()
    else:
        claim.decided_at = timezone.now()
        claim.decided_by = actor
        claim.decision_note = note

    claim.full_clean()
    claim.save()

    if new_status == ExpenseClaim.APPROVED:
        post_to_ledger(claim)

    record(
        actor,
        action,
        "ExpenseClaim",
        claim.reference,
        old=before,
        new=claim.snapshot(),
    )
    return claim


def post_to_ledger(claim):
    """Post the double entry for an approved claim: expense debit, cash credit."""
    if claim.ledger.exists():
        raise ClaimError(f"{claim.reference} is already posted to the ledger")

    try:
        expense_account = Account.objects.get(
            code=ExpenseClaim.CATEGORY_ACCOUNT[claim.category]
        )
        cash_account = Account.objects.get(code=CASH_CODE)
    except Account.DoesNotExist as exc:
        raise ClaimError(f"chart of accounts is incomplete: {exc}") from exc

    amount = claim.amount

    LedgerEntry.objects.create(
        claim=claim,
        account=expense_account,
        side=LedgerEntry.DEBIT,
        amount=amount,
    )
    LedgerEntry.objects.create(
        claim=claim,
        account=cash_account,
        side=LedgerEntry.CREDIT,
        amount=amount,
    )

    debits = _total(claim, LedgerEntry.DEBIT)
    credits = _total(claim, LedgerEntry.CREDIT)
    if debits != credits:
        raise ClaimError(
            f"unbalanced posting for {claim.reference}: debit {debits} credit {credits}"
        )


def _total(claim, side):
    total = Decimal("0.00")
    for line in claim.ledger.filter(side=side):
        total += line.amount
    return total
