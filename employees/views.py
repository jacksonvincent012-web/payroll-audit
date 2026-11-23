from django.core.exceptions import PermissionDenied
import json

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from employees.forms import EmployeeForm
from employees.models import Employee
from employees.services import create_employee, update_employee

VIEW_ROLES = ("HR_OFFICER", "ADMIN", "ACCOUNTANT", "AUDITOR")
EDIT_ROLES = ("HR_OFFICER",)


@login_required
@role_required(*VIEW_ROLES)
def employee_list(request):
    user = request.user
    can_edit = user.has_role("HR_OFFICER")
    return render(
        request,
        "employees/employee_list.html",
        {"employees": Employee.objects.all(), "can_edit": can_edit},
    )


@login_required
def employee_create(request):
    if not request.user.has_role("HR_OFFICER"):
        raise PermissionDenied
    form = EmployeeForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        create_employee(request.user, **form.cleaned_data)
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
        or request.user.has_role("HR_OFFICER")
        or request.user.has_role("APPROVER")
    ):
        raise PermissionDenied
    return FileResponse(employee.video, as_attachment=True, filename=employee.video.name)