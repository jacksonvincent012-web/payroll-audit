"""Read and write an external checkpoint of the audit chain head."""

import json
from pathlib import Path

from django.conf import settings
from django.utils import timezone


def checkpoint_path(path=None):
    return Path(path or settings.AUDIT_CHECKPOINT_PATH)


def load_checkpoint(path=None):
    """Return (seq, entry_hash) or None when no checkpoint exists."""
    target = checkpoint_path(path)
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return (int(data["seq"]), str(data["entry_hash"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_checkpoint(seq, entry_hash, path=None):
    """Write the current chain head to a file outside the database."""
    target = checkpoint_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "seq": int(seq),
        "entry_hash": str(entry_hash),
        "exported_at": timezone.now().isoformat(),
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target
