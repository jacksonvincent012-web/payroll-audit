from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import ValidationError

from accounts.models import Role, User, UserRole


class UserRoleForm(forms.ModelForm):
    class Meta:
        model = UserRole
        fields = ("user", "role")

    def clean(self):
        cleaned = super().clean()
        user = cleaned.get("user")
        role = cleaned.get("role")
        if user and role:
            blocked = UserRole.CONFLICTS.get(role.code, set())
            taken = set(user.roles.values_list("code", flat=True)) - {role.code}
            clash = blocked & taken
            if clash:
                raise ValidationError(
                    f"{role.code} cannot be combined with {', '.join(sorted(clash))}"
                )
        return cleaned


class UserRoleInline(admin.TabularInline):
    model = UserRole
    form = UserRoleForm
    extra = 1


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (("Payroll", {"fields": ("staff_no",)}),)
    inlines = [UserRoleInline]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    form = UserRoleForm
    list_display = ("user", "role", "assigned_at")
