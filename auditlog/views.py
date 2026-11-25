from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from accounts.decorators import role_required
from auditlog.models import AuditEntry
from core.chain import verify
from core.checkpoint import (
    checkpoint_status,
    load_checkpoint,
    load_checkpoint_record,
    verify_checkpoint_signature,
)


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

    checkpoint = load_checkpoint()
    record = load_checkpoint_record()
    signature_ok = None if record is None else verify_checkpoint_signature(record)
    result = None
    if "verify" in request.GET:
        ok, reason = verify(
            [_serialise(e) for e in entries],
            settings.AUDIT_HMAC_KEY.encode(),
            checkpoint=checkpoint,
        )
        if signature_ok is False:
            ok, reason = False, "checkpoint signature invalid"
        result = {"ok": ok, "reason": reason}

    return render(
        request,
        "auditlog/entry_list.html",
        {
            "entries": entries,
            "result": result,
            "checkpoint": checkpoint,
            "checkpoint_message": checkpoint_status(),
        },
    )


@login_required
@role_required("AUDITOR", "ADMIN")
def entry_detail(request, pk):
    entry = get_object_or_404(AuditEntry, pk=pk)

    qr_payload = (
        f"Payroll Audit Entry #{entry.seq}\n"
        f"When: {entry.occurred_at:%Y-%m-%d %H:%M:%S}\n"
        f"Actor: {entry.actor.username}\n"
        f"Action: {entry.action}\n"
        f"Entity: {entry.entity_type}:{entry.entity_id}\n"
        f"Hash: {entry.entry_hash}"
    )

    return render(
        request,
        "auditlog/entry_detail.html",
        {"entry": entry, "qr_payload": qr_payload},
    )
