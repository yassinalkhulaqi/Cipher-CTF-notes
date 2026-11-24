"""Batched event flushing, triggers, checkpoints, and sink integration."""

from __future__ import annotations

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.events.outbox import MemoryOutbox, OutboxWriter
from redscribe.v3.events.types import DomainEvent, EventRecord
from redscribe.v3.performance.batching import EventBatcher, FlushPolicy


def record(sequence: int, topic: str = "alpha") -> EventRecord:
    return EventRecord(
        sequence=sequence,
        event=DomainEvent(kind="note.indexed", payload={"topic": topic}),
        timestamp=float(sequence),
    )


def make_batcher(**options: object) -> EventBatcher:
    sink = OutboxWriter(MemoryOutbox())
    policy = FlushPolicy(**options)  # type: ignore[arg-type]
    return EventBatcher(sink=sink, policy=policy, clock=FixedClock(start=0.0, step=0.0))


def test_flush_policy_validation() -> None:
    with pytest.raises(ValueError, match="max_size"):
        FlushPolicy(max_size=0)
    with pytest.raises(ValueError, match="max_bytes"):
        FlushPolicy(max_bytes=0)
    with pytest.raises(ValueError, match="max_lag"):
        FlushPolicy(max_lag=0)
    assert FlushPolicy().as_dict()["max_size"] == 128


def test_batcher_buffers_before_threshold() -> None:
    batcher = make_batcher(max_size=5)
    assert batcher.append(record(1), now=0.0) is False
    assert batcher.append(record(2), now=0.0) is False
    assert len(batcher.pending) == 2
    assert batcher.report().batches == 0
    assert batcher.checkpoint == 0


def test_size_trigger_flushes_earlier_records() -> None:
    batcher = make_batcher(max_size=3)
    triggers = [batcher.append(record(sequence), now=0.0) for sequence in range(1, 5)]
    assert triggers == [False, False, False, True]
    assert batcher.report().batches == 1
    assert batcher.report().flushed == 3
    assert len(batcher.pending) == 1
    report = batcher.drain()
    assert report.flushed == 4
    assert report.checkpoint == 4


def test_time_trigger_uses_supplied_timestamp() -> None:
    batcher = make_batcher(max_size=100, max_lag=1.0)
    assert batcher.append(record(1), now=0.0) is False
    assert batcher.append(record(2), now=0.5) is False
    assert batcher.append(record(3), now=2.0) is True
    assert batcher.report().flushed == 2


def test_byte_trigger_uses_payload_size() -> None:
    batcher = make_batcher(max_size=100, max_bytes=120)
    assert batcher.append(record(1, "x" * 80), now=0.0) is False
    assert batcher.append(record(2, "y" * 80), now=0.0) is True
    assert batcher.report().flushed == 1


def test_duplicate_sequences_are_dropped() -> None:
    batcher = make_batcher()
    assert batcher.append(record(1), now=0.0) is False
    assert batcher.append(record(1), now=0.0) is False
    assert batcher.append(record(2), now=0.0) is False
    report = batcher.drain()
    assert report.received == 2
    assert report.dropped == 1
    assert report.flushed == 2


def test_flush_is_idempotent_when_empty() -> None:
    batcher = make_batcher()
    assert batcher.flush() == 0
    batcher.append(record(1), now=0.0)
    assert batcher.flush() == 1
    assert batcher.flush() == 0
    assert batcher.report().batches == 1


def test_report_and_meter_reflect_written_events() -> None:
    batcher = make_batcher(max_size=2)
    for sequence in range(1, 6):
        batcher.append(record(sequence), now=0.0)
    report = batcher.drain()
    rendered = report.as_dict()
    assert rendered["batches"] == 3
    assert rendered["flushed"] == 5
    assert rendered["checkpoint"] == 5
    assert batcher.meter.count("event_append") == 5
    assert batcher.meter.count("event_flush") == 5
    assert batcher.meter.modeled_ms > 0


def test_reset_clears_pending_and_seen() -> None:
    batcher = make_batcher()
    batcher.append(record(1), now=0.0)
    batcher.reset()
    assert batcher.pending == ()
    assert batcher.report().received == 0
    assert batcher.append(record(1), now=0.0) is False
    assert batcher.report().dropped == 0


def test_batcher_accepts_default_construction() -> None:
    batcher = EventBatcher(OutboxWriter(MemoryOutbox()))
    assert batcher.policy.max_size == 128
    assert batcher.flush() == 0
