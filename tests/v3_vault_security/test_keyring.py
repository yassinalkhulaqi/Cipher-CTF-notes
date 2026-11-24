"""Tests for key derivation state and rotation."""

from __future__ import annotations

import pytest

from redscribe.v3.vault_security.crypto import MIN_ITERATIONS, VaultKdfParams
from redscribe.v3.vault_security.keyring import (
    KeyRing,
    KeyRingError,
    KeyStatus,
    RotationPlan,
    descriptor_from_dict,
    fresh_iterations,
)

FAST = VaultKdfParams(iterations=MIN_ITERATIONS)
PASSPHRASE = "long enough passphrase for tests"
NEXT = "a different long enough passphrase"


def make_ring() -> KeyRing:
    ring = KeyRing("case-1")
    ring.install(PASSPHRASE, created_at=100.0, params=FAST)
    return ring


def test_install_and_repr_never_reveals_passphrase() -> None:
    ring = make_ring()
    assert ring.is_initialized
    assert ring.is_unlocked
    assert ring.current_version == 1
    assert PASSPHRASE not in repr(ring)
    assert PASSPHRASE not in str(ring.snapshot())


def test_unlock_and_verify() -> None:
    ring = make_ring()
    ring.lock()
    assert ring.is_unlocked is False
    assert ring.unlock(PASSPHRASE) is True
    assert ring.unlock("wrong passphrase") is False
    assert ring.verify(PASSPHRASE) is True
    assert ring.verify("wrong passphrase") is False
    assert ring.verify("", key_id="missing") is False


def test_wrong_verifier_does_not_unlock() -> None:
    ring = make_ring()
    ring.lock()
    descriptor = ring.active()
    assert descriptor is not None
    object.__setattr__(descriptor, "verifier", "bogus")
    assert ring.unlock(PASSPHRASE) is False
    assert ring.is_unlocked is False


def test_rotation_retires_previous_key() -> None:
    ring = make_ring()
    plan = ring.rotate(NEXT, created_at=200.0)
    assert isinstance(plan, RotationPlan)
    assert plan.from_version == 1
    assert plan.to_version == 2
    assert ring.rotation_count == 1
    assert ring.current_version == 2
    assert ring.active() is not None
    assert ring.active().version == 2
    assert [key.status for key in ring.descriptors()] == [KeyStatus.RETIRED, KeyStatus.ACTIVE]
    assert ring.verify(PASSPHRASE) is True
    assert ring.verify(NEXT) is True
    assert ring.unlock("wrong") is False
    assert ring.unlock(NEXT) is True


def test_rotation_guards() -> None:
    ring = make_ring()
    ring.lock()
    with pytest.raises(KeyRingError, match="unlocked"):
        ring.rotate(NEXT, created_at=200.0)
    ring.unlock(PASSPHRASE)
    with pytest.raises(KeyRingError, match="differ"):
        ring.rotate(PASSPHRASE, created_at=200.0)
    empty = KeyRing()
    with pytest.raises(KeyRingError, match="not initialized"):
        empty.unlock(PASSPHRASE)
    with pytest.raises(KeyRingError, match="not initialized"):
        empty.rotate(NEXT, created_at=10.0)


def test_double_install_rejected() -> None:
    ring = make_ring()
    with pytest.raises(KeyRingError, match="already initialized"):
        ring.install(NEXT, created_at=100.0)


def test_revoke_and_reset() -> None:
    ring = make_ring()
    ring.rotate(NEXT, created_at=200.0)
    first = ring.descriptors()[0]
    assert ring.revoke(first.key_id) is True
    assert ring.revoke(first.key_id) is True
    active = ring.active()
    assert active is not None
    assert ring.revoke(active.key_id) is False
    assert ring.revoke("missing") is False
    ring.reset("brand new recovery passphrase", created_at=300.0)
    assert ring.rotation_count == 0
    assert len(ring.descriptors()) == 1
    assert ring.verify(PASSPHRASE) is False
    assert ring.verify("brand new recovery passphrase") is True


def test_descriptors_and_snapshot_are_secret_free() -> None:
    ring = make_ring()
    descriptor = ring.active()
    assert descriptor is not None
    rendered = descriptor.as_dict()
    assert "iterations" in rendered
    assert "verifier" in rendered
    assert "passphrase" not in rendered
    assert PASSPHRASE not in str(ring.snapshot())
    assert ring.snapshot()["active_key_id"] == descriptor.key_id
    assert ring.snapshot()["key_count"] == 1
    assert ring.snapshot()["keys"][0]["status"] == "active"


def test_descriptor_round_trip_and_iteration_helper() -> None:
    ring = make_ring()
    descriptor = ring.active()
    assert descriptor is not None
    payload = descriptor.as_dict()
    payload["params"] = descriptor.params.as_dict()
    payload["salt_b64"] = descriptor.salt_b64
    rebuilt = descriptor_from_dict(payload)
    assert rebuilt.key_id == descriptor.key_id
    assert rebuilt.verifier == descriptor.verifier
    assert fresh_iterations(MIN_ITERATIONS) == MIN_ITERATIONS + 20_000
    with pytest.raises(ValueError, match="base and step"):
        fresh_iterations(-1)


def test_current_passphrase_requires_unlock() -> None:
    ring = make_ring()
    assert ring.current_passphrase() == PASSPHRASE
    ring.lock()
    with pytest.raises(KeyRingError, match="locked"):
        ring.current_passphrase()
