from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from auditlog.services import record
from accounts.notifications import notify
from expenses.models import Alert, ApprovalRule, ApprovalStep, Account, ExpenseClaim, LedgerEntry

CASH_CODE = "1000"

ALLOWED = {
    ExpenseClaim.DRAFT: {ExpenseClaim.SUBMITTED},
    ExpenseClaim.SUBMITTED: {
        ExpenseClaim.APPROVED,
        ExpenseClaim.PENDING_L2,
        ExpenseClaim.REJECTED,
    },
    ExpenseClaim.PENDING_L2: {ExpenseClaim.APPROVED, ExpenseClaim.REJECTED},
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
    claim = _transition(actor, claim, ExpenseClaim.SUBMITTED, "SUBMIT")
    _raise_alerts(actor, claim)
    return claim


def required_levels(claim):
    rule = (
        ApprovalRule.objects.filter(
            is_active=True,
            min_amount__lte=claim.amount,
            max_amount__gte=claim.amount,
        )
        .order_by("min_amount")
        .first()
    )
    return rule.required_levels if rule else 1


def _current_level(claim):
    return 2 if claim.status == ExpenseClaim.PENDING_L2 else 1


def _create_alert(claim, kind, severity, note):
    alert = Alert.objects.create(
        claim=claim, kind=kind, severity=severity, note=note
    )
    record(
        claim.claimant,
        "ALERT_RAISE",
        "Alert",
        str(alert.pk),
        new={"kind": kind, "severity": severity, "claim": claim.reference},
    )
    return alert


def _raise_alerts(actor, claim):
    duplicate = (
        ExpenseClaim.objects.filter(
            claimant=claim.claimant,
            amount=claim.amount,
            description=claim.description,
        )
        .exclude(pk=claim.pk)
        .exists()
    )
    if duplicate:
        _create_alert(
            claim,
            Alert.DUPLICATE_CLAIM,
            Alert.HIGH,
            "Same claimant, amount and description already on file",
        )
    levels = required_levels(claim)
    if levels > 1:
        _create_alert(
            claim,
            Alert.OVER_LIMIT,
            Alert.MEDIUM,
            f"Amount {claim.amount} requires {levels} approval levels",
        )


@transaction.atomic
def approve_claim(actor, claim, note=""):
    level = _current_level(claim)
    _require_decider(actor, claim)
    target = (
        ExpenseClaim.APPROVED
        if level >= required_levels(claim)
        else ExpenseClaim.PENDING_L2
    )
    claim = _transition(actor, claim, target, "APPROVE", note)
    ApprovalStep.objects.create(
        claim=claim,
        level=level,
        approver=actor,
        decision=ApprovalStep.APPROVED,
        note=note,
    )
    return claim


@transaction.atomic
def reject_claim(actor, claim, note=""):
    level = _current_level(claim)
    _require_decider(actor, claim)
    claim = _transition(actor, claim, ExpenseClaim.REJECTED, "REJECT", note)
    ApprovalStep.objects.create(
        claim=claim,
        level=level,
        approver=actor,
        decision=ApprovalStep.REJECTED,
        note=note,
    )
    return claim


@transaction.atomic
def clear_alert(actor, alert, reason):
    if not (reason or "").strip():
        raise ClaimError("a reason is required to clear an alert")
    if not (
        actor.is_superuser
        or actor.has_role("AUDITOR")
        or actor.has_role("APPROVER")
    ):
        raise ClaimError("only an auditor or approver can clear an alert")

    before = {"status": alert.status, "clear_reason": alert.clear_reason}
    alert.status = Alert.CLEARED
    alert.cleared_at = timezone.now()
    alert.cleared_by = actor
    alert.clear_reason = reason.strip()
    alert.full_clean()
    alert.save()
    record(
        actor,
        "ALERT_CLEAR",
        "Alert",
        str(alert.pk),
        old=before,
        new={"status": alert.status, "clear_reason": alert.clear_reason},
    )
    return alert


def _require_decider(actor, claim):
    if claim.claimant_id == actor.pk:
        raise ClaimError("a claimant cannot decide their own claim")
    if not actor.is_superuser and not actor.has_role("APPROVER"):
        raise ClaimError("only an approver can decide claims")
    if claim.steps.filter(approver=actor).exists():
        raise ClaimError("this approver has already decided this claim")


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
    if new_status in (ExpenseClaim.APPROVED, ExpenseClaim.REJECTED):
        notify(
            claim.claimant,
            f"Claim {claim.reference} {new_status.lower()}",
            f"Your claim {claim.reference} for KES {claim.amount} was "
            f"{new_status.lower()} by {actor.username}. {note}".strip(),
            kind="SUCCESS" if new_status == ExpenseClaim.APPROVED else "WARNING",
            sender=actor,
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
