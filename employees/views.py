from django.core.exceptions import PermissionDenied
import json
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from datetime import timedelta

from accounts.decorators import role_required
from auditlog.models import AuditEntry
from employees.forms import AttendanceUploadForm, EmployeeForm, PayrollUploadForm
from employees.models import (
    AttendanceImport,
    AttendanceRecord,
    Employee,
    PayrollEntry,
)
from employees.services import (
    create_employee,
    import_attendance,
    import_payroll,
    update_employee,
)
from expenses.models import Alert
from expenses.services import ClaimError, clear_alert

VIEW_ROLES = ("HR_OFFICER", "ADMIN", "ACCOUNTANT", "AUDITOR", "APPROVER")
EDIT_ROLES = ("HR_OFFICER",)
VIDEO_ROLES = ("HR_OFFICER", "APPROVER", "AUDITOR", "ADMIN")
AUDIT_ROLES = ("AUDITOR", "ADMIN")


@login_required
@role_required(*VIEW_ROLES)
def employee_list(request):
    user = request.user
    can_edit = user.has_role("HR_OFFICER")
    query = (request.GET.get("q") or "").strip()
    employees = Employee.objects.all()
    if query:
        employees = employees.filter(
            Q(staff_no__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(department__icontains=query)
            | Q(job_title__icontains=query)
        )
    return render(
        request,
        "employees/employee_list.html",
        {
            "employees": employees,
            "can_edit": can_edit,
            "query": query,
            "new_only": False,
        },
    )


@login_required
@role_required(*VIEW_ROLES)
def employee_detail(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    history = (
        AuditEntry.objects.filter(
            entity_type="Employee", entity_id=employee.staff_no
        )
        .select_related("actor")
        .order_by("-seq")[:25]
    )
    can_audit = request.user.is_superuser or any(
        request.user.has_role(code) for code in AUDIT_ROLES
    )
    can_watch = request.user.is_superuser or any(
        request.user.has_role(code) for code in VIDEO_ROLES
    )
    return render(
        request,
        "employees/employee_detail.html",
        {
            "employee": employee,
            "history": history,
            "can_edit": request.user.has_role("HR_OFFICER"),
            "can_watch": can_watch,
            "can_audit": can_audit,
        },
    )


@login_required
@role_required(*VIEW_ROLES)
def employee_new_list(request):
    since = timezone.now() - timedelta(days=30)
    employees = Employee.objects.filter(created_at__gte=since).order_by("-created_at")
    return render(
        request,
        "employees/employee_list.html",
        {"employees": employees, "can_edit": False, "new_only": True},
    )


@login_required
def employee_create(request):
    if not request.user.has_role("HR_OFFICER"):
        raise PermissionDenied
    form = EmployeeForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        employee = create_employee(request.user, **form.cleaned_data)
        messages.success(request, f"Employee {employee.staff_no} created")
        return redirect("employees:employee_list")
    return render(
        request,
        "employees/employee_form.html",
        {"form": form, "title": "Add employee"},
    )


@login_required
def employee_edit(request, pk):
    if not request.user.has_role("HR_OFFICER"):
        raise PermissionDenied
    employee = get_object_or_404(Employee, pk=pk)
    form = EmployeeForm(request.POST or None, instance=employee)
    if request.method == "POST" and form.is_valid():
        update_employee(request.user, employee, **form.cleaned_data)
        messages.success(request, f"Employee {employee.staff_no} updated")
        return redirect("employees:employee_list")
    return render(
        request,
        "employees/employee_form.html",
        {"form": form, "title": f"Edit {employee.staff_no}"},
    )


@login_required
@require_POST
def employee_autosave(request):
    if not request.user.has_role("HR_OFFICER"):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    # Collect whatever fields were sent
    data = {}
    for key in ("staff_no", "first_name", "last_name", "national_id",
                "department", "job_title", "gross_salary", "is_active"):
        if key in request.POST:
            data[key] = request.POST.get(key)

    # Write an audit entry capturing the in-progress draft
    from auditlog.services import record
    record(
        request.user,
        "DRAFT_SAVE",
        "EmployeeDraft",
        data.get("staff_no", "draft"),
        new=data,
    )

    return JsonResponse({"ok": True, "status": "saved"})


@login_required
def employee_video(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if not employee.video:
        raise Http404("no verification video")
    if not (
        request.user.is_superuser
        or any(request.user.has_role(code) for code in VIDEO_ROLES)
    ):
        raise PermissionDenied
    filename = employee.video.name.rsplit("/", 1)[-1]
    content_type = mimetypes.guess_type(filename)[0] or "video/mp4"
    return FileResponse(
        employee.video,
        as_attachment=False,
        filename=filename,
        content_type=content_type,
    )


@login_required
@role_required("HR_OFFICER", "ACCOUNTANT", "ADMIN")
def attendance_import(request):
    if request.method == "POST":
        form = AttendanceUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                batch = import_attendance(request.user, form.cleaned_data["csv_file"])
                messages.success(request, f"Imported {batch.row_count} attendance rows")
            except (ValueError, UnicodeDecodeError) as exc:
                form.add_error(None, str(exc))
            else:
                return redirect("employees:attendance_import")
    else:
        form = AttendanceUploadForm()
    return render(
        request,
        "employees/attendance_import.html",
        {
            "form": form,
            "batches": AttendanceImport.objects.select_related("uploaded_by")[:20],
            "records": AttendanceRecord.objects.select_related("batch")[:20],
        },
    )


@login_required
@role_required("HR_OFFICER", "ACCOUNTANT", "ADMIN")
def payroll_import(request):
    if request.method == "POST":
        form = PayrollUploadForm(request.POST, request.FILES)
        if form.is_valid():
            period = form.cleaned_data["period"]
            try:
                count = import_payroll(request.user, form.cleaned_data["csv_file"], period)
                messages.success(request, f"Imported {count} payroll lines for {period}")
            except (ValueError, UnicodeDecodeError) as exc:
                form.add_error(None, str(exc))
            else:
                return redirect("employees:payroll_import")
    else:
        form = PayrollUploadForm()
    return render(
        request,
        "employees/payroll_import.html",
        {
            "form": form,
            "entries": PayrollEntry.objects.all()[:50],
        },
    )


@login_required
@role_required("HR_OFFICER", "APPROVER", "AUDITOR", "ADMIN")
def verification_alerts(request):
    if request.method == "POST":
        alert = get_object_or_404(Alert, pk=request.POST.get("alert_id"))
        try:
            cleared = clear_alert(request.user, alert, request.POST.get("reason", ""))
            messages.success(request, f"Alert on {cleared.employee.staff_no} cleared")
        except ClaimError as exc:
            messages.error(request, str(exc))
        return redirect("employees:verification_alerts")

    alerts = (
        Alert.objects.filter(employee__isnull=False)
        .select_related("employee", "cleared_by")
        .order_by("-raised_at")
    )
    return render(
        request,
        "employees/verification_alerts.html",
        {"alerts": alerts},
    )