"""Tests for single-use recovery codes."""

from __future__ import annotations

import pytest

from redscribe.v3.vault_security.recovery import (
    MAX_CODES_PER_BATCH,
    RecoveryCodeError,
    RecoveryCodeStore,
    is_well_formed,
    normalize_code,
)


def issue(store: RecoveryCodeStore, count: int = 3, **kwargs: float) -> tuple[str, ...]:
    defaults: dict[str, float] = {"created_at": 100.0}
    defaults.update(kwargs)
    return store.issue(count, **defaults)  # type: ignore[arg-type]


def test_issue_format_and_normalization() -> None:
    store = RecoveryCodeStore()
    codes = issue(store)
    assert len(codes) == 3
    assert len(set(codes)) == 3
    assert all(is_well_formed(code) for code in codes)
    assert is_well_formed(codes[0].lower().replace("-", " ")) is True
    assert normalize_code(codes[0].lower()) == normalize_code(codes[0])
    assert is_well_formed("short") is False
    assert is_well_formed("") is False
    assert store.issued_count == 3
    assert store.active_count(100.0) == 3


def test_single_use_redemption() -> None:
    store = RecoveryCodeStore()
    code = issue(store, 1)[0]
    result = store.redeem(code, now=110.0)
    assert result.consumed is True
    assert result.code_id == "rc_0001"
    assert result.redeemed_at == 110.0
    assert result.remaining_active == 0
    assert store.active_count(110.0) == 0
    assert store.used_count() == 1
    with pytest.raises(RecoveryCodeError, match="already been used"):
        store.redeem(code, now=120.0)


def test_wrong_and_malformed_codes() -> None:
    store = RecoveryCodeStore()
    code = issue(store, 1)[0]
    with pytest.raises(RecoveryCodeError, match="invalid format"):
        store.redeem("nope", now=110.0)
    alternate = code[:-1] + ("A" if code[-1] != "A" else "B")
    with pytest.raises(RecoveryCodeError, match="not recognized"):
        store.redeem(alternate, now=110.0)
    assert store.active_count(110.0) == 1


def test_expiry_and_revocation() -> None:
    store = RecoveryCodeStore()
    codes = issue(store, 2, valid_for_seconds=50.0)
    assert store.redeem(codes[0], now=120.0).redeemed_at == 120.0
    with pytest.raises(RecoveryCodeError, match="expired"):
        store.redeem(codes[1], now=151.0)
    fresh = RecoveryCodeStore()
    fresh_codes = issue(fresh, 1)
    record = fresh.lookup(fresh_codes[0])
    assert record is not None
    assert fresh.revoke(record.code_id) is True
    assert fresh.revoke(record.code_id) is False
    with pytest.raises(RecoveryCodeError, match="revoked"):
        fresh.redeem(fresh_codes[0], now=101.0)


def test_lookup_does_not_consume() -> None:
    store = RecoveryCodeStore()
    code = issue(store, 1)[0]
    assert store.lookup(code) is not None
    assert store.lookup("bad") is None
    assert store.active_count(100.0) == 1


def test_snapshot_never_contains_codes_or_digests() -> None:
    store = RecoveryCodeStore()
    codes = issue(store, 2, label="recovery batch")
    snapshot = store.snapshot(now=100.0)
    rendered = str(snapshot)
    for code in codes:
        assert code not in rendered
        assert normalize_code(code) not in rendered
    assert "digest" not in rendered
    assert snapshot["active"] == 2
    assert snapshot["issued"] == 2
    assert snapshot["codes"][0]["state"] == "active"
    assert snapshot["codes"][0]["label"] == "recovery batch"


def test_record_state_labels() -> None:
    store = RecoveryCodeStore()
    codes = issue(store, 2, valid_for_seconds=10.0)
    first = store.lookup(codes[0])
    assert first is not None
    assert first.state(105.0) == "active"
    store.redeem(codes[0], now=106.0)
    assert first.state(106.0) == "used"
    second = store.lookup(codes[1])
    assert second is not None
    assert second.state(111.0) == "expired"
    assert first.as_dict(106.0)["state"] == "used"


def test_batch_limits_and_clear() -> None:
    store = RecoveryCodeStore()
    with pytest.raises(ValueError, match="count"):
        issue(store, 0)
    with pytest.raises(ValueError, match="count"):
        issue(store, MAX_CODES_PER_BATCH + 1)
    with pytest.raises(ValueError, match="valid_for_seconds"):
        issue(store, 1, valid_for_seconds=-1)
    with pytest.raises(TypeError, match="count"):
        store.issue(True, created_at=1.0)  # type: ignore[arg-type]
    issue(store, 2)
    store.clear()
    assert store.issued_count == 0
    assert store.records() == ()


def test_normalize_requires_string() -> None:
    with pytest.raises(TypeError, match="string"):
        normalize_code(123)  # type: ignore[arg-type]
