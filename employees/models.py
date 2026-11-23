from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


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
        }
