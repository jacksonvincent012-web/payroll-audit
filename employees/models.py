from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.normalise import normalise_bank, normalise_id, normalise_phone


class Employee(models.Model):
    staff_no = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    national_id = models.CharField(max_length=20, unique=True)
    department = models.CharField(max_length=60)
    job_title = models.CharField(max_length=60)
    gross_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    is_active = models.BooleanField(default=True)
    is_draft = models.BooleanField(default=False)
    video = models.FileField(upload_to="videos/", blank=True, null=True)
    bank_account = models.CharField(max_length=40, blank=True)
    bank_account_norm = models.CharField(max_length=40, blank=True, db_index=True)
    phone = models.CharField(max_length=30, blank=True)
    phone_norm = models.CharField(max_length=30, blank=True, db_index=True)
    national_id_norm = models.CharField(max_length=20, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["staff_no"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(gross_salary__gt=0),
                name="employee_gross_salary_positive",
            ),
        ]

    def save(self, *args, **kwargs):
        self.bank_account_norm = normalise_bank(self.bank_account)
        self.phone_norm = normalise_phone(self.phone)
        self.national_id_norm = normalise_id(self.national_id)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff_no} {self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def snapshot(self):
        return {
            "staff_no": self.staff_no,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "department": self.department,
            "job_title": self.job_title,
            "gross_salary": str(self.gross_salary),
            "is_active": self.is_active,
            "is_draft": self.is_draft,
            "video": self.video.name if self.video else "",
            "bank_account": self.bank_account,
            "phone": self.phone,
        }


class AttendanceImport(models.Model):
    """One imported attendance file, including its SHA-256 fingerprint."""

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_imports"
    )
    filename = models.CharField(max_length=200)
    file_hash = models.CharField(max_length=64)
    row_count = models.PositiveIntegerField(default=0)
    imported_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-imported_at"]

    def __str__(self):
        return f"{self.filename} ({self.row_count} rows, {self.file_hash[:12]})"


class AttendanceRecord(models.Model):
    batch = models.ForeignKey(
        AttendanceImport, on_delete=models.CASCADE, related_name="records"
    )
    staff_no = models.CharField(max_length=20, db_index=True)
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("8.00"))

    class Meta:
        ordering = ["staff_no", "date"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff_no", "date"], name="unique_attendance_per_day"
            ),
        ]


class PayrollEntry(models.Model):
    """One employee's line in a payroll period being checked."""

    staff_no = models.CharField(max_length=20, db_index=True)
    period = models.CharField(max_length=7)
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["period", "staff_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff_no", "period"], name="unique_payroll_line"
            ),
        ]

    def __str__(self):
        return f"{self.period} {self.staff_no}"
