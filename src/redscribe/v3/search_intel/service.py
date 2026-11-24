"""High-level search intelligence service combining all B05 primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities.service import EntityService
from redscribe.v3.search_intel.clustering import cluster_documents
from redscribe.v3.search_intel.facets import (
    extract_facets,
    normalize_facet_fields,
)
from redscribe.v3.search_intel.index import SearchIndex
from redscribe.v3.search_intel.parser import parse_query
from redscribe.v3.search_intel.pivots import pivot_context, suggest_pivots
from redscribe.v3.search_intel.ranking import rank_documents
from redscribe.v3.search_intel.saved import (
    SavedFacetSetStore,
    SavedSearchStore,
    normalize_tags,
)
from redscribe.v3.search_intel.templates import TemplateRegistry
from redscribe.v3.search_intel.types import (
    FIELD_VOCABULARY,
    QUERY_FIELDS,
    ClusterStrategy,
    ParsedQuery,
)


@dataclass(frozen=True, slots=True)
class Completion:
    """One autocomplete candidate for the query builder."""

    value: str
    label: str
    kind: str
    insert_text: str
    start: int
    end: int
    score: float

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "value": self.value,
            "label": self.label,
            "kind": self.kind,
            "insert_text": self.insert_text,
            "start": self.start,
            "end": self.end,
            "score": round(self.score, 6),
        }


class SearchIntelService:
    """Compose query parsing, ranking, facets, clusters, pivots and storage."""

    def __init__(
        self,
        entities: EntityService | None = None,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._clock: Clock = clock or SystemClock()
        self.entities = entities or EntityService(clock=self._clock)
        self.index = SearchIndex(clock=self._clock)
        self.index.attach(self.entities)
        self.saved = SavedSearchStore(clock=self._clock)
        self.facet_sets = SavedFacetSetStore(clock=self._clock)
        self.templates = TemplateRegistry()

    def parse(self, query: str) -> ParsedQuery:
        """Parse a query expression."""
        return parse_query(query)

    def search(
        self,
        query: str,
        *,
        fields: tuple[str, ...] | str | None = None,
        selected: dict[str, list[str]] | None = None,
        cluster_by: str = ClusterStrategy.FIELD.value,
        cluster_field: str = "kind",
        limit: int = 50,
        facet_limit: int = 20,
        pivot_limit: int = 6,
        now: float = 0.0,
    ) -> dict[str, Any]:
        """Run a full cross-entity search and return a UI-ready payload."""
        parsed = self.parse(query)
        hits = rank_documents(self.index.documents(), parsed, limit=limit, now=now)
        facet_fields = normalize_facet_fields(fields) if fields is not None else None
        facets = (
            extract_facets(
                tuple(hit.doc for hit in hits),
                fields=facet_fields if facet_fields else (),
                selected=selected,
                limit=facet_limit,
            )
            if facet_fields is not None
            else ()
        )
        clusters = cluster_documents(
            hits,
            strategy=cluster_by,
            field=cluster_field,
        )
        pivots: list[dict[str, Any]] = []
        for hit in hits[: max(0, pivot_limit)]:
            context = pivot_context(hit.ref, self.entities, limit=4)
            if context["pivots"]:
                pivots.append(context)
        return {
            "query": parsed.as_dict(),
            "hits": [hit.as_dict() for hit in hits],
            "total": len(hits),
            "facets": [facet.as_dict() for facet in facets],
            "clusters": [cluster.as_dict() for cluster in clusters],
            "pivots": pivots,
            "index": self.index.state().as_dict(),
        }

    def facets(
        self,
        query: str,
        *,
        fields: tuple[str, ...] | str | None = None,
        selected: dict[str, list[str]] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Compute facets over the documents matching a query."""
        parsed = self.parse(query)
        docs = tuple(hit.doc for hit in rank_documents(self.index.documents(), parsed))
        chosen = normalize_facet_fields(fields) if fields else None
        return [
            facet.as_dict()
            for facet in extract_facets(
                docs,
                fields=chosen if chosen else (),
                selected=selected,
                limit=limit,
            )
        ]

    def clusters(
        self,
        query: str,
        *,
        strategy: str = ClusterStrategy.FIELD.value,
        field: str = "kind",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Cluster the documents matching a query."""
        parsed = self.parse(query)
        hits = rank_documents(self.index.documents(), parsed, limit=limit)
        return [
            cluster.as_dict() for cluster in cluster_documents(hits, strategy=strategy, field=field)
        ]

    def pivots(self, ref: str, *, limit: int = 8, depth: int = 1) -> dict[str, Any]:
        """Return a pivot payload for one entity reference."""
        return (
            pivot_context(ref, self.entities, limit=limit)
            if depth == 1
            else {
                "origin": ref,
                "pivots": [
                    item.as_dict()
                    for item in suggest_pivots(ref, self.entities, limit=limit, depth=depth)
                ],
            }
        )

    def _known_tags(self) -> list[str]:
        return sorted({tag.casefold() for doc in self.index.documents() for tag in doc.tags})

    def autocomplete(self, text: str, *, limit: int = 8) -> tuple[Completion, ...]:
        """Suggest field names, values, tags, saved searches and templates."""
        start = text.rfind(" ") + 1
        partial = text[start:]
        needle = partial.casefold()
        if not needle:
            return ()
        candidates: list[Completion] = []
        if ":" in partial:
            field_text, value_text = partial.split(":", 1)
            field = field_text.lstrip("-").casefold()
            vocabulary = FIELD_VOCABULARY.get(field, ())
            known_tags = self._known_tags()
            values = list(vocabulary) + known_tags
            for value in values:
                if value.casefold().startswith(value_text.casefold()):
                    candidates.append(
                        Completion(
                            value=value,
                            label=f"{field}:{value}",
                            kind="value",
                            insert_text=f"{field}:{value} ",
                            start=start,
                            end=len(text),
                            score=10.0 - len(value_text),
                        )
                    )
        else:
            for field in QUERY_FIELDS:
                if field.startswith(needle.lstrip("-")):
                    candidates.append(
                        Completion(
                            value=f"{field}:",
                            label=f"{field}:",
                            kind="field",
                            insert_text=f"{field}:",
                            start=start,
                            end=len(text),
                            score=20.0 - len(partial),
                        )
                    )
            for saved in self.saved.list(search=needle, limit=4):
                candidates.append(
                    Completion(
                        value=saved.query,
                        label=saved.name,
                        kind="saved",
                        insert_text=saved.query,
                        start=start,
                        end=len(text),
                        score=8.0,
                    )
                )
            for template in self.templates.suggest(needle, limit=3):
                candidates.append(
                    Completion(
                        value=template.id,
                        label=template.name,
                        kind="template",
                        insert_text=template.example or template.pattern,
                        start=start,
                        end=len(text),
                        score=6.0,
                    )
                )
            for tag in self._known_tags():
                if tag.startswith(needle.lstrip("-")):
                    candidates.append(
                        Completion(
                            value=tag,
                            label=f"tag:{tag}",
                            kind="tag",
                            insert_text=f"tag:{tag} ",
                            start=start,
                            end=len(text),
                            score=4.0,
                        )
                    )
        candidates.sort(key=lambda item: (-item.score, item.label, item.start))
        seen: set[str] = set()
        unique: list[Completion] = []
        for candidate in candidates:
            if candidate.label in seen:
                continue
            seen.add(candidate.label)
            unique.append(candidate)
        return tuple(unique[: max(0, limit)])

    def snapshot(self) -> dict[str, Any]:
        """Serialize all mutable B05 state."""
        return {
            "version": 1,
            "saved": self.saved.to_dict(),
            "facet_sets": self.facet_sets.to_dict(),
        }

    def load(self, payload: dict[str, Any]) -> int:
        """Restore saved state, returning the number of imported items."""
        count = self.saved.load(payload.get("saved", ()))
        count += self.facet_sets.load(payload.get("facet_sets", ()))
        return count

    def save_search(
        self,
        name: str,
        query: str,
        *,
        description: str = "",
        tags: str | tuple[str, ...] = (),
        pinned: bool = False,
    ) -> dict[str, Any]:
        """Create a saved search and return its view."""
        return self.saved.create(
            name,
            query,
            description=description,
            tags=normalize_tags(tags),
            pinned=pinned,
        ).as_dict()
