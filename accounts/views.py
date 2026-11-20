from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

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
def dashboard(request):
    entries = list(AuditEntry.objects.all())
    ok, reason = verify(
        [_serialise(e) for e in entries],
        settings.AUDIT_HMAC_KEY.encode(),
    )

    context = {
        "audit_count": len(entries),
        "user_count": get_user_model().objects.count(),
        "chain_ok": ok,
        "chain_reason": reason,
        "recent": entries[-5:][::-1],
    }
    return render(request, "accounts/dashboard.html", context)