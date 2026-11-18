"""Operations on report section trees."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from typing import Any

from redscribe.v2.reporting.identifiers import unique_identifier
from redscribe.v2.reporting.models import Finding, ReportSection


def flatten_sections(sections: Iterable[ReportSection]) -> tuple[ReportSection, ...]:
    """Return all sections in depth-first document order."""
    result: list[ReportSection] = []
    for section in sections:
        result.extend(section.walk())
    return tuple(result)


def section_index(sections: Iterable[ReportSection]) -> dict[str, ReportSection]:
    """Index sections by identifier."""
    return {section.identifier: section for section in flatten_sections(sections)}


def find_section(sections: Iterable[ReportSection], identifier: str) -> ReportSection | None:
    """Find one section by identifier."""
    return section_index(sections).get(identifier)


def section_path(sections: Sequence[ReportSection], identifier: str) -> tuple[ReportSection, ...]:
    """Return the ancestor chain ending at ``identifier``."""
    for root in sections:
        for section in root.walk():
            if section.identifier == identifier:
                return (root,)
            if any(child.identifier == identifier for child in section.children):
                return (root, *section_path(section.children, identifier))
    return ()


def update_section(
    sections: Sequence[ReportSection],
    identifier: str,
    **changes: Any,
) -> tuple[ReportSection, ...]:
    """Return a tree with one section replaced by updated fields."""
    result: list[ReportSection] = []
    for section in sections:
        if section.identifier == identifier:
            result.append(replace(section, **changes))
            continue
        result.append(
            replace(
                section,
                children=update_section(section.children, identifier, **changes),
            )
        )
    return tuple(result)


def insert_section(
    sections: Sequence[ReportSection],
    section: ReportSection,
    *,
    parent_id: str = "",
    index: int | None = None,
) -> tuple[ReportSection, ...]:
    """Insert a section at a root or under a parent."""
    result: list[ReportSection]
    if not parent_id:
        result = list(sections)
        position = len(result) if index is None else max(0, min(index, len(result)))
        result.insert(position, section)
        return tuple(result)
    result = []
    for root in sections:
        if root.identifier == parent_id:
            children = list(root.children)
            position = len(children) if index is None else max(0, min(index, len(children)))
            children.insert(position, section)
            result.append(replace(root, children=tuple(children)))
            continue
        nested = insert_section(root.children, section, parent_id=parent_id, index=index)
        result.append(replace(root, children=nested))
    return tuple(result)


def remove_section(sections: Sequence[ReportSection], identifier: str) -> tuple[ReportSection, ...]:
    """Remove one section and its descendants."""
    result: list[ReportSection] = []
    for section in sections:
        if section.identifier == identifier:
            continue
        result.append(replace(section, children=remove_section(section.children, identifier)))
    return tuple(result)


def move_section(
    sections: Sequence[ReportSection],
    identifier: str,
    *,
    parent_id: str = "",
    index: int,
) -> tuple[ReportSection, ...]:
    """Move a section to a new parent and position."""
    section = find_section(sections, identifier)
    if section is None:
        raise ValueError(f"Unknown section: {identifier}")
    if parent_id == identifier or parent_id in {item.identifier for item in section.walk()}:
        raise ValueError("A section cannot be moved into its own subtree")
    removed = remove_section(sections, identifier)
    return insert_section(removed, section, parent_id=parent_id, index=index)


def reorder_sections(
    sections: Sequence[ReportSection], parent_id: str, order: Sequence[str]
) -> tuple[ReportSection, ...]:
    """Replace the child ordering of one section."""
    if not parent_id:
        by_id = {section.identifier: section for section in sections}
        ordered = [by_id[item] for item in order if item in by_id]
        ordered.extend(section for section in sections if section.identifier not in order)
        return tuple(ordered)
    result: list[ReportSection] = []
    for section in sections:
        if section.identifier == parent_id:
            by_id = {child.identifier: child for child in section.children}
            ordered = [by_id[item] for item in order if item in by_id]
            ordered.extend(child for child in section.children if child.identifier not in order)
            result.append(replace(section, children=tuple(ordered)))
            continue
        result.append(
            replace(
                section,
                children=reorder_sections(section.children, parent_id, order),
            )
        )
    return tuple(result)


def renumber_sections(sections: Sequence[ReportSection]) -> tuple[ReportSection, ...]:
    """Recompute display order and depth-derived heading levels."""
    return _renumber(sections, offset=0, depth=1)


def _renumber(
    sections: Sequence[ReportSection], *, offset: int, depth: int
) -> tuple[ReportSection, ...]:
    result: list[ReportSection] = []
    for position, section in enumerate(sections, start=1):
        children = _renumber(section.children, offset=offset + position, depth=depth + 1)
        result.append(
            replace(section, order=offset + position, level=min(6, depth), children=children)
        )
    return tuple(result)


def clone_section_tree(sections: Sequence[ReportSection]) -> tuple[ReportSection, ...]:
    """Return a defensive copy of a section tree."""
    return tuple(
        replace(
            section,
            metadata=dict(section.metadata),
            children=clone_section_tree(section.children),
        )
        for section in sections
    )


def sections_with_findings(sections: Iterable[ReportSection]) -> tuple[ReportSection, ...]:
    """Return sections that contain findings directly."""
    return tuple(section for section in flatten_sections(sections) if section.findings)


def section_stats(sections: Iterable[ReportSection]) -> dict[str, int]:
    """Return counts for sections, findings, and evidence references."""
    items = flatten_sections(sections)
    findings = [finding for section in items for finding in section.findings]
    return {
        "sections": len(items),
        "roots": len([item for item in items if item.level == 1]),
        "findings": len(findings),
        "evidence": sum(len(finding.evidence) for finding in findings),
        "with_body": len([item for item in items if item.body.strip()]),
    }


def assign_unique_identifiers(sections: Sequence[ReportSection]) -> tuple[ReportSection, ...]:
    """Rewrite duplicate section identifiers with numbered variants."""
    used: set[str] = set()
    result: list[ReportSection] = []
    for section in sections:
        identifier = unique_identifier(section.title, used)
        used.add(identifier)
        children = _assign_children(section.children, used)
        result.append(replace(section, identifier=identifier, children=children))
    return tuple(result)


def _assign_children(
    sections: Sequence[ReportSection], used: set[str]
) -> tuple[ReportSection, ...]:
    result: list[ReportSection] = []
    for section in sections:
        identifier = unique_identifier(section.title, used)
        used.add(identifier)
        result.append(
            replace(
                section,
                identifier=identifier,
                children=_assign_children(section.children, used),
            )
        )
    return tuple(result)


def findings_in_sections(sections: Iterable[ReportSection]) -> tuple[Finding, ...]:
    """Collect findings from a section tree in document order."""
    return tuple(finding for section in flatten_sections(sections) for finding in section.findings)


def section_titles(sections: Iterable[ReportSection], *, indent: str = "  ") -> tuple[str, ...]:
    """Render an indented outline of section titles."""
    rows: list[str] = []
    for root in sections:
        _append_titles(rows, root, indent=indent, depth=0)
    return tuple(rows)


def _append_titles(rows: list[str], section: ReportSection, *, indent: str, depth: int) -> None:
    rows.append(f"{indent * depth}{section.title}")
    for child in section.children:
        _append_titles(rows, child, indent=indent, depth=depth + 1)


def section_by_order(sections: Iterable[ReportSection], order: int) -> ReportSection | None:
    """Find the section carrying a display order value."""
    return next(
        (section for section in flatten_sections(sections) if section.order == order),
        None,
    )
