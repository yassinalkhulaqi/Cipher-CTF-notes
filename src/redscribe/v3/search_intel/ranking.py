"""Deterministic relevance scoring and fragment rendering."""

from __future__ import annotations

from collections.abc import Sequence

from redscribe.v3.search_intel.types import (
    ClauseKind,
    FieldName,
    Fragment,
    Highlight,
    IndexDocument,
    ParsedQuery,
    QueryClause,
    RankDetails,
    RankedHit,
)

_YEAR_SECONDS = 365.25 * 24 * 60 * 60
_FRAGMENT_WIDTH = 140


def _field_match(doc: IndexDocument, clause: QueryClause) -> bool:
    field = clause.field
    if field == FieldName.KIND.value:
        return doc.kind == clause.value
    if field == FieldName.TAG.value:
        return clause.value in {tag.casefold() for tag in doc.tags}
    if field == FieldName.SEVERITY.value:
        return doc.severity == clause.value
    if field == FieldName.STATUS.value:
        return doc.status == clause.value
    if field == FieldName.BEFORE.value:
        return doc.updated_at < clause.before
    return False


def clause_matches(doc: IndexDocument, clause: QueryClause) -> tuple[bool, tuple[str, ...]]:
    """Evaluate one clause against a document, returning match and terms."""
    if clause.kind is ClauseKind.FIELD:
        matched = _field_match(doc, clause)
        if clause.negated:
            return not matched, ()
        return matched, ()
    if clause.kind is ClauseKind.HAS_LINK:
        matched = doc.has_links
        if clause.link_kind:
            matched = clause.link_kind in doc.link_kinds
        if clause.negated:
            return not matched, ()
        return matched, ()
    haystack = f"{doc.title} {doc.summary} {' '.join(doc.tags)}".casefold()
    if clause.phrase:
        matched = clause.value in haystack
    else:
        tokens = doc.tokens
        matched = clause.value in tokens or (
            len(clause.value) >= 3 and any(token.startswith(clause.value) for token in tokens)
        )
    if clause.negated:
        return not matched, ()
    return matched, (clause.value,) if matched else ()


def query_matches(doc: IndexDocument, parsed: ParsedQuery) -> tuple[bool, tuple[str, ...]]:
    """Return whether a document matches any conjunction group of a query."""
    terms: list[str] = []
    for group in parsed.groups:
        group_ok = True
        local: list[str] = []
        for clause in group.clauses:
            ok, matched = clause_matches(doc, clause)
            if not ok:
                group_ok = False
                break
            local.extend(matched)
        if group_ok:
            terms.extend(local)
            return True, tuple(dict.fromkeys(terms))
    return False, ()


def score_document(
    doc: IndexDocument,
    parsed: ParsedQuery,
    *,
    matched_terms: Sequence[str] = (),
    now: float = 0.0,
) -> RankDetails:
    """Compute an explainable score for a matching document."""
    components: dict[str, float] = {
        "title": 0.0,
        "content": 0.0,
        "phrase": 0.0,
        "field": 0.0,
        "link": 0.0,
        "coverage": 0.0,
        "recency": 0.0,
    }
    title = doc.title.casefold()
    body = f"{doc.summary} {' '.join(doc.tags)}".casefold()
    for term in matched_terms:
        if term in title:
            components["title"] += 4.0
        elif term in body:
            components["content"] += 1.5
        else:
            components["content"] += 0.75
    for clause in parsed.clauses:
        if clause.negated:
            continue
        if clause.phrase:
            components["phrase"] += 3.0
        if clause.kind is ClauseKind.FIELD:
            components["field"] += 1.25
        if clause.kind is ClauseKind.HAS_LINK:
            components["link"] += 0.5 + min(1.0, doc.link_degree * 0.1)
    positive_terms = {
        clause.value
        for clause in parsed.clauses
        if not clause.negated and clause.kind is ClauseKind.TERM
    }
    coverage = (
        len(set(matched_terms) & positive_terms) / len(positive_terms) if positive_terms else 1.0
    )
    components["coverage"] = coverage * 3.0
    if now > 0 and doc.updated_at > 0:
        age = max(0.0, now - doc.updated_at)
        components["recency"] = max(0.0, 1.0 - age / _YEAR_SECONDS)
    components = {key: round(value, 6) for key, value in components.items()}
    return RankDetails(
        total=round(sum(components.values()), 6),
        components=components,
        matched_terms=tuple(sorted(set(matched_terms))),
        coverage=round(coverage, 6),
    )


def build_fragment(
    doc: IndexDocument,
    terms: Sequence[str],
    *,
    width: int = _FRAGMENT_WIDTH,
    field: str = "summary",
) -> Fragment:
    """Build a short snippet with exact highlight offsets."""
    source = doc.summary if field == "summary" else doc.title
    clean = " ".join(source.split())
    if not clean:
        clean = " ".join(doc.title.split())
    folded = clean.casefold()
    positions = [
        folded.find(term.casefold()) for term in terms if term and term.casefold() in folded
    ]
    positions = [position for position in positions if position >= 0]
    if not positions:
        truncated = clean[:width]
        return Fragment(
            text=truncated,
            prefix=False,
            suffix=len(clean) > width,
            field=field,
        )
    first = min(positions)
    span = max(1, min(width, len(clean)))
    start = max(0, first - span // 3)
    end = min(len(clean), start + span)
    text = clean[start:end]
    highlights: list[Highlight] = []
    for term in sorted(set(terms), key=lambda item: (-len(item), item)):
        needle = term.casefold()
        if not needle:
            continue
        cursor = text.casefold().find(needle)
        while cursor >= 0:
            highlights.append(
                Highlight(
                    start=cursor,
                    end=cursor + len(term),
                    value=text[cursor : cursor + len(term)],
                    field=field,
                )
            )
            cursor = text.casefold().find(needle, cursor + len(needle))
    highlights.sort(key=lambda item: (item.start, item.end))
    return Fragment(
        text=text,
        highlights=tuple(highlights),
        field=field,
        prefix=start > 0,
        suffix=end < len(clean),
    )


def rank_documents(
    docs: Sequence[IndexDocument],
    parsed: ParsedQuery,
    *,
    limit: int = 50,
    now: float = 0.0,
) -> tuple[RankedHit, ...]:
    """Filter, score, and order matching documents."""
    hits: list[RankedHit] = []
    for doc in docs:
        matched, terms = query_matches(doc, parsed)
        if not matched:
            continue
        details = score_document(doc, parsed, matched_terms=terms, now=now)
        hits.append(
            RankedHit(
                doc=doc,
                score=details.total,
                details=details,
                fragment=build_fragment(doc, terms),
            )
        )
    hits.sort(key=lambda hit: (-hit.score, hit.ref))
    return tuple(hits[: max(0, limit)])


def rank_stable(hits: Sequence[RankedHit]) -> bool:
    """Return whether a hit list is in canonical rank order."""
    keys = [(-hit.score, hit.ref) for hit in hits]
    return keys == sorted(keys)
