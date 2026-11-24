import csv
import hashlib
import io
import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.contrib.auth import get_user_model

from auditlog.services import record
from core.emailing import is_configured
from employees.models import (
    AttendanceImport,
    AttendanceRecord,
    Employee,
    PayrollEntry,
)
from expenses.models import Alert

logger = logging.getLogger(__name__)

EDITABLE = {
    "first_name",
    "last_name",
    "national_id",
    "department",
    "job_title",
    "gross_salary",
    "bank_account",
    "phone",
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
    run_detections(actor, employee)
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

    run_detections(actor, employee)
    return employee


def _raise_employee_alert(actor, employee, kind, severity, note):
    open_states = (Alert.OPEN, Alert.ASSIGNED, Alert.UNDER_REVIEW, Alert.ESCALATED)
    if Alert.objects.filter(
        employee=employee, kind=kind, status__in=open_states
    ).exists():
        return None
    alert = Alert.objects.create(
        employee=employee, kind=kind, severity=severity, note=note
    )
    record(
        actor,
        "ALERT_RAISE",
        "Alert",
        str(alert.pk),
        new={
            "kind": kind,
            "severity": severity,
            "employee": employee.staff_no,
        },
    )
    return alert


def run_detections(actor, employee, period=None):
    """Apply the identity and payroll checks from Iteration 2."""
    from django.utils import timezone

    period = period or timezone.now().strftime("%Y-%m")
    checks = (
        (
            employee.bank_account_norm,
            Alert.DUPLICATE_BANK,
            Alert.HIGH,
            "Bank account matches another employee",
            "bank_account_norm",
        ),
        (
            employee.national_id_norm,
            Alert.DUPLICATE_ID,
            Alert.HIGH,
            "National ID matches another employee",
            "national_id_norm",
        ),
        (
            employee.phone_norm,
            Alert.DUPLICATE_PHONE,
            Alert.LOW,
            "Phone number matches another employee (may be a family phone)",
            "phone_norm",
        ),
    )
    for value, kind, severity, note, field in checks:
        if not value:
            continue
        if Employee.objects.filter(**{field: value}).exclude(pk=employee.pk).exists():
            _raise_employee_alert(actor, employee, kind, severity, note)

    on_payroll = PayrollEntry.objects.filter(
        staff_no=employee.staff_no, period=period
    ).exists()
    if not on_payroll:
        return

    if not employee.is_active:
        _raise_employee_alert(
            actor,
            employee,
            Alert.INACTIVE_ON_PAYROLL,
            Alert.HIGH,
            f"Inactive employee appears on payroll for {period}",
        )

    year, month = (int(part) for part in period.split("-"))
    has_attendance = AttendanceRecord.objects.filter(
        staff_no=employee.staff_no, date__year=year, date__month=month
    ).exists()
    if not has_attendance:
        _raise_employee_alert(
            actor,
            employee,
            Alert.MISSING_ATTENDANCE,
            Alert.MEDIUM,
            f"No attendance record for {period} but employee is on payroll",
        )


@transaction.atomic
def import_attendance(actor, uploaded):
    """Import a CSV of staff_no,date[,hours] and record its file hash."""
    from datetime import datetime
    from decimal import Decimal

    data = uploaded.read()
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if not reader.fieldnames or not {"staff_no", "date"}.issubset(reader.fieldnames):
        raise ValueError("CSV must contain staff_no and date columns")

    batch = AttendanceImport.objects.create(
        uploaded_by=actor,
        filename=uploaded.name,
        file_hash=hashlib.sha256(data).hexdigest(),
    )
    count = 0
    for row in reader:
        staff_no = (row.get("staff_no") or "").strip()
        date_text = (row.get("date") or "").strip()
        if not staff_no or not date_text:
            continue
        try:
            day = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue
        hours_text = (row.get("hours") or "8").strip() or "8"
        try:
            hours = Decimal(hours_text)
        except Exception:
            hours = Decimal("8.00")
        AttendanceRecord.objects.get_or_create(
            batch=batch,
            staff_no=staff_no,
            date=day,
            defaults={"hours": hours},
        )
        count += 1

    batch.row_count = count
    batch.save(update_fields=["row_count"])
    record(
        actor,
        "IMPORT_ATTENDANCE",
        "AttendanceImport",
        str(batch.pk),
        new={
            "filename": batch.filename,
            "file_hash": batch.file_hash,
            "rows": count,
        },
    )
    return batch


@transaction.atomic
def import_payroll(actor, uploaded, period):
    """Import a CSV of staff_no,gross_salary and rerun checks for that period."""
    from decimal import Decimal

    reader = csv.DictReader(io.StringIO(uploaded.read().decode("utf-8-sig")))
    if not reader.fieldnames or not {"staff_no", "gross_salary"}.issubset(reader.fieldnames):
        raise ValueError("CSV must contain staff_no and gross_salary columns")

    count = 0
    for row in reader:
        staff_no = (row.get("staff_no") or "").strip()
        if not staff_no:
            continue
        try:
            salary = Decimal((row.get("gross_salary") or "0").strip())
        except Exception:
            continue
        PayrollEntry.objects.update_or_create(
            staff_no=staff_no,
            period=period,
            defaults={"gross_salary": salary},
        )
        count += 1

    record(
        actor,
        "IMPORT_PAYROLL",
        "PayrollEntry",
        period,
        new={"period": period, "rows": count},
    )
    for entry in PayrollEntry.objects.filter(period=period):
        employee = Employee.objects.filter(staff_no=entry.staff_no).first()
        if employee:
            run_detections(actor, employee, period)
    return count
