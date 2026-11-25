"""Read and write an externally anchored, signed checkpoint of the chain head."""

import hashlib
import hmac
import json
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def checkpoint_path(path=None):
    return Path(path or settings.AUDIT_CHECKPOINT_PATH)


def _signed_payload(payload, key=None):
    key = key if key is not None else settings.CHECKPOINT_SIGNING_KEY
    if not key:
        return None
    message = json.dumps(
        {"seq": payload["seq"], "entry_hash": payload["entry_hash"]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def load_checkpoint(path=None):
    """Return (seq, entry_hash) or None when no checkpoint exists."""
    record = load_checkpoint_record(path)
    if record is None:
        return None
    return (record["seq"], record["entry_hash"])


def load_checkpoint_record(path=None):
    target = checkpoint_path(path)
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return {
            "seq": int(data["seq"]),
            "entry_hash": str(data["entry_hash"]),
            "exported_at": str(data.get("exported_at", "")),
            "signature": str(data.get("signature", "")),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None


def verify_checkpoint_signature(record, key=None):
    key = key if key is not None else settings.CHECKPOINT_SIGNING_KEY
    if not key:
        return None
    expected = _signed_payload(record, key)
    return bool(expected) and hmac.compare_digest(expected, record["signature"])


def checkpoint_status(path=None):
    record = load_checkpoint_record(path)
    if record is None:
        return "No checkpoint exported"
    valid = verify_checkpoint_signature(record)
    if valid is False:
        return "Checkpoint signature INVALID"
    if valid is None:
        return f"Checkpoint seq {record['seq']} (unsigned)"
    return f"Signed checkpoint seq {record['seq']} — valid"


def save_checkpoint(seq, entry_hash, path=None):
    """Write the current chain head to a file outside the database."""
    target = checkpoint_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seq": int(seq),
        "entry_hash": str(entry_hash),
        "exported_at": timezone.now().isoformat(),
    }
    payload["signature"] = _signed_payload(payload) or ""
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
