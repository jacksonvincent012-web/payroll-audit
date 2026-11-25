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
