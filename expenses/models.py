from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Account(models.Model):
    ASSET = "ASSET"
    EXPENSE = "EXPENSE"

    KIND_CHOICES = (
        (ASSET, "Asset"),
        (EXPENSE, "Expense"),
    )

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"


class ExpenseClaim(models.Model):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PENDING_L2 = "PENDING_L2"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

    STATUS_CHOICES = (
        (DRAFT, "Draft"),
        (SUBMITTED, "Submitted"),
        (PENDING_L2, "Pending second approval"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    )

    TUITION = "TUITION"
    TRANSPORT = "TRANSPORT"
    SALARY = "SALARY"
    SUPPLIES = "SUPPLIES"
    OTHER = "OTHER"

    CATEGORY_CHOICES = (
        (TUITION, "School fees"),
        (TRANSPORT, "Transport"),
        (SALARY, "Salary"),
        (SUPPLIES, "Supplies"),
        (OTHER, "Other"),
    )

    CATEGORY_ACCOUNT = {
        TUITION: "5100",
        TRANSPORT: "5200",
        SALARY: "5300",
        SUPPLIES: "5400",
        OTHER: "5900",
    }

    claimant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="claims",
    )
    reference = models.CharField(max_length=20, unique=True)
    description = models.CharField(max_length=200)
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=OTHER,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="decided_claims",
    )
    decision_note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=Decimal("0.01")),
                name="claim_amount_positive",
            ),
        ]

    def __str__(self):
        return f"{self.reference} {self.amount} ({self.status})"

    def snapshot(self):
        return {
            "reference": self.reference,
            "claimant": self.claimant.username,
            "description": self.description,
            "category": self.category,
            "amount": str(self.amount),
            "status": self.status,
            "decided_by": self.decided_by.username if self.decided_by else None,
        }


class LedgerEntry(models.Model):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"

    SIDE_CHOICES = (
        (DEBIT, "Debit"),
        (CREDIT, "Credit"),
    )

    claim = models.ForeignKey(
        ExpenseClaim,
        on_delete=models.PROTECT,
        related_name="ledger",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    side = models.CharField(max_length=6, choices=SIDE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="ledger_amount_positive",
            ),
        ]

    def __str__(self):
        return f"{self.side} {self.account.code} {self.amount}"


class ApprovalRule(models.Model):
    """Routes a claim by amount to the required number of approval levels."""

    name = models.CharField(max_length=60)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2)
    required_levels = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["min_amount"]

    def __str__(self):
        return (
            f"{self.name}: {self.min_amount}-{self.max_amount} "
            f"-> {self.required_levels} level(s)"
        )


class ApprovalStep(models.Model):
    """One decision in a claim's approval trail."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DECISION_CHOICES = ((APPROVED, "Approved"), (REJECTED, "Rejected"))

    claim = models.ForeignKey(
        ExpenseClaim, on_delete=models.PROTECT, related_name="steps"
    )
    level = models.PositiveSmallIntegerField()
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="approval_steps"
    )
    decision = models.CharField(max_length=8, choices=DECISION_CHOICES)
    note = models.CharField(max_length=200, blank=True)
    decided_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["level"]
        constraints = [
            models.UniqueConstraint(
                fields=["claim", "level"], name="one_decision_per_level"
            ),
        ]

    def __str__(self):
        return f"{self.claim.reference} level {self.level}: {self.decision}"


class Alert(models.Model):
    """A raised flag that a human must resolve, with a logged reason."""

    DUPLICATE_CLAIM = "DUPLICATE_CLAIM"
    OVER_LIMIT = "OVER_LIMIT"

    KIND_CHOICES = (
        (DUPLICATE_CLAIM, "Possible duplicate claim"),
        (OVER_LIMIT, "Over spending limit"),
    )
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    SEVERITY_CHOICES = ((HIGH, "High"), (MEDIUM, "Medium"), (LOW, "Low"))
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    UNDER_REVIEW = "UNDER_REVIEW"
    CLEARED = "CLEARED"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"
    STATUS_CHOICES = (
        (OPEN, "Open"),
        (ASSIGNED, "Assigned"),
        (UNDER_REVIEW, "Under review"),
        (CLEARED, "Cleared"),
        (ESCALATED, "Escalated"),
        (CLOSED, "Closed"),
    )

    claim = models.ForeignKey(
        ExpenseClaim, on_delete=models.PROTECT, related_name="alerts"
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    severity = models.CharField(max_length=6, choices=SEVERITY_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=OPEN)
    note = models.CharField(max_length=200, blank=True)
    raised_at = models.DateTimeField(default=timezone.now)
    cleared_at = models.DateTimeField(null=True, blank=True)
    cleared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cleared_alerts",
    )
    clear_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-raised_at"]

    def __str__(self):
        return f"{self.severity} {self.kind} on {self.claim.reference}"

    def is_open(self):
        return self.status in (self.OPEN, self.ASSIGNED, self.UNDER_REVIEW, self.ESCALATED)
