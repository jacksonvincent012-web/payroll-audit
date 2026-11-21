from django.contrib import admin

from employees.models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("staff_no", "full_name", "department", "gross_salary", "is_active")
    list_filter = ("department", "is_active")
    search_fields = ("staff_no", "first_name", "last_name", "national_id")
