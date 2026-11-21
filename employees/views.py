from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from employees.forms import EmployeeForm
from employees.models import Employee
from employees.services import create_employee, update_employee

VIEW_ROLES = ("HR_OFFICER", "ADMIN", "ACCOUNTANT", "AUDITOR")
EDIT_ROLES = ("HR_OFFICER", "ADMIN")


@login_required
@role_required(*VIEW_ROLES)
def employee_list(request):
    user = request.user
    can_edit = (
        user.is_superuser or user.has_role("HR_OFFICER") or user.has_role("ADMIN")
    )
    return render(
        request,
        "employees/employee_list.html",
        {"employees": Employee.objects.all(), "can_edit": can_edit},
    )


@login_required
@role_required(*EDIT_ROLES)
def employee_create(request):
    form = EmployeeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        create_employee(request.user, **form.cleaned_data)
        return redirect("employees:employee_list")
    return render(
        request,
        "employees/employee_form.html",
        {"form": form, "title": "Add employee"},
    )


@login_required
@role_required(*EDIT_ROLES)
def employee_edit(request, pk):
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