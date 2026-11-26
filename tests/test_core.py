"""Tests for the core helpers: chain payload signing, checkpoint anchoring
and the identity normalisation rules used for duplicate detection."""

import json

import pytest
from django.test import override_settings

from core import checkpoint, normalise


@pytest.fixture
def checkpoint_env(tmp_path):
    return tmp_path / "chain.json", "ci-only-checkpoint-key"


def test_save_then_load_round_trip(checkpoint_env):
    path, key = checkpoint_env
    with override_settings(AUDIT_CHECKPOINT_PATH=str(path), CHECKPOINT_SIGNING_KEY=key):
        returned = checkpoint.save_checkpoint(seq=7, entry_hash="abc123", path=str(path))
        assert returned == path
        assert checkpoint.load_checkpoint(str(path)) == (7, "abc123")


def test_missing_checkpoint_returns_none(checkpoint_env):
    path, _key = checkpoint_env
    with override_settings(AUDIT_CHECKPOINT_PATH=str(path), CHECKPOINT_SIGNING_KEY="k"):
        assert checkpoint.load_checkpoint(str(path)) is None
        assert checkpoint.checkpoint_status(str(path)) == "No checkpoint exported"


def test_tampered_signature_is_detected(checkpoint_env):
    path, key = checkpoint_env
    with override_settings(AUDIT_CHECKPOINT_PATH=str(path), CHECKPOINT_SIGNING_KEY=key):
        checkpoint.save_checkpoint(seq=9, entry_hash="deadbeef", path=str(path))
        record = checkpoint.load_checkpoint_record(str(path))
        assert record is not None
        assert checkpoint.verify_checkpoint_signature(record, key=key) is True
        # Tamper: flip the stored sequence.
        data = json.loads(path.read_text(encoding="utf-8"))
        data["seq"] = 10
        path.write_text(json.dumps(data), encoding="utf-8")
        tampered = checkpoint.load_checkpoint_record(str(path))
        assert checkpoint.verify_checkpoint_signature(tampered, key=key) is False
        assert checkpoint.checkpoint_status(str(path)) == "Checkpoint signature INVALID"


def test_unsigned_when_key_missing(checkpoint_env, tmp_path):
    path, _key = checkpoint_env
    with override_settings(AUDIT_CHECKPOINT_PATH=str(path), CHECKPOINT_SIGNING_KEY=""):
        checkpoint.save_checkpoint(seq=3, entry_hash="feed", path=str(path))
        record = checkpoint.load_checkpoint_record(str(path))
        assert checkpoint.verify_checkpoint_signature(record) is None
        assert checkpoint.checkpoint_status(str(path)) == "Checkpoint seq 3 (unsigned)"


class TestNormalise:
    def test_digits_keeps_only_digits(self):
        assert normalise.digits("070012345678") == "070012345678"
        assert normalise.digits("AB12C34") == "1234"
        assert normalise.digits("") == ""

    def test_bank_is_digits_only(self):
        assert normalise.normalise_bank("+254 712 345 678") == "254712345678"
        assert normalise.normalise_bank("07-1234-5678") == "0712345678"

    def test_phone_is_kebab_normalised(self):
        assert normalise.normalise_phone("+254712345678") == "712345678"
        assert normalise.normalise_phone("254712345678") == "712345678"
        assert normalise.normalise_phone("0712345678") == "712345678"
        assert normalise.normalise_phone("712345678") == "712345678"

    def test_id_is_digits_only(self):
        assert normalise.normalise_id("98887766") == "98887766"
        assert normalise.normalise_id("(01)234567") == "01234567"
