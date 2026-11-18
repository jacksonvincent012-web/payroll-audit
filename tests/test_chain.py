import hashlib
import hmac
import json

KEY = b"test-key-do-not-use-in-production"


def entry_hash(
    key, seq, occurred_at, actor_id, action, entity_type, entity_id, old, new, prev_hash
):
    payload = {
        "seq": seq,
        "occurred_at": occurred_at,
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "old": old,
        "new": new,
        "prev_hash": prev_hash,
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hmac.new(key, encoded, hashlib.sha256).hexdigest()


def verify(chain, key, checkpoint=None):
    if checkpoint is not None:
        checkpoint_seq, _ = checkpoint
        if len(chain) < checkpoint_seq:
            return (
                False,
                f"Chain truncation detected: expected {checkpoint_seq} entries, got {len(chain)}",
            )

    prev_hash = "0" * 64
    for expected_seq, entry in enumerate(chain, start=1):
        if entry.get("seq") != expected_seq:
            return (
                False,
                f"Invalid seq at position {expected_seq}: entry {entry.get('seq')}",
            )

        actual_hash = entry.get("prev_hash")
        try:
            expected_hash = entry_hash(
                key,
                entry["seq"],
                entry["occurred_at"],
                entry["actor_id"],
                entry["action"],
                entry["entity_type"],
                entry["entity_id"],
                entry["old"],
                entry["new"],
                prev_hash,
            )
        except KeyError as exc:
            return False, f"Missing field {exc.args[0]} in entry {expected_seq}"

        if not hmac.compare_digest(actual_hash or "", expected_hash):
            return False, f"Hash mismatch at entry {expected_seq}"
        prev_hash = actual_hash

    return True, None


def make_entry(seq, prev_hash, old=None, new=None, action="CREATED"):
    e = {
        "seq": seq,
        "occurred_at": f"2026-11-17T09:00:0{seq}+00:00",
        "actor_id": 1,
        "action": action,
        "entity_type": "Employee",
        "entity_id": "E001",
        "old": old,
        "new": new,
    }
    e["prev_hash"] = entry_hash(
        KEY,
        e["seq"],
        e["occurred_at"],
        e["actor_id"],
        e["action"],
        e["entity_type"],
        e["entity_id"],
        e["old"],
        e["new"],
        prev_hash,
    )
    return e


def build_chain(n=3):
    chain, prev = [], "0" * 64
    for i in range(1, n + 1):
        e = make_entry(i, prev)
        chain.append(e)
        prev = e["prev_hash"]
    return chain


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_1_intact_chain_verifies():
    ok, reason = verify(build_chain(3), KEY)
    assert ok is True
    assert reason is None


def test_2_tampered_value_is_detected():
    chain = build_chain(3)
    chain[1]["old"] = {"salary": 1}
    ok, reason = verify(chain, KEY)
    assert ok is False
    assert "2" in reason


def test_3_tampered_hash_is_detected():
    chain = build_chain(3)
    chain[1]["prev_hash"] = "0" * 64
    ok, reason = verify(chain, KEY)
    assert ok is False
    assert "2" in reason


def test_4_truncation_is_detected_by_checkpoint():
    chain = build_chain(3)
    checkpoint = (3, chain[2]["prev_hash"])
    ok, reason = verify(chain[:2], KEY, checkpoint=checkpoint)
    assert ok is False
    assert "truncation" in reason.lower()


def test_5_wrong_key_fails():
    ok, reason = verify(build_chain(3), b"wrong-key")
    assert ok is False
    assert "1" in reason


def test_6_canonical_ignores_key_order():
    assert canonical({"a": 1, "b": 2}) == canonical({"b": 2, "a": 1})
