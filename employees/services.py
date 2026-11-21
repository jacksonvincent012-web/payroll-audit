from django.db import transaction

from auditlog.services import record
from employees.models import Employee

EDITABLE = {
    "first_name",
    "last_name",
    "national_id",
    "department",
    "job_title",
    "gross_salary",
    "is_active",
}


@transaction.atomic
def create_employee(actor, **fields):
    employee = Employee(**fields)
    employee.full_clean()
    employee.save()

    record(actor, "CREATE", "Employee", employee.staff_no, new=employee.snapshot())
    return employee


@transaction.atomic
def update_employee(actor, employee, **fields):
    if "staff_no" in fields and fields["staff_no"] != employee.staff_no:
        raise ValueError("staff_no is the audit identity and cannot be changed")

    unknown = set(fields) - EDITABLE
    if unknown:
        raise ValueError(f"not editable: {sorted(unknown)}")

    before = employee.snapshot()

    for name, value in fields.items():
        setattr(employee, name, value)
    employee.full_clean()
    employee.save()

    after = employee.snapshot()

    if before != after:
        record(
            actor,
            "UPDATE",
            "Employee",
            employee.staff_no,
            old=before,
            new=after,
        )
    return employee
