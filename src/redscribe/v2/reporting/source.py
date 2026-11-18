"""Vault-to-report source snapshot construction."""

from __future__ import annotations

import re
from collections.abc import Iterable

from redscribe.domain.models import Node
from redscribe.storage.db import Vault
from redscribe.v2.reporting.identifiers import digest_text
from redscribe.v2.reporting.models import (
    SEVERITY_ALIASES,
    SEVERITY_ORDER,
    ReportSource,
    SeverityName,
    SourceNote,
)
from redscribe.v2.reporting.redaction import (
    API_KEY_PATTERN,
    EMAIL_PATTERN,
    FLAG_PATTERN,
    IPV4_PATTERN,
    PRIVATE_KEY_PATTERN,
)

SEVERITY_TAGS = ("critical", "high", "medium", "low", "info", "severe", "major", "minor")
OPEN_STATUSES = ("todo", "active")


def _severity_from_tags(tags: Iterable[str]) -> SeverityName:
    values = {tag.strip().casefold() for tag in tags}
    for tag in SEVERITY_TAGS:
        if tag in values:
            normalized = SEVERITY_ALIASES.get(tag, tag)
            if normalized in SEVERITY_ORDER:
                return normalized
    return "info"


def _is_sensitive(note: Node) -> bool:
    tags = {tag.casefold() for tag in note.tag_list}
    content = f"{note.content}\n{note.tags}"
    if tags & {"secret", "sensitive", "credential", "private"}:
        return True
    patterns = (
        API_KEY_PATTERN,
        PRIVATE_KEY_PATTERN,
        EMAIL_PATTERN,
        FLAG_PATTERN,
        IPV4_PATTERN,
    )
    return any(re.search(pattern, content, re.IGNORECASE) for pattern in patterns)


def note_to_source(note: Node, vault: Vault) -> SourceNote:
    """Convert one vault node into a report source snapshot."""
    tags = tuple(note.tag_list)
    return SourceNote(
        identifier=note.id,
        title=note.title,
        path=vault.path_of(note.id, include_self=False),
        content=note.content,
        tags=tags,
        status=note.status,
        severity=_severity_from_tags(tags),
        category=_first_category(tags),
        target=note.target,
        flag=note.flag,
        updated_at=note.updated_at,
        sensitive=_is_sensitive(note),
    )


def _first_category(tags: Iterable[str]) -> str:
    ignored = set(SEVERITY_TAGS) | {
        "report",
        "finding",
        "evidence",
        "sensitive",
        "secret",
        "credential",
        "private",
    }
    return next((tag for tag in tags if tag.casefold() not in ignored), "")


def build_source(
    vault: Vault,
    *,
    tag: str = "",
    status: str = "",
    root_id: int | None = None,
    generated_at: str = "",
) -> ReportSource:
    """Capture a deterministic snapshot of notes in the vault."""
    notes = [note_to_source(node, vault) for node in vault.live_nodes() if node.is_note]
    if tag:
        needle = tag.casefold()
        notes = [note for note in notes if needle in {value.casefold() for value in note.tags}]
    if status:
        notes = [note for note in notes if note.status == status]
    if root_id is not None:
        allowed = _descendant_ids(vault, root_id)
        notes = [note for note in notes if note.identifier in allowed]
    notes.sort(key=lambda note: (note.path.casefold(), note.title.casefold(), note.identifier))
    revision_parts = [f"{note.identifier}:{note.updated_at}" for note in notes]
    return ReportSource(
        notes=tuple(notes),
        generated_at=generated_at,
        vault_name=vault.path.stem if vault.path is not None else "RedScribe",
        schema_version=int(vault.schema_version),
        revision=digest_text("|".join(revision_parts)),
    )


def _descendant_ids(vault: Vault, root_id: int) -> set[int]:
    root = vault.get_node(root_id)
    if root is None:
        raise ValueError(f"Unknown root node: {root_id}")
    result = {root_id}
    for child in vault.children(root_id):
        result.update(_descendant_ids(vault, child.id))
    return result


def source_digest(source: ReportSource) -> str:
    """Return a digest of a source snapshot."""
    return source.digest()


def source_tags(source: ReportSource) -> tuple[str, ...]:
    """Return sorted distinct tags across a source snapshot."""
    tags = {tag for note in source.notes for tag in note.tags}
    return tuple(sorted(tags, key=str.casefold))


def source_paths(source: ReportSource) -> tuple[str, ...]:
    """Return sorted distinct source paths."""
    paths = {note.path for note in source.notes}
    return tuple(sorted(paths, key=str.casefold))


def source_by_title(source: ReportSource, title: str) -> SourceNote | None:
    """Find a note by exact casefolded title."""
    needle = title.strip().casefold()
    return next((note for note in source.notes if note.title.casefold() == needle), None)
