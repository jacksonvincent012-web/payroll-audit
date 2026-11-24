from django.test import SimpleTestCase

from core.chain import canonical, entry_hash, verify

KEY = b"test-key-do-not-use-in-production"


def make_entry(seq, prev_hash, old=None, new=None, action="CREATE"):
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
    e["prev_hash"] = prev_hash
    e["entry_hash"] = entry_hash(
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
        e = make_entry(i, prev, new={"name": f"emp{i}"})
        chain.append(e)
        prev = e["entry_hash"]
    return chain


class ChainTests(SimpleTestCase):
    def test_1_intact_chain_verifies(self):
        ok, reason = verify(build_chain(3), KEY)
        self.assertTrue(ok)
        self.assertIsNone(reason)

    def test_2_tampered_value_is_detected(self):
        chain = build_chain(3)
        chain[1]["old"] = {"salary": 1}
        ok, reason = verify(chain, KEY)
        self.assertFalse(ok)
        self.assertIn("2", reason)

    def test_3_tampered_hash_is_detected(self):
        chain = build_chain(3)
        chain[1]["entry_hash"] = "0" * 64
        ok, reason = verify(chain, KEY)
        self.assertFalse(ok)
        self.assertIn("2", reason)

    def test_4_truncation_is_detected_by_checkpoint(self):
        chain = build_chain(3)
        checkpoint = (3, chain[2]["entry_hash"])
        ok, reason = verify(chain[:2], KEY, checkpoint=checkpoint)
        self.assertFalse(ok)
        self.assertIn("truncat", reason.lower())

    def test_5_wrong_key_fails(self):
        ok, reason = verify(build_chain(3), b"wrong-key")
        self.assertFalse(ok)
        self.assertIn("1", reason)

    def test_6_canonical_ignores_key_order(self):
        self.assertEqual(
            canonical({"a": 1, "b": 2}), canonical({"b": 2, "a": 1})
        )
