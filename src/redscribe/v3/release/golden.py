"""Deterministic, in-memory golden-path vault for release validation.

The runner never touches the network, the filesystem, or an external process.
It composes the B00 universal contracts (entities, events, outbox, envelopes,
idempotency) into the capture -> finding -> evidence -> report -> export ->
import -> merge workflow so the release suite can prove the contracts work
together rather than only in isolation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.api.idempotency import IdempotencyGuard, MemoryIdempotencyStore, compute_etag
from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.links import DuplicateLinkError
from redscribe.v3.entities.service import EntityService
from redscribe.v3.entities.types import EntityId, EntityKind, EntityLink, EntityStatus, LinkKind
from redscribe.v3.events.bus import EventBus
from redscribe.v3.events.outbox import MemoryOutbox, OutboxWriter
from redscribe.v3.events.redaction import RedactionPolicy
from redscribe.v3.events.replay import EventReplay
from redscribe.v3.events.types import DomainEvent, EventRecord, EventSeverity

DEFAULT_PREFIX = "golden"
DEFAULT_CORRELATION = "golden-path-001"


class GoldenPathError(RuntimeError):
    """Raised when a golden-path invariant is violated."""


@dataclass(frozen=True, slots=True)
class GoldenBundle:
    """Portable export produced by the golden path."""

    source: str
    version: str
    records: tuple[dict[str, Any], ...]
    links: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]
    digest: str

    def payload(self) -> dict[str, Any]:
        """Return the digest-covered portion of the bundle."""
        return {
            "source": self.source,
            "version": self.version,
            "records": [dict(record) for record in self.records],
            "links": [dict(link) for link in self.links],
            "events": [dict(event) for event in self.events],
        }

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return self.payload() | {"digest": self.digest}

    def canonical(self) -> str:
        """Return the canonical JSON used for digest computation."""
        return json.dumps(self.payload(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Result of validating and restoring an exported bundle."""

    source: str
    digest: str
    restored: int
    links_restored: int
    event_count: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "source": self.source,
            "digest": self.digest,
            "restored": self.restored,
            "links_restored": self.links_restored,
            "event_count": self.event_count,
        }


@dataclass(frozen=True, slots=True)
class MergeResult:
    """Result of merging a peer bundle into a local vault."""

    source: str
    added: int
    skipped: int
    links_added: int
    links_skipped: int

    @property
    def ok(self) -> bool:
        """Whether the merge produced a consistent local state."""
        return self.added + self.skipped > 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "source": self.source,
            "added": self.added,
            "skipped": self.skipped,
            "links_added": self.links_added,
            "links_skipped": self.links_skipped,
            "ok": self.ok,
        }


@dataclass(slots=True)
class GoldenPathVault:
    """A local vault driven through the release golden path."""

    prefix: str = DEFAULT_PREFIX
    clock: FixedClock = field(default_factory=lambda: FixedClock(start=1000.0, step=1.0))
    correlation_id: str = DEFAULT_CORRELATION

    entities: EntityService = field(init=False)
    events: EventBus = field(init=False)
    outbox: MemoryOutbox = field(init=False)
    writer: OutboxWriter = field(init=False)
    guard: IdempotencyGuard = field(init=False)
    redactor: RedactionPolicy = field(init=False)
    artifacts: dict[str, dict[str, Any]] = field(init=False)
    imported: ImportResult | None = field(init=False, default=None)
    last_bundle: GoldenBundle | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if not self.prefix or any(char.isspace() for char in self.prefix):
            raise GoldenPathError("Vault prefix must be a non-empty token")
        self.entities = EntityService(clock=self.clock)
        self.events = EventBus(clock=self.clock)
        self.outbox = MemoryOutbox()
        self.writer = OutboxWriter(self.outbox)
        self.guard = IdempotencyGuard(MemoryIdempotencyStore())
        self.redactor = RedactionPolicy(extra_keys=("sessionid",))
        self.artifacts = {}
        self.events.subscribe_all(self._persist)

    def _persist(self, record: EventRecord) -> None:
        """Write a published event to the durable outbox."""
        self.writer.write(record)

    def _emit(
        self,
        kind: str,
        subject: EntityId | None,
        payload: dict[str, Any],
        *,
        severity: EventSeverity = EventSeverity.INFO,
    ) -> EventRecord:
        """Publish one correlated domain event."""
        event = DomainEvent(
            kind=kind,
            subject=subject,
            actor="golden-runner",
            severity=severity,
            payload=dict(payload),
            correlation_id=self.correlation_id,
        )
        return self.events.publish(event)

    def _ref(self, kind: str) -> str:
        """Build a deterministic entity value for this vault."""
        return f"{self.prefix}-{kind}"

    def ref_for(self, kind: EntityKind | str, role: str) -> EntityId:
        """Build an entity id for a known role."""
        token = kind.value if isinstance(kind, EntityKind) else kind
        return EntityId.parse(f"{token}:{self._ref(role)}")

    def capture_note(
        self,
        title: str = "Initial capture note",
        body: str = "Observed behaviour recorded during the engagement.",
        tags: tuple[str, ...] = ("capture", "golden"),
        *,
        idempotency_key: str = "",
        value: str = "",
    ) -> dict[str, Any]:
        """Record the first note; repeated writes are idempotent."""
        key = idempotency_key or f"{self.prefix}:capture"
        request = {"title": title, "body": body, "tags": list(tags)}

        def operation() -> dict[str, Any]:
            record = self.entities.create(
                EntityKind.NOTE,
                title=title,
                summary=body[:120],
                tags=tags,
                value=value or self._ref("note-capture"),
                owner="local",
                metadata={"phase": "capture", "role": "source-note"},
            )
            self.artifacts["capture"] = {"body": body, "title": title}
            self._emit(
                "golden.captured",
                record.entity_id,
                {"title": title, "characters": len(body), "tags": list(tags)},
            )
            return {
                "entity_id": str(record.entity_id),
                "title": record.title,
                "characters": len(body),
                "version": record.version,
                "cached": False,
            }

        result, cached = self.guard.execute(key, request, operation)
        result["cached"] = cached
        return result

    def create_finding(
        self,
        title: str = "Finding: default credentials accepted",
        severity: str = "high",
        score: float = 7.5,
    ) -> dict[str, Any]:
        """Create a finding derived from the captured note."""
        source = self.ref_for(EntityKind.NOTE, "note-capture")
        record = self.entities.create(
            EntityKind.FINDING,
            title=title,
            summary=f"{severity} severity finding derived from the capture note.",
            tags=("finding", severity),
            value=self._ref("finding"),
            owner="analyst",
            metadata={"severity": severity, "cvss_score": score},
        )
        self.entities.link(source, record.entity_id, kind=LinkKind.DERIVES, label="derived from")
        self.artifacts["finding"] = {"severity": severity, "score": score}
        self._emit(
            "golden.finding_created",
            record.entity_id,
            {"severity": severity, "cvss": score, "source": str(source)},
            severity=EventSeverity.NOTICE,
        )
        return {
            "entity_id": str(record.entity_id),
            "title": record.title,
            "severity": severity,
            "cvss": score,
        }

    def attach_evidence(
        self,
        path: str = "artifacts/proof.txt",
        digest: str = "c0ffee" * 10 + "dead",
        mime: str = "text/plain",
    ) -> dict[str, Any]:
        """Attach evidence to the finding and record a redactable payload."""
        finding = self.ref_for(EntityKind.FINDING, "finding")
        record = self.entities.create(
            EntityKind.EVIDENCE,
            title="Supporting evidence",
            summary=f"Evidence captured at {path}.",
            tags=("evidence", "hashed"),
            value=self._ref("evidence"),
            metadata={"sha256": digest, "mime": mime},
        )
        self.entities.link(
            record.entity_id, finding, kind=LinkKind.EVIDENCES, label="supports finding"
        )
        self.artifacts["evidence"] = {"path": path, "sha256": digest}
        self._emit(
            "golden.evidence_attached",
            record.entity_id,
            {
                "path": path,
                "sha256": digest,
                "sessionid": "should-not-be-exported",
                "api_key": "should-not-be-exported",
            },
        )
        return {"entity_id": str(record.entity_id), "sha256": digest, "mime": mime}

    def compose_report(self, title: str = "Golden path release report") -> dict[str, Any]:
        """Compose a report that references the note and contains the finding."""
        note = self.ref_for(EntityKind.NOTE, "note-capture")
        finding = self.ref_for(EntityKind.FINDING, "finding")
        record = self.entities.create(
            EntityKind.REPORT,
            title=title,
            summary="Release report generated from the golden path.",
            tags=("report", "golden"),
            value=self._ref("report"),
            owner="analyst",
            metadata={"sections": 3},
        )
        self.entities.link(record.entity_id, finding, kind=LinkKind.CONTAINS, label="finding")
        self.entities.link(record.entity_id, note, kind=LinkKind.REFERENCES, label="source")
        self._emit(
            "golden.report_composed",
            record.entity_id,
            {"title": title, "sections": 3, "finding": str(finding)},
        )
        return {"entity_id": str(record.entity_id), "sections": 3}

    def export_bundle(self, *, source: str = "") -> GoldenBundle:
        """Export a redacted, deterministic bundle of the current state."""
        events = EventReplay(self.events.records()).collect(redactor=self.redactor)
        bundle = GoldenBundle(
            source=source or self.prefix,
            version="3.0",
            records=tuple(dict(record) for record in self._records()),
            links=tuple(link.as_dict() for link in self.entities.graph().links()),
            events=events,
            digest="",
        )
        digest = compute_etag(bundle.payload())
        sealed = GoldenBundle(
            source=bundle.source,
            version=bundle.version,
            records=bundle.records,
            links=bundle.links,
            events=bundle.events,
            digest=digest,
        )
        self.last_bundle = sealed
        self._emit(
            "golden.exported",
            None,
            {"source": sealed.source, "records": len(sealed.records), "digest": digest},
        )
        return sealed

    def _records(self) -> tuple[Any, ...]:
        """Return entity records in stable id order."""
        refs = sorted(self.entities.snapshot()["records"], key=lambda item: item["entity_id"])
        return tuple(refs)

    @staticmethod
    def verify_bundle(bundle: GoldenBundle) -> bool:
        """Check the digest and basic shape of an exported bundle."""
        if bundle.version != "3.0" or not bundle.records:
            return False
        return compute_etag(bundle.payload()) == bundle.digest

    @classmethod
    def from_bundle(
        cls,
        bundle: GoldenBundle,
        *,
        prefix: str = "",
        correlation_id: str = "golden-import-001",
    ) -> tuple[GoldenPathVault, ImportResult]:
        """Validate and restore a bundle into a fresh local vault."""
        if not cls.verify_bundle(bundle):
            raise GoldenPathError("Bundle digest mismatch or unsupported version")
        vault = cls(prefix=prefix or bundle.source, correlation_id=correlation_id)
        restored = 0
        for payload in bundle.records:
            entity_id = EntityId.parse(payload["entity_id"])
            vault.entities.create(
                entity_id.kind,
                title=payload["title"],
                summary=payload.get("summary", ""),
                tags=tuple(payload.get("tags", ())),
                owner=payload.get("owner", ""),
                value=entity_id.value,
                metadata=dict(payload.get("metadata", {})),
            )
            if payload.get("status"):
                vault.entities.update(entity_id, status=EntityStatus(payload["status"]))
            restored += 1
        links = 0
        for payload in bundle.links:
            source = EntityId.parse(payload["source"])
            target = EntityId.parse(payload["target"])
            vault.entities.link(
                source,
                target,
                kind=LinkKind.parse(payload["kind"]),
                label=payload.get("label", ""),
                weight=float(payload.get("weight", 1.0)),
            )
            links += 1
        result = ImportResult(
            source=bundle.source,
            digest=bundle.digest,
            restored=restored,
            links_restored=links,
            event_count=len(bundle.events),
        )
        vault.imported = result
        vault.artifacts["import"] = {"digest": bundle.digest, "source": bundle.source}
        vault._emit(
            "golden.imported",
            None,
            {
                "source": bundle.source,
                "records": restored,
                "links": links,
                "digest": bundle.digest,
            },
        )
        return vault, result

    def merge_bundle(self, bundle: GoldenBundle, *, source: str = "") -> MergeResult:
        """Merge a peer bundle, skipping records and links already present."""
        if not self.verify_bundle(bundle):
            raise GoldenPathError("Cannot merge a bundle with an invalid digest")
        label = source or bundle.source
        added = 0
        skipped = 0
        for payload in bundle.records:
            entity_id = EntityId.parse(payload["entity_id"])
            if self.entities.find(str(entity_id)) is not None:
                skipped += 1
                continue
            self.entities.create(
                entity_id.kind,
                title=payload["title"],
                summary=payload.get("summary", ""),
                tags=tuple(payload.get("tags", ())),
                owner=payload.get("owner", ""),
                value=entity_id.value,
                metadata=dict(payload.get("metadata", {})) | {"imported_from": label},
            )
            added += 1
        links_added = 0
        links_skipped = 0
        for payload in bundle.links:
            source_id = EntityId.parse(payload["source"])
            target_id = EntityId.parse(payload["target"])
            if (
                self.entities.find(str(source_id)) is None
                or self.entities.find(str(target_id)) is None
            ):
                links_skipped += 1
                continue
            link = EntityLink(
                source=source_id,
                target=target_id,
                kind=LinkKind.parse(payload["kind"]),
                label=payload.get("label", ""),
                weight=float(payload.get("weight", 1.0)),
            )
            try:
                self.entities.graph().add(link)
            except DuplicateLinkError:
                links_skipped += 1
            else:
                links_added += 1
        result = MergeResult(
            source=label,
            added=added,
            skipped=skipped,
            links_added=links_added,
            links_skipped=links_skipped,
        )
        self._emit(
            "golden.merged",
            None,
            {
                "source": label,
                "added": added,
                "skipped": skipped,
                "links_added": links_added,
                "severity": EventSeverity.INFO.value,
            },
        )
        return result

    def stats(self) -> dict[str, Any]:
        """Return serialisable statistics for assertions and dashboards."""
        kinds = self.entities.stats()
        return {
            "prefix": self.prefix,
            "entities": kinds["entities"],
            "links": kinds["links"],
            "events": self.events.size(),
            "checkpoint": self.writer.checkpoint(),
            "outbox": len(self.outbox.all()),
            "correlation_id": self.correlation_id,
        }

    def event_kinds(self) -> tuple[str, ...]:
        """Return published event kinds in sequence order."""
        return tuple(record.kind for record in self.events.records())

    def has_link(self, source: EntityId, target: EntityId, kind: LinkKind) -> bool:
        """Return whether a typed link exists between two entities."""
        return any(
            link.source == source and link.target == target and link.kind is kind
            for link in self.entities.graph().links()
        )
