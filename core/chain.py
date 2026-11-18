@'
import hashlib
import hmac
import json

GENESIS = "0" * 64


def canonical(obj) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def entry_hash(key: bytes, seq: int, occurred_at: str, actor_id: int,
               action: str, entity_type: str, entity_id: str,
               old, new, prev_hash: str) -> str:
    payload = canonical({
        "seq": seq, "occurred_at": occurred_at, "actor_id": actor_id,
        "action": action, "entity_type": entity_type, "entity_id": entity_id,
        "old": old, "new": new, "prev_hash": prev_hash,
    })
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify(entries, key: bytes, checkpoint=None):
    prev = GENESIS
    expected_seq = 1
    for e in entries:
        if e["seq"] != expected_seq:
            return (False, f"missing entry at seq {expected_seq}")
        recomputed = entry_hash(
            key, e["seq"], e["occurred_at"], e["actor_id"], e["action"],
            e["entity_type"], e["entity_id"], e["old"], e["new"], e["prev_hash"],
        )
        if not hmac.compare_digest(recomputed, e["entry_hash"]):
            return (False, f"hash mismatch at seq {e['seq']}")
        if e["prev_hash"] != prev:
            return (False, f"broken link at seq {e['seq']}")
        prev = e["entry_hash"]
        expected_seq += 1

    if checkpoint is not None:
        cp_seq, cp_hash = checkpoint
        if not entries:
            return (False, "truncated: chain is empty but a checkpoint exists")
        last = entries[-1]
        if last["seq"] < cp_seq:
            return (False, f"truncated: checkpoint expects seq {cp_seq}, "
                           f"chain ends at seq {last['seq']}")
        if last["seq"] == cp_seq and last["entry_hash"] != cp_hash:
            return (False, f"checkpoint mismatch at seq {cp_seq}")
    return (True, None)
'@ | Set-Content core\chain.py -Encoding UTF8