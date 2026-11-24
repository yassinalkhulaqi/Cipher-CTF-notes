"""Incremental search index with universal-entity change hooks."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities.ids import try_parse
from redscribe.v3.entities.service import EntityService
from redscribe.v3.entities.types import EntityId, EntityRecord
from redscribe.v3.events.types import DomainEvent
from redscribe.v3.search_intel.types import IndexDocument, IndexState


def document_from_record(
    record: EntityRecord,
    *,
    link_degree: int = 0,
    link_kinds: tuple[str, ...] = (),
) -> IndexDocument:
    """Project a universal entity record into a search document."""
    severity = str(record.metadata.get("severity", "") or "").casefold()
    return IndexDocument(
        ref=str(record.entity_id),
        kind=record.entity_id.kind.value,
        title=record.title,
        summary=record.summary,
        tags=record.tags,
        status=record.status.value,
        severity=severity,
        owner=record.owner,
        updated_at=record.updated_at,
        has_links=link_degree > 0 or bool(link_kinds),
        link_degree=link_degree,
        link_kinds=tuple(sorted(set(link_kinds))),
        version=record.version,
        metadata=dict(record.metadata),
    )


def document_from_dict(payload: dict[str, Any]) -> IndexDocument | None:
    """Rebuild a search document from its serialized form."""
    ref = str(payload.get("ref", ""))
    if not ref:
        return None
    return IndexDocument(
        ref=ref,
        kind=str(payload.get("kind", "note")),
        title=str(payload.get("title", "")),
        summary=str(payload.get("summary", "")),
        tags=tuple(str(tag) for tag in payload.get("tags", ())),
        status=str(payload.get("status", "draft")),
        severity=str(payload.get("severity", "")),
        owner=str(payload.get("owner", "")),
        updated_at=float(payload.get("updated_at", 0.0)),
        has_links=bool(payload.get("has_links", False)),
        link_degree=int(payload.get("link_degree", 0)),
        link_kinds=tuple(str(kind) for kind in payload.get("link_kinds", ())),
        version=int(payload.get("version", 1)),
        metadata=dict(payload.get("metadata", {})),
    )


class SearchIndex:
    """Inverted index updated incrementally from entity and domain events."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or SystemClock()
        self._docs: dict[str, IndexDocument] = {}
        self._inverted: dict[str, set[str]] = defaultdict(set)
        self._generation = 0
        self._dirty: set[str] = set()
        self._last_action = "init"

    def __len__(self) -> int:
        return len(self._docs)

    def upsert(self, doc: IndexDocument) -> None:
        """Insert or replace a document and refresh its token postings."""
        existing = self._docs.get(doc.ref)
        if existing is not None:
            for token in existing.tokens:
                self._inverted[token].discard(doc.ref)
                if not self._inverted[token]:
                    self._inverted.pop(token, None)
        self._docs[doc.ref] = doc
        for token in doc.tokens:
            self._inverted[token].add(doc.ref)
        self._generation += 1
        self._dirty.add(doc.ref)
        self._last_action = "upsert"

    def remove(self, ref: str) -> bool:
        """Remove a document by reference."""
        existing = self._docs.pop(ref, None)
        if existing is None:
            return False
        for token in existing.tokens:
            self._inverted[token].discard(ref)
            if not self._inverted[token]:
                self._inverted.pop(token, None)
        self._generation += 1
        self._dirty.discard(ref)
        self._last_action = "remove"
        return True

    def find(self, ref: str) -> IndexDocument | None:
        """Look up one indexed document."""
        return self._docs.get(ref)

    def documents(self) -> tuple[IndexDocument, ...]:
        """Return all documents in stable reference order."""
        return tuple(self._docs[ref] for ref in sorted(self._docs))

    def postings(self, token: str) -> frozenset[str]:
        """Return references for a case-folded token."""
        return frozenset(self._inverted.get(token.casefold(), ()))

    def apply_entity_event(
        self,
        action: str,
        record: EntityRecord,
        *,
        link_degree: int = 0,
        link_kinds: tuple[str, ...] = (),
    ) -> None:
        """Apply a universal-entity change notification."""
        if action == "deleted" or record.status.value == "deleted":
            self.remove(str(record.entity_id))
            return
        self.upsert(document_from_record(record, link_degree=link_degree, link_kinds=link_kinds))

    def consume_event(self, event: DomainEvent) -> bool:
        """Consume a domain event emitted by an owning branch."""
        payload = event.payload
        nested = payload.get("payload")
        if isinstance(nested, dict):
            payload = nested
        if event.kind.endswith(".deleted") or event.kind.endswith(".removed"):
            ref = str(payload.get("ref", event.subject_ref))
            return self.remove(ref)
        raw = payload.get("record")
        if not isinstance(raw, dict):
            return False
        doc = document_from_dict(raw)
        if doc is None:
            return False
        self.upsert(doc)
        return True

    def attach(self, service: EntityService) -> None:
        """Subscribe to an entity service for automatic incremental updates."""

        def on_change(action: str, record: EntityRecord) -> None:
            self.apply_entity_event(action, record)

        service.subscribe(on_change)

    def refresh_links(self, service: EntityService) -> int:
        """Recompute link metadata for every indexed document."""
        changed = 0
        for doc in self.documents():
            entity_id = doc.ref
            parsed = _parse_ref(entity_id)
            if parsed is None:
                continue
            degree = service.graph().degree(parsed)
            kinds = tuple(
                sorted(
                    {
                        link.kind.value
                        for link in (
                            *service.graph().for_source(parsed),
                            *service.graph().for_target(parsed),
                        )
                    }
                )
            )
            updated = _with_links(doc, degree, kinds)
            if updated != doc:
                self.upsert(updated)
                changed += 1
        return changed

    def reindex(self, docs: Sequence[IndexDocument]) -> None:
        """Rebuild the whole index from a document collection."""
        self._docs.clear()
        self._inverted.clear()
        self._dirty.clear()
        for doc in docs:
            self._docs[doc.ref] = doc
            for token in doc.tokens:
                self._inverted[token].add(doc.ref)
        self._generation += 1
        self._last_action = "reindex"

    def drain_dirty(self) -> tuple[str, ...]:
        """Return and clear the set of changed references."""
        changed = tuple(sorted(self._dirty))
        self._dirty.clear()
        return changed

    def state(self, *, by_kind_limit: int = 20) -> IndexState:
        """Return a snapshot of index state for observability."""
        by_kind = Counter(doc.kind for doc in self._docs.values())
        counts = dict(sorted(by_kind.items())[: max(1, by_kind_limit)])
        return IndexState(
            generation=self._generation,
            documents=len(self._docs),
            tokens=len(self._inverted),
            dirty=len(self._dirty),
            by_kind=counts,
            last_action=self._last_action,
        )


def _parse_ref(raw: str) -> EntityId | None:
    return try_parse(raw)


def _with_links(
    doc: IndexDocument,
    degree: int,
    kinds: tuple[str, ...],
) -> IndexDocument:
    return IndexDocument(
        ref=doc.ref,
        kind=doc.kind,
        title=doc.title,
        summary=doc.summary,
        tags=doc.tags,
        status=doc.status,
        severity=doc.severity,
        owner=doc.owner,
        updated_at=doc.updated_at,
        has_links=degree > 0,
        link_degree=degree,
        link_kinds=kinds,
        version=doc.version,
        metadata=dict(doc.metadata),
    )
