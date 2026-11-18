"""Typed links between evidence items and findings."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from redscribe.v2.evidence.errors import ConflictError, ValidationError
from redscribe.v2.evidence.models import FindingLink, LinkType
from redscribe.v2.evidence.validation import (
    now_iso,
    optional_float,
    validate_evidence_id,
)

POSITIVE_LINKS: frozenset[LinkType] = frozenset({LinkType.SUPPORTS, LinkType.CONTAINS})
NEGATIVE_LINKS: frozenset[LinkType] = frozenset({LinkType.REFUTES, LinkType.DUPLICATE_OF})


def link_key(evidence_id: str, finding_id: str, link_type: LinkType) -> tuple[str, str, str]:
    """Return the uniqueness key for a finding link."""
    return evidence_id, finding_id.casefold(), link_type.value


def validate_link(link: FindingLink) -> None:
    """Raise when a finding link has invalid fields."""
    validate_evidence_id(link.evidence_id, field="evidence_id")
    if not link.finding_id.strip():
        raise ValidationError("Finding id is required", details={"field": "finding_id"})
    if not 0 <= link.strength <= 1:
        raise ValidationError(
            "Link strength must be between 0 and 1", details={"field": "strength"}
        )
    if link.strength > 0 and not link.link_type:
        raise ValidationError("Link type is required", details={"field": "link_type"})


def link_weight(link: FindingLink) -> float:
    """Return a signed weight used to rank supporting and refuting links."""
    if link.link_type in POSITIVE_LINKS:
        return link.strength
    if link.link_type in NEGATIVE_LINKS:
        return -link.strength
    return round(link.strength * 0.5, 3)


class FindingLinkIndex:
    """In-memory index for finding links with stable sequence ids."""

    def __init__(self, links: Iterable[FindingLink] = ()) -> None:
        self._links = sorted(links, key=lambda item: item.id)

    @property
    def links(self) -> tuple[FindingLink, ...]:
        return tuple(self._links)

    def next_id(self) -> int:
        """Return the next link sequence number."""
        if not self._links:
            return 1
        return max(item.id for item in self._links) + 1

    def replace(self, links: Iterable[FindingLink]) -> None:
        """Replace all indexed links."""
        self._links = sorted(links, key=lambda item: item.id)

    def find_duplicate(
        self,
        evidence_id: str,
        finding_id: str,
        link_type: LinkType,
    ) -> FindingLink | None:
        """Return an existing link with the same identity key, if present."""
        key = link_key(evidence_id, finding_id, link_type)
        for link in self._links:
            if link_key(link.evidence_id, link.finding_id, link.link_type) == key:
                return link
        return None

    def add(
        self,
        *,
        evidence_id: str,
        finding_id: str,
        finding_title: str = "",
        link_type: LinkType = LinkType.RELATED_TO,
        strength: float = 0.5,
        created_by: str = "",
        created_at: str = "",
        note: str = "",
        allow_duplicate: bool = False,
        link_id: int | None = None,
    ) -> FindingLink:
        """Create and index a finding link."""
        record_id = validate_evidence_id(evidence_id, field="evidence_id")
        target = finding_id.strip()
        if not target or len(target) > 120:
            raise ValidationError("'finding_id' is required", details={"field": "finding_id"})
        resolved_strength = optional_float({"strength": strength}, "strength", default=0.5)
        duplicate = self.find_duplicate(record_id, target, link_type)
        if duplicate is not None and not allow_duplicate:
            raise ConflictError(
                "That finding link already exists",
                details={"evidence_id": record_id, "finding_id": target},
            )
        link = FindingLink(
            id=link_id if link_id is not None else self.next_id(),
            evidence_id=record_id,
            finding_id=target,
            finding_title=finding_title.strip()[:200] or target,
            link_type=link_type,
            strength=resolved_strength,
            created_at=created_at or now_iso(),
            created_by=created_by.strip()[:120],
            note=note.strip()[:1_000],
        )
        validate_link(link)
        self._links.append(link)
        self._links.sort(key=lambda item: item.id)
        return link

    def remove(self, link_id: int) -> FindingLink:
        """Remove a link by id and return it."""
        for index, link in enumerate(self._links):
            if link.id == link_id:
                return self._links.pop(index)
        raise ValidationError(
            f"Finding link {link_id} does not exist", details={"field": "link_id"}
        )

    def get(self, link_id: int) -> FindingLink | None:
        """Return one link by id."""
        return next((item for item in self._links if item.id == link_id), None)

    def for_evidence(self, evidence_id: str) -> list[FindingLink]:
        """Return links attached to one evidence item."""
        return [item for item in self._links if item.evidence_id == evidence_id]

    def for_finding(self, finding_id: str) -> list[FindingLink]:
        """Return links attached to one finding, case-insensitively."""
        needle = finding_id.casefold()
        return [item for item in self._links if item.finding_id.casefold() == needle]

    def strongest(self, evidence_id: str) -> FindingLink | None:
        """Return the strongest link for one evidence item."""
        candidates = self.for_evidence(evidence_id)
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item.strength, -item.id))


def update_link(
    link: FindingLink,
    *,
    finding_title: str | None = None,
    link_type: LinkType | None = None,
    strength: float | None = None,
    note: str | None = None,
) -> FindingLink:
    """Return a link with updated editable fields."""
    payload = link.as_dict()
    if finding_title is not None:
        payload["finding_title"] = finding_title.strip()[:200]
    if link_type is not None:
        payload["link_type"] = link_type.value
    if strength is not None:
        payload["strength"] = optional_float({"strength": strength}, "strength")
    if note is not None:
        payload["note"] = note.strip()[:1_000]
    return FindingLink.from_dict(payload)


def group_by_type(links: Sequence[FindingLink]) -> dict[str, list[dict[str, Any]]]:
    """Group serialized links by relationship type."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        groups.setdefault(link.link_type.value, []).append(link.as_dict())
    return {key: groups[key] for key in sorted(groups)}


def link_summary(links: Sequence[FindingLink]) -> dict[str, Any]:
    """Return compact link statistics."""
    finding_ids = {item.finding_id.casefold() for item in links}
    return {
        "total": len(links),
        "findings": len(finding_ids),
        "supporting": sum(1 for item in links if item.link_type in POSITIVE_LINKS),
        "refuting": sum(1 for item in links if item.link_type in NEGATIVE_LINKS),
        "average_strength": round(sum(item.strength for item in links) / len(links), 3)
        if links
        else 0.0,
    }


def link_sort_key(link: FindingLink) -> tuple[float, int]:
    """Return a deterministic ranking key for a link."""
    return -link.strength, link.id


def link_from_manifest(value: Mapping[str, Any]) -> FindingLink:
    """Parse a link from a manifest mapping."""
    return FindingLink.from_dict(value)
