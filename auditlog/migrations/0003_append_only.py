from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION auditlog_deny_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only: % denied on %', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auditlog_no_row_mutation
BEFORE UPDATE OR DELETE ON auditlog_auditentry
FOR EACH ROW EXECUTE FUNCTION auditlog_deny_mutation();

CREATE TRIGGER auditlog_no_truncate
BEFORE TRUNCATE ON auditlog_auditentry
FOR EACH STATEMENT EXECUTE FUNCTION auditlog_deny_mutation();
"""

REVERSE = """
DROP TRIGGER IF EXISTS auditlog_no_truncate ON auditlog_auditentry;
DROP TRIGGER IF EXISTS auditlog_no_row_mutation ON auditlog_auditentry;
DROP FUNCTION IF EXISTS auditlog_deny_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("auditlog", "0002_auditentry_key_id_alter_auditentry_entry_hash_and_more"),
    ]

    operations = [
        migrations.RunSQL(FORWARD, REVERSE),
    ]
