"""Facet extraction with stable counts and drill-down semantics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence

from redscribe.v3.search_intel.types import (
    DEFAULT_FACET_FIELDS,
    FacetCount,
    FacetField,
    FacetResult,
    IndexDocument,
)

FacetSelection = Mapping[str, frozenset[str]]


def normalize_facet_fields(fields: Iterable[str] | str) -> tuple[str, ...]:
    """Normalize and deduplicate an iterable of facet field names."""
    raw = fields.split(",") if isinstance(fields, str) else list(fields)
    result: list[str] = []
    for item in raw:
        parsed = FacetField.parse(str(item))
        if parsed is not None and parsed.value not in result:
            result.append(parsed.value)
    return tuple(result) or DEFAULT_FACET_FIELDS


def normalize_selection(
    selected: Mapping[str, Iterable[str]] | None,
) -> dict[str, frozenset[str]]:
    """Normalize a facet selection mapping to case-folded value sets."""
    if not selected:
        return {}
    result: dict[str, frozenset[str]] = {}
    for name, values in selected.items():
        parsed = FacetField.parse(str(name))
        if parsed is None:
            continue
        folded = frozenset(value.strip().casefold() for value in values if str(value).strip())
        if folded:
            result[parsed.value] = folded
    return result


def document_values(doc: IndexDocument, field: str) -> tuple[str, ...]:
    """Return all facet values a document contributes to a field."""
    parsed = FacetField.parse(field)
    if parsed is None:
        return ()
    if parsed is FacetField.KIND:
        return (doc.kind,)
    if parsed is FacetField.STATUS:
        return (doc.status,)
    if parsed is FacetField.SEVERITY:
        return (doc.severity or "(none)",)
    if parsed is FacetField.TAG:
        seen: set[str] = set()
        ordered: list[str] = []
        for tag in doc.tags:
            folded = tag.casefold()
            if folded not in seen:
                seen.add(folded)
                ordered.append(folded)
        return tuple(ordered)
    if parsed is FacetField.OWNER:
        return (doc.owner.casefold() or "(unassigned)",)
    return ("yes" if doc.has_links else "no",)


def matches_selection(doc: IndexDocument, selection: FacetSelection) -> bool:
    """Return whether a document satisfies every selected facet value."""
    for field, wanted in selection.items():
        values = {value.casefold() for value in document_values(doc, field)}
        if not values.intersection(wanted):
            return False
    return True


def extract_facets(
    docs: Sequence[IndexDocument],
    *,
    fields: Iterable[str] | str = DEFAULT_FACET_FIELDS,
    selected: Mapping[str, Iterable[str]] | None = None,
    limit: int = 20,
) -> tuple[FacetResult, ...]:
    """Extract facet counts for a result set.

    Each field is counted over the documents that satisfy all *other* facet
    selections (the standard "semi-joint" faceted-search behavior). This lets a
    facet sidebar show the alternative values still available to the user.
    """
    normalized_fields = normalize_facet_fields(fields)
    selection = normalize_selection(selected)
    results: list[FacetResult] = []
    cap = max(1, limit)
    for field in normalized_fields:
        other = {name: values for name, values in selection.items() if name != field}
        considered = [doc for doc in docs if matches_selection(doc, other)]
        counter: Counter[str] = Counter()
        missing = 0
        for doc in considered:
            values = document_values(doc, field)
            if not values:
                missing += 1
            counter.update(set(values))
        chosen = selection.get(field, frozenset())
        ordered = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        counts = tuple(
            FacetCount(value=value, count=count, selected=value in chosen)
            for value, count in ordered[:cap]
        )
        results.append(
            FacetResult(
                field=field,
                values=counts,
                total=len(considered),
                missing=missing,
            )
        )
    return tuple(results)


def facet_groups(
    facets: Sequence[FacetResult],
) -> dict[str, tuple[tuple[str, int], ...]]:
    """Return a plain mapping view of facet counts for API responses."""
    return {
        result.field: tuple((item.value, item.count) for item in result.values) for result in facets
    }


def facet_deltas(
    facets: Sequence[FacetResult],
) -> dict[str, tuple[str, ...]]:
    """Return the currently selected values for every facet."""
    return {
        result.field: tuple(item.value for item in result.values if item.selected)
        for result in facets
    }
