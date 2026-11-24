"""Tests for auditable conflict resolution and redacted event emission."""

from __future__ import annotations

import pytest

from redscribe.v3.events.bus import EventBus
from redscribe.v3.portability.conflicts import ConflictResolver, ResolutionLedger
from redscribe.v3.portability.errors import ResolutionError
from redscribe.v3.portability.merge import (
    MergeResult,
    ResolutionChoice,
    ResolutionStrategy,
    apply_resolution,
    merge_families,
)
from tests.v3_portability.conftest import make_entity


def conflicted_result() -> MergeResult:
    """Create a merge with one field conflict."""
    base = make_entity("note:1", title="Base")
    local = base.apply_fields({"title": "Local"}, vector=base.vector.bump("alpha"))
    remote = base.apply_fields({"title": "Remote"}, vector=base.vector.bump("beta"))
    return merge_families((base,), (local,), (remote,))


def test_ledger_records_hash_chained_entries() -> None:
    ledger = ResolutionLedger()
    result = conflicted_result()
    conflict = result.conflicts[0]
    first = ledger.record(
        conflict=conflict,
        choice=ResolutionChoice.KEEP_LOCAL,
        actor="alice",
        device="alpha",
        decided_at=100.0,
        before_digest="before",
        after_digest="after",
    )
    second = ledger.record(
        conflict=conflict,
        choice=ResolutionChoice.KEEP_REMOTE,
        actor="bob",
        device="beta",
        decided_at=101.0,
        note="second look",
        before_digest="after",
        after_digest="final",
    )
    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_hash == first.entry_hash
    assert ledger.verify_chain()
    assert ledger.for_ref("note:1") == (first, second)
    assert ledger.stats() == {"keep_local": 1, "keep_remote": 1}


def test_ledger_detects_tampering() -> None:
    ledger = ResolutionLedger()
    conflict = conflicted_result().conflicts[0]
    entry = ledger.record(
        conflict=conflict,
        choice=ResolutionChoice.KEEP_LOCAL,
        actor="alice",
        device="alpha",
        decided_at=100.0,
        before_digest="a",
        after_digest="b",
    )
    from dataclasses import replace

    ledger._entries[0] = replace(entry, note="tampered")
    assert not ledger.verify_chain()


def test_ledger_serialization() -> None:
    ledger = ResolutionLedger()
    conflict = conflicted_result().conflicts[0]
    ledger.record(
        conflict=conflict,
        choice=ResolutionChoice.SKIP,
        actor="alice",
        device="alpha",
        decided_at=1.0,
        before_digest="a",
        after_digest="b",
    )
    payload = ledger.as_dict()
    assert payload["count"] == 1
    assert payload["intact"]
    assert payload["entries"][0]["choice"] == "skip"


def test_resolver_applies_decision_and_emits_event() -> None:
    bus = EventBus()
    resolver = ConflictResolver(bus=bus)
    result = conflicted_result()
    updated, entry = resolver.resolve(
        result,
        result.conflicts[0],
        ResolutionChoice.KEEP_LOCAL,
        actor="alice",
        device="alpha",
        decided_at=100.0,
    )
    assert updated.clean
    assert updated.entities[0].title == "Local"
    assert entry.actor == "alice"
    assert len(bus.of_kind("portability.conflict.resolved")) == 1
    assert bus.last() is not None
    assert bus.last().event.payload["choice"] == "keep_local"


def test_resolver_redacts_secrets_in_event_payloads() -> None:
    bus = EventBus()
    resolver = ConflictResolver(bus=bus)
    result = conflicted_result()
    resolver.resolve(
        result,
        result.conflicts[0],
        ResolutionChoice.KEEP_LOCAL,
        note="flag{do-not-leak-this-secret}",
    )
    record = bus.last()
    assert record is not None
    assert "do-not-leak" not in str(record.event.payload)
    assert "[flag-redacted]" in record.event.payload["note"]


def test_resolver_bulk_uses_default_strategy() -> None:
    resolver = ConflictResolver()
    result = conflicted_result()
    updated, entries = resolver.resolve_bulk(result, {}, default=ResolutionStrategy.KEEP_REMOTE)
    assert updated.clean
    assert len(entries) == 1
    assert entries[0].choice == "keep_remote"


def test_resolver_bulk_honors_explicit_choices() -> None:
    resolver = ConflictResolver()
    result = conflicted_result()
    updated, entries = resolver.resolve_bulk(result, {"note:1": "keep_local"})
    assert updated.entities[0].title == "Local"
    assert entries[0].choice == "keep_local"


def test_resolver_bulk_rejects_unknown_choice() -> None:
    resolver = ConflictResolver()
    result = conflicted_result()
    with pytest.raises(ResolutionError, match="Unknown resolution choice"):
        resolver.resolve_bulk(result, {"note:1": "explode"})


def test_resolver_bulk_rejects_manual_default() -> None:
    resolver = ConflictResolver()
    result = conflicted_result()
    with pytest.raises(ResolutionError, match="requires a decision"):
        resolver.resolve_bulk(result, {})


def test_resolver_serialization_includes_ledger() -> None:
    resolver = ConflictResolver()
    result = conflicted_result()
    resolver.resolve(result, result.conflicts[0], ResolutionChoice.SKIP)
    payload = resolver.as_dict()
    assert payload["count"] == 1
    assert payload["intact"]


def test_applied_result_has_no_remaining_conflicts() -> None:
    result = conflicted_result()
    updated = apply_resolution(result, result.conflicts[0], ResolutionChoice.KEEP_LOCAL)
    assert updated.clean
    assert updated.conflicts == ()
