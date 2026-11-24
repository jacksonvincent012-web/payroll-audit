from django.db import migrations


def seed_rules(apps, schema_editor):
    Rule = apps.get_model("expenses", "ApprovalRule")
    Rule.objects.update_or_create(
        name="Standard",
        defaults={
            "min_amount": "0.01",
            "max_amount": "100000.00",
            "required_levels": 1,
            "is_active": True,
        },
    )
    Rule.objects.update_or_create(
        name="High value",
        defaults={
            "min_amount": "100000.01",
            "max_amount": "999999999.99",
            "required_levels": 2,
            "is_active": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0004_approvalrule_alter_expenseclaim_status_alert_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_rules, migrations.RunPython.noop),
    ]
