from django.conf import settings
from django.db import transaction
from django.utils import timezone

from auditlog.models import AuditEntry
from core.chain import GENESIS, entry_hash


def _key():
    return settings.AUDIT_HMAC_KEY.encode("utf-8")


@transaction.atomic
def record(actor, action, entity_type, entity_id, old=None, new=None):
    last = AuditEntry.objects.select_for_update().order_by("-seq").first()

    seq = 1 if last is None else last.seq + 1
    prev = GENESIS if last is None else last.entry_hash
    occurred_at = timezone.now()

    digest = entry_hash(
        _key(),
        seq,
        occurred_at.isoformat(),
        actor.pk,
        action,
        entity_type,
        entity_id,
        old,
        new,
        prev,
    )

    return AuditEntry.objects.create(
        seq=seq,
        occurred_at=occurred_at,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old,
        new_values=new,
        prev_hash=prev,
        entry_hash=digest,
        key_id="v1",
    )
