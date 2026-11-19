from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditEntry(models.Model):
    id = models.BigAutoField(primary_key=True)
    seq = models.BigIntegerField(unique=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=32)
    entity_type = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    prev_hash = models.CharField(max_length=64)
    entry_hash = models.CharField(max_length=64, unique=True)
    key_id = models.CharField(max_length=16, default="v1")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"#{self.id} {self.action} {self.entity_type}:{self.entity_id}"
