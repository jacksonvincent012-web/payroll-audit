from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Role(models.Model):
    CLAIMANT = "CLAIMANT"
    HR_OFFICER = "HR_OFFICER"
    ACCOUNTANT = "ACCOUNTANT"
    APPROVER = "APPROVER"
    AUDITOR = "AUDITOR"
    ADMIN = "ADMIN"

    CODE_CHOICES = (
        (CLAIMANT, "Claimant"),
        (HR_OFFICER, "HR Officer"),
        (ACCOUNTANT, "Accountant"),
        (APPROVER, "Approver"),
        (AUDITOR, "Auditor"),
        (ADMIN, "Administrator"),
    )

    code = models.CharField(max_length=20, unique=True, choices=CODE_CHOICES)
    name = models.CharField(max_length=60)

    def __str__(self):
        return self.name


class User(AbstractUser):
    staff_no = models.CharField(max_length=20, unique=True, null=True, blank=True)
    roles = models.ManyToManyField(
        Role,
        through="UserRole",
        related_name="users",
        blank=True,
    )

    def has_role(self, code):
        return self.roles.filter(code=code).exists()

    @property
    def is_hr_officer(self):
        return self.has_role("HR_OFFICER")

    @property
    def is_approver(self):
        return self.has_role("APPROVER")


class UserRole(models.Model):
    CONFLICTS: ClassVar[dict[str, set[str]]] = {
        "ACCOUNTANT": {"APPROVER"},
        "APPROVER": {"ACCOUNTANT", "ADMIN"},
        "ADMIN": {"APPROVER"},
    }

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["user", "role"], name="uniq_user_role"),
        ]

    def clean(self):
        blocked = self.CONFLICTS.get(self.role.code, set())
        for existing in self.user.roles.all():
            if existing.code in blocked:
                raise ValidationError(
                    f"{self.role.code} cannot be combined with {existing.code}"
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username}: {self.role.code}"


class AccessRequest(models.Model):
    """A request from a new user asking for a portal account."""

    PENDING_HR = "PENDING_HR"
    PENDING_FORWARD = "PENDING_FORWARD"
    PENDING_ADMIN = "PENDING_ADMIN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"
    STATUS_CHOICES = (
        (PENDING_HR, "Pending HR verification"),
        (PENDING_FORWARD, "Pending head-dept forwarding"),
        (PENDING_ADMIN, "Pending admin decision"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
        (ESCALATED, "Escalated - under review"),
    )

    name = models.CharField(max_length=100)
    email = models.EmailField()
    staff_no = models.CharField(max_length=20, blank=True)
    role_requested = models.CharField(max_length=30)
    reason = models.TextField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING_HR)
    created_at = models.DateTimeField(default=timezone.now)

    # HR verification (step 3: checklist + note)
    identity_confirmed = models.BooleanField(default=False)
    role_justified = models.BooleanField(default=False)
    no_conflict = models.BooleanField(default=False)
    verification_note = models.TextField(blank=True)
    hr_verified_at = models.DateTimeField(null=True, blank=True)
    hr_verified_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="hr_verified_requests",
    )

    # Escalation / objection (step 5)
    escalated = models.BooleanField(default=False)
    escalation_reason = models.TextField(blank=True)
    escalated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="escalated_requests",
    )
    escalated_at = models.DateTimeField(null=True, blank=True)

    # Head department forwarding
    forwarded_at = models.DateTimeField(null=True, blank=True)
    forwarded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="forwarded_requests",
    )

    # Admin decision (step 4 delay + step 6 counter-signature)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="decided_access_requests",
    )
    decision_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.role_requested}) - {self.status}"

    def hr_checklist_complete(self):
        return self.identity_confirmed and self.role_justified and self.no_conflict

    def can_be_forwarded(self):
        return (
            self.status == self.PENDING_FORWARD
            or (self.status == self.PENDING_HR and self.hr_checklist_complete())
        )

    def can_be_decided(self):
        if self.status != self.PENDING_ADMIN:
            return False
        if self.escalated:
            return False
        if not self.forwarded_at:
            return False
        # Configurable delay (1 working day in production, 0 in tests)
        from django.conf import settings
        from datetime import timedelta

        delay_hours = getattr(settings, "ACCESS_DECISION_DELAY_HOURS", 24)
        if delay_hours <= 0:
            return True
        # 1 working day delay
        earliest = self._add_working_day(self.forwarded_at)
        from django.utils import timezone as tz

        return tz.now() >= earliest

    def _add_working_day(self, dt):
        from datetime import timedelta

        day = dt
        while True:
            day = day + timedelta(days=1)
            if day.weekday() < 5:  # Monday=0 ... Friday=4
                break
        return day

    def working_day_remaining(self):
        if not self.forwarded_at or self.can_be_decided():
            return None
        from datetime import timedelta

        earliest = self._add_working_day(self.forwarded_at)
        remaining = earliest - timezone.now()
        return max(remaining.total_seconds(), 0)


class AppMessage(models.Model):
    """An internal notification shown in the user's message centre."""

    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    KIND_CHOICES = (
        (INFO, "Information"),
        (SUCCESS, "Success"),
        (WARNING, "Warning"),
    )

    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="app_messages"
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_messages",
    )
    subject = models.CharField(max_length=200)
    body = models.TextField()
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=INFO)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_unread(self):
        return self.read_at is None

    def __str__(self):
        return f"{self.recipient.username}: {self.subject}"


class UATParticipant(models.Model):
    """An anonymised participant in user acceptance testing."""

    code = models.CharField(max_length=20, unique=True)
    role_tested = models.CharField(max_length=30)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.code} ({self.role_tested})"


class SUSResponse(models.Model):
    """A completed ten-item System Usability Scale questionnaire."""

    participant = models.OneToOneField(
        UATParticipant, on_delete=models.PROTECT, related_name="sus"
    )
    q1 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    q2 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    q3 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    q4 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    q5 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    q6 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    q7 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    q8 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    q9 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    q10 = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    completed_at = models.DateTimeField(default=timezone.now)

    @property
    def score(self):
        total = 0
        for number in range(1, 11):
            answer = getattr(self, f"q{number}")
            total += answer - 1 if number % 2 else 5 - answer
        return round(total * 2.5, 2)

    def __str__(self):
        return f"{self.participant.code}: {self.score}"
