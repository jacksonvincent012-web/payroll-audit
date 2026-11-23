from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.contrib.auth import get_user_model

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
    "is_draft",
    "video",
}


def _notify_verification(actor, employee, action):
    User = get_user_model()
    approvers = [u for u in User.objects.all() if u.has_role("APPROVER")]
    if not approvers:
        return
    video_name = employee.video.name if employee.video else ""
    details = (
        "Payroll Audit - Employee verification video " + action + "\n"
        + "Staff No: " + str(employee.staff_no) + "\n"
        + "Name: " + employee.full_name + "\n"
        + "National ID: " + str(employee.national_id) + "\n"
        + "Department: " + str(employee.department) + "\n"
        + "Job Title: " + str(employee.job_title) + "\n"
        + "Gross Salary: " + str(employee.gross_salary) + "\n"
        + "Video: " + str(video_name) + "\n"
        + "Action: " + action + "\n"
        + "Recorded by: " + str(actor.username) + "\n"
        + "Recorded at: " + str(employee.updated_at) + "\n"
    )
    for u in approvers:
        if not u.email:
            continue
        send_mail(
            subject="Payroll Audit - Verification video " + action + ": " + str(employee.staff_no),
            message=details,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[u.email],
            fail_silently=True,
        )


@transaction.atomic
def create_employee(actor, **fields):
    employee = Employee(**fields)
    employee.full_clean()
    employee.save()

    record(actor, "CREATE", "Employee", employee.staff_no, new=employee.snapshot())
    if employee.video:
        _notify_verification(actor, employee, "CREATE")
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

    if employee.video:
        _notify_verification(actor, employee, "UPDATE")

    return employee
