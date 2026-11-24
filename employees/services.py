import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.contrib.auth import get_user_model

from auditlog.services import record
from core.emailing import is_configured
from employees.models import Employee

logger = logging.getLogger(__name__)

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
    if not is_configured():
        logger.warning(
            "Skipping verification email for %s: email is not configured.",
            employee.staff_no,
        )
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
        attachments = []
        if employee.video:
            try:
                video_file = employee.video.open("rb")
                attachments.append((employee.video.name, video_file.read(), "video/mp4"))
                video_file.close()
            except Exception:
                pass
        try:
            message = EmailMessage(
                subject="Payroll Audit - Verification video "
                + action
                + ": "
                + str(employee.staff_no),
                body=details,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[u.email],
            )
            for name, content, mime in attachments:
                message.attach(name, content, mime)
            message.send(fail_silently=False)
        except Exception:
            logger.exception(
                "Could not send verification email for %s to %s",
                employee.staff_no,
                u.email,
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
