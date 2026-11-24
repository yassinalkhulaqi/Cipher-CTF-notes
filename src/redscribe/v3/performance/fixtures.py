"""Deterministic, in-memory fixture generation for large-vault benchmarks.

Fixtures are never written to disk. A given :class:`FixtureSpec` always yields
the same records, links, events, and fingerprint, which makes benchmark runs
comparable across machines and across branches.
"""

from __future__ import annotations

import hashlib
import random
from typing import Final

from redscribe.v3.clock import FixedClock, epoch_start
from redscribe.v3.entities.types import EntityId, EntityKind, EntityRecord, EntityStatus
from redscribe.v3.events.bus import EventBus
from redscribe.v3.events.types import make_event
from redscribe.v3.performance.models import FixtureSpec, VaultFixture

_VOCABULARY_SIZE: Final[int] = 320
_TOPIC_COUNT: Final[int] = 16
_TAGS: Final[tuple[str, ...]] = ("benchmark", "generated", "research", "v3", "scale")


def _note_tokens(index: int, spec: FixtureSpec, rng: random.Random) -> tuple[str, ...]:
    """Generate a deterministic token set for one note."""
    vocabulary = [f"term{value:03d}" for value in range(_VOCABULARY_SIZE)]
    tokens = [rng.choice(vocabulary) for _ in range(max(0, spec.tokens_per_note - 1))]
    tokens.append(f"topic{index % _TOPIC_COUNT:02d}")
    if index % 10 == 0:
        tokens.append("common")
    return tuple(dict.fromkeys(tokens))


def _record(
    kind: EntityKind,
    key: str,
    title: str,
    summary: str,
    index: int,
    tags: tuple[str, ...],
) -> EntityRecord:
    """Build one benchmark entity record."""
    timestamp = epoch_start() + float(index)
    return EntityRecord(
        entity_id=EntityId(kind, key),
        title=title,
        summary=summary,
        status=EntityStatus.ACTIVE,
        tags=tags,
        owner="benchmark",
        created_at=timestamp,
        updated_at=timestamp + 1.0,
        metadata={"source": "generated", "ordinal": index},
    )


def generate_fixture(spec: FixtureSpec | None = None) -> VaultFixture:
    """Generate a reproducible vault fixture entirely in memory."""
    settings = spec or FixtureSpec()
    rng = random.Random(settings.seed)
    notes: list[EntityRecord] = []
    for index in range(settings.notes):
        tokens = _note_tokens(index, settings, rng)
        notes.append(
            _record(
                EntityKind.NOTE,
                f"note-{index:05d}",
                f"Note {index:05d} {tokens[0]}",
                f"Generated note {index:05d} about {tokens[0]} and {tokens[-1]}",
                index,
                (_TAGS[index % len(_TAGS)], f"topic{index % _TOPIC_COUNT:02d}"),
            )
        )

    findings: list[EntityRecord] = []
    linked: list[tuple[EntityId, EntityId]] = []
    for index in range(settings.findings):
        source = notes[(index * 7) % settings.notes] if settings.notes else None
        finding_id = EntityId(EntityKind.FINDING, f"finding-{index:05d}")
        findings.append(
            _record(
                EntityKind.FINDING,
                f"finding-{index:05d}",
                f"Finding {index:05d} on term{index % _VOCABULARY_SIZE:03d}",
                f"Generated finding {index:05d} derived from indexed research",
                settings.notes + index,
                (_TAGS[index % len(_TAGS)], "finding"),
            )
        )
        if source is not None:
            linked.append((finding_id, source.entity_id))

    evidence: list[EntityRecord] = []
    for index in range(settings.evidence):
        source = findings[(index * 3) % settings.findings] if settings.findings else None
        evidence_id = EntityId(EntityKind.EVIDENCE, f"evidence-{index:05d}")
        evidence.append(
            _record(
                EntityKind.EVIDENCE,
                f"evidence-{index:05d}",
                f"Evidence {index:05d} attachment",
                f"Generated evidence {index:05d} for large-vault benchmarks",
                settings.notes + settings.findings + index,
                (_TAGS[index % len(_TAGS)], "evidence"),
            )
        )
        if source is not None:
            linked.append((evidence_id, source.entity_id))

    bus = EventBus(clock=FixedClock(start=epoch_start(), step=0.01))
    samples = settings.notes // settings.event_sample_every
    for index in range(samples):
        source = notes[index * settings.event_sample_every]
        bus.publish(
            make_event(
                "note.indexed",
                source.entity_id,
                ordinal=index,
                topic=f"topic{index % _TOPIC_COUNT:02d}",
            )
        )

    fingerprint_input = "|".join(
        (
            str(settings.notes),
            str(settings.findings),
            str(settings.evidence),
            str(settings.seed),
            str(settings.tokens_per_note),
            str(settings.event_sample_every),
            notes[0].title if notes else "-",
            notes[-1].title if notes else "-",
        )
    ).encode("utf-8")
    return VaultFixture(
        spec=settings,
        notes=tuple(notes),
        findings=tuple(findings),
        evidence=tuple(evidence),
        linked=tuple(linked),
        events=bus.records(),
        fingerprint=hashlib.blake2b(fingerprint_input, digest_size=12).hexdigest(),
    )


def fixture_documents(fixture: VaultFixture) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return index-ready ``(key, tokens)`` pairs for a fixture."""
    rng = random.Random(fixture.spec.seed)
    result: list[tuple[str, tuple[str, ...]]] = []
    for index, record in enumerate(fixture.notes):
        result.append((str(record.entity_id), _note_tokens(index, fixture.spec, rng)))
    return tuple(result)
