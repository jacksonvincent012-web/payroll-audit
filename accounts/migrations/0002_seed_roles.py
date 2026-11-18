from django.db import migrations

ROLES = [
    ("CLAIMANT", "Claimant"),
    ("HR_OFFICER", "HR Officer"),
    ("ACCOUNTANT", "Accountant"),
    ("APPROVER", "Approver"),
    ("AUDITOR", "Auditor"),
    ("ADMIN", "Administrator"),
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    for code, name in ROLES:
        Role.objects.get_or_create(code=code, defaults={"name": name})


def reverse_seed_roles(apps, _schema_editor):
    Role = apps.get_model("accounts", "Role")
    Role.objects.filter(code__in=[code for code, _ in ROLES]).delete()


class Migration(migrations.Migration):
    dependencies = (("accounts", "0001_initial"),)

    operations = (migrations.RunPython(seed_roles, reverse_seed_roles),)
