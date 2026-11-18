"""BM25-style ranking with field boosts, proximity, and explanations."""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any

from redscribe.v2.search.index import InvertedIndex
from redscribe.v2.search.models import (
    DEFAULT_FIELD_BOOSTS,
    FacetCount,
    IndexedDocument,
    ParsedQuery,
    ResultGroup,
    ScoreBreakdown,
    SearchHit,
    SortKey,
    ensure_field_boosts,
)
from redscribe.v2.search.snippets import build_document_snippet, find_query_spans
from redscribe.v2.search.tokenizer import fold_text


@dataclass(frozen=True, slots=True)
class RankingConfig:
    """Tunable weights for relevance scoring."""

    field_boosts: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_FIELD_BOOSTS))
    k1: float = 1.4
    b: float = 0.72
    synonym_weight: float = 0.55
    prefix_weight: float = 0.85
    fuzzy_weight: float = 0.6
    negation_penalty: float = 8.0
    phrase_bonus: float = 14.0
    proximity_bonus: float = 6.0
    proximity_window: int = 5
    pinned_bonus: float = 3.0
    active_bonus: float = 1.5
    recency_bonus: float = 2.0

    def __post_init__(self) -> None:
        if self.k1 <= 0 or not 0 <= self.b <= 1:
            raise ValueError("k1 must be positive and b must be between 0 and 1")
        if any(value < 0 for value in self.field_boosts.values()):
            raise ValueError("field boosts must be non-negative")

    def with_boosts(self, values: Mapping[str, float] | None) -> RankingConfig:
        """Return a copy with merged field boosts."""
        if not values:
            return self
        return replace(self, field_boosts=ensure_field_boosts(values))


def _parse_updated(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


class RankingEngine:
    """Score, order, and group candidate documents."""

    def __init__(self, config: RankingConfig | None = None) -> None:
        self._config = config if config is not None else RankingConfig()

    @property
    def config(self) -> RankingConfig:
        return self._config

    def score(
        self, query: ParsedQuery, document: IndexedDocument, index: InvertedIndex
    ) -> ScoreBreakdown:
        """Compute an explainable relevance score for one document."""
        config = self._config
        stats = index.stats()
        average_length = stats.average_field_length or 1.0
        document_count = max(1, stats.documents)
        components: dict[str, float] = {}
        matched: list[str] = []
        positive = [term for term in query.positive if not term.synonym or term.boost > 0]
        phrases = [term for term in positive if term.phrase]

        for term in positive:
            term_score = self._score_term(term, document, index, document_count, average_length)
            if term_score > 0:
                components[term.key] = components.get(term.key, 0.0) + term_score
                matched.append(term.value)

        if phrases:
            phrase_score = 0.0
            for term in phrases:
                for item in document.fields:
                    if fold_text(term.value) in fold_text(item.text):
                        phrase_score += config.phrase_bonus * term.boost * min(item.boost, 3.0)
                        break
            if phrase_score:
                components["phrase"] = phrase_score

        proximity = self._proximity_score(positive, document, index)
        if proximity:
            components["proximity"] = proximity

        for term in query.negative:
            if index.posting(term.value, document.doc_id) is not None:
                components["negative"] = components.get("negative", 0.0) - config.negation_penalty

        metadata = self._metadata_score(document)
        if metadata:
            components["metadata"] = metadata

        required = [term for term in positive if not term.optional]
        coverage = 1.0
        if required:
            matched_keys = {term.key for term in positive if term.value in matched}
            coverage = len([term for term in required if term.key in matched_keys]) / len(required)
        total = sum(components.values())
        if positive and coverage < 1.0:
            total *= 0.35 + 0.65 * coverage
        return ScoreBreakdown(total, components, tuple(dict.fromkeys(matched)), coverage)

    def _score_term(
        self,
        term: Any,
        document: IndexedDocument,
        index: InvertedIndex,
        document_count: int,
        average_length: float,
    ) -> float:
        config = self._config
        candidates: list[tuple[str, float]] = [(term.value, 1.0)]
        if term.prefix:
            candidates.extend(
                (value, config.prefix_weight) for value in index.prefix_terms(term.value, limit=12)
            )
        if term.fuzzy:
            candidates.extend(
                (value, config.fuzzy_weight)
                for value in index.fuzzy_terms(term.value, max_distance=1, limit=8)
            )
        if term.synonym:
            candidates = [(value, weight * config.synonym_weight) for value, weight in candidates]

        score = 0.0
        seen: set[str] = set()
        for candidate, weight in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            postings = [
                posting
                for posting in index.postings(candidate, field=term.field)
                if posting.doc_id == document.doc_id
            ]
            if not postings:
                continue
            document_frequency = max(1, index.term_stats(candidate).document_frequency)
            idf = math.log(
                1.0 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
            )
            for posting in postings:
                length_ratio = posting.field_length / average_length if average_length else 0.0
                normalization = (
                    posting.frequency
                    * (config.k1 + 1)
                    / (posting.frequency + config.k1 * (1 - config.b + config.b * length_ratio))
                )
                boost = config.field_boosts.get(posting.field, posting.boost)
                score += weight * term.boost * boost * idf * normalization
        return score

    def _proximity_score(
        self,
        terms: Sequence[Any],
        document: IndexedDocument,
        index: InvertedIndex,
    ) -> float:
        if len(terms) < 2:
            return 0.0
        config = self._config
        best = 0.0
        for indexed_field in document.fields:
            positions_by_term: list[list[int]] = []
            for term in terms:
                positions: list[int] = []
                for posting in index.postings(term.value, field=indexed_field.name):
                    if posting.doc_id == document.doc_id:
                        positions.extend(posting.positions)
                if positions:
                    positions_by_term.append(sorted(positions))
            if len(positions_by_term) < 2:
                continue
            adjacent = 0
            for left_positions, right_positions in itertools.pairwise(positions_by_term):
                if any(
                    abs(left - right) <= config.proximity_window
                    for left in left_positions
                    for right in right_positions
                ):
                    adjacent += 1
            best = max(best, adjacent * config.proximity_bonus)
        return best

    def _metadata_score(self, document: IndexedDocument) -> float:
        config = self._config
        score = 0.0
        if document.pinned:
            score += config.pinned_bonus
        if str(document.metadata.get("status", "")) == "active":
            score += config.active_bonus
        updated = _parse_updated(document.updated_at)
        if updated is not None and config.recency_bonus:
            age_days = max(0.0, (datetime.now(timezone.utc) - updated).total_seconds() / 86_400)
            score += config.recency_bonus * max(0.0, 1.0 - min(age_days, 90.0) / 90.0)
        return score

    def rank(
        self,
        query: ParsedQuery,
        documents: Iterable[IndexedDocument],
        index: InvertedIndex,
        *,
        limit: int | None = None,
        group_by: str = "",
        sort: SortKey | None = None,
        width: int = 180,
    ) -> list[SearchHit]:
        """Rank documents and attach highlighted snippets."""
        sort_key = sort if sort is not None else query.sort
        scored: list[tuple[ScoreBreakdown, IndexedDocument]] = []
        for document in documents:
            breakdown = self.score(query, document, index)
            if query.positive and breakdown.total <= 0:
                continue
            scored.append((breakdown, document))

        if sort_key == SortKey.UPDATED:
            scored.sort(
                key=lambda item: (item[1].updated_at, item[0].total, -item[1].doc_id),
                reverse=True,
            )
        elif sort_key == SortKey.TITLE:
            scored.sort(key=lambda item: (item[1].title.casefold(), -item[0].total, item[1].doc_id))
        elif sort_key == SortKey.ID:
            scored.sort(key=lambda item: item[1].doc_id)
        else:
            scored.sort(
                key=lambda item: (item[0].total, -item[1].doc_id),
                reverse=True,
            )

        hits: list[SearchHit] = []
        group_field = group_by or query.group_by
        for breakdown, document in scored:
            hits.append(
                SearchHit(
                    node_id=document.doc_id,
                    title=document.title,
                    path=document.path,
                    snippet=build_document_snippet(document, query, width=width),
                    score=breakdown.total,
                    score_details=breakdown,
                    metadata=dict(document.metadata),
                    group=group_key(document, group_field),
                )
            )
        return hits[:limit] if limit is not None else hits

    def explain(self, hit: SearchHit) -> str:
        """Render one hit's score components as a readable string."""
        details = hit.score_details
        if not details.components:
            return "no score components"
        pieces = [f"{name}={value:+.2f}" for name, value in sorted(details.components.items())]
        return f"{hit.score:.2f} ({', '.join(pieces)}); coverage={details.coverage:.0%}"


def group_key(document: IndexedDocument, group_by: str) -> str:
    """Return a stable bucket key for one document."""
    if not group_by:
        return ""
    if group_by in document.metadata:
        value = document.metadata[group_by]
        if isinstance(value, (list, tuple, set, frozenset)):
            values = [str(item) for item in value if str(item)]
            return values[0].casefold() if values else "none"
        return str(value).casefold() or "none"
    if group_by == "tag":
        tags = document.metadata.get("tags", document.field_text("tags"))
        if isinstance(tags, str):
            tags = [item for item in tags.split(",") if item.strip()]
        values = [str(item).strip() for item in tags if str(item).strip()]
        return values[0].casefold() if values else "untagged"
    if group_by == "path":
        path = document.path.replace("\\", "/").strip("/")
        return path.split("/", 1)[0].casefold() if path else "vault root"
    return str(document.field_text(group_by)).casefold() or "none"


def group_hits(hits: Iterable[SearchHit], group_by: str) -> list[ResultGroup]:
    """Bucket hits by group key in stable first-seen order."""
    buckets: dict[str, list[SearchHit]] = {}
    for hit in hits:
        key = hit.group or group_key_from_hit(hit, group_by)
        buckets.setdefault(key, []).append(hit)
    groups: list[ResultGroup] = []
    for key, items in buckets.items():
        label = key.replace("_", " ").title() if key else "Results"
        groups.append(ResultGroup(key=key, label=label, hits=tuple(items), total=len(items)))
    return groups


def group_key_from_hit(hit: SearchHit, group_by: str) -> str:
    metadata = hit.metadata
    if group_by in metadata:
        return str(metadata[group_by]).casefold()
    return ""


def facet_counts(
    hits: Iterable[SearchHit], field: str, *, limit: int = 20
) -> tuple[FacetCount, ...]:
    """Compute facets directly from hits for small client-side datasets."""
    counts: dict[str, int] = {}
    for hit in hits:
        value = hit.metadata.get(field, "")
        values = value if isinstance(value, (list, tuple, set)) else [value]
        for item in values:
            text = str(item).strip()
            if text:
                counts[text] = counts.get(text, 0) + 1
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0].casefold()))
    return tuple(FacetCount(value, count) for value, count in ordered[:limit])


def matched_term_count(query: ParsedQuery, document: IndexedDocument, index: InvertedIndex) -> int:
    """Return how many positive query terms occur in a document."""
    terms = [term.value for term in query.positive]
    return sum(
        1
        for term in terms
        if index.documents_for_term(term) and document.doc_id in index.documents_for_term(term)
    )


def query_coverage(query: ParsedQuery, document: IndexedDocument, index: InvertedIndex) -> float:
    """Return the fraction of positive query terms found in a document."""
    terms = [term.value for term in query.positive]
    if not terms:
        return 1.0
    return matched_term_count(query, document, index) / len(terms)


def highlight_preview(hit: SearchHit) -> tuple[str, ...]:
    """Return the highlighted text chunks of a hit for UI rendering."""
    return tuple(chunk.text for chunk in hit.snippet.chunks() if chunk.match)


def sort_hits(hits: Sequence[SearchHit], key: SortKey) -> list[SearchHit]:
    """Reorder hits without changing their identity or score."""
    if key == SortKey.UPDATED:
        return sorted(hits, key=lambda hit: hit.metadata.get("updated_at", ""), reverse=True)
    if key == SortKey.TITLE:
        return sorted(hits, key=lambda hit: hit.title.casefold())
    if key == SortKey.ID:
        return sorted(hits, key=lambda hit: hit.node_id)
    return sorted(hits, key=lambda hit: (-hit.score, -hit.node_id))


def score_label(score: float) -> str:
    """Return a compact relevance label for UI badges."""
    if score >= 25:
        return "exact"
    if score >= 10:
        return "strong"
    if score >= 2:
        return "related"
    return "weak"


def snippet_matches_query(hit: SearchHit, query: ParsedQuery) -> bool:
    """Return whether a hit's snippet highlights any query term."""
    terms = [term.value for term in query.positive]
    if not terms:
        return True
    return bool(find_query_spans(hit.snippet.text, terms))


def rerank_by_group(hits: Sequence[SearchHit], preferred: str) -> list[SearchHit]:
    """Move hits from one group to the front while preserving relative order."""
    target = preferred.casefold()
    selected = [hit for hit in hits if hit.group.casefold() == target]
    remainder = [hit for hit in hits if hit.group.casefold() != target]
    return [*selected, *remainder]
