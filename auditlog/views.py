from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.decorators import role_required
from auditlog.models import AuditEntry
from core.chain import verify


def _serialise(e):
    return {
        "seq": e.seq,
        "occurred_at": e.occurred_at.isoformat(),
        "actor_id": e.actor_id,
        "action": e.action,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "old": e.old_values,
        "new": e.new_values,
        "prev_hash": e.prev_hash,
        "entry_hash": e.entry_hash,
    }


@login_required
@role_required("AUDITOR", "ADMIN")
def entry_list(request):
    entries = list(AuditEntry.objects.all())

    result = None
    if "verify" in request.GET:
        ok, reason = verify(
            [_serialise(e) for e in entries],
            settings.AUDIT_HMAC_KEY.encode(),
        )
        result = {"ok": ok, "reason": reason}

    return render(
        request, "auditlog/entry_list.html", {"entries": entries, "result": result}
    )
