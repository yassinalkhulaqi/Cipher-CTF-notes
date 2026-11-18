"""Evidence extraction, excerpting, and completeness checks."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import replace

from redscribe.v2.reporting.identifiers import digest_text
from redscribe.v2.reporting.models import (
    EVIDENCE_KINDS,
    EvidenceRef,
    Finding,
    SourceNote,
)

COMMAND_LINE_RE = re.compile(r"^\s*(?:\$|#|λ)\s+(.+)$")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")


def evidence_from_note(note: SourceNote, *, locator: str = "") -> EvidenceRef:
    """Create an evidence reference from one source note."""
    return EvidenceRef(
        identifier=f"note-{note.identifier}",
        title=note.title,
        content=note.content,
        kind="note",
        source_id=note.identifier,
        source_path=note.path,
        source_updated_at=note.updated_at,
        locator=locator,
        excerpt=excerpt(note.content),
        sensitive=note.sensitive,
    )


def evidence_from_notes(notes: Iterable[SourceNote]) -> tuple[EvidenceRef, ...]:
    """Create one evidence reference per source note."""
    return tuple(evidence_from_note(note) for note in notes)


def excerpt(text: str, *, width: int = 240, line_limit: int = 8) -> str:
    """Return a compact readable excerpt from Markdown content."""
    if width < 20:
        raise ValueError("width must be at least 20")
    lines: list[str] = []
    in_fence = False
    for raw in text.splitlines():
        line = raw.strip()
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        heading = HEADING_RE.match(line)
        if heading:
            line = heading.group(1)
        command = COMMAND_LINE_RE.match(line)
        if command:
            line = f"$ {command.group(1)}"
        lines.append(line)
        if len(lines) >= line_limit:
            break
    value = " ".join(lines).strip()
    if len(value) <= width:
        return value
    return value[: width - 1].rstrip() + "…"


def evidence_digest(evidence: EvidenceRef) -> str:
    """Return a stable digest of an evidence reference."""
    return digest_text(
        "|".join((evidence.identifier, evidence.title, evidence.source_path, evidence.content))
    )


def evidence_signature(evidence: Sequence[EvidenceRef]) -> str:
    """Return a digest of an ordered evidence collection."""
    return digest_text("|".join(evidence_digest(item) for item in evidence))


def deduplicate_evidence(evidence: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    """Remove duplicate evidence by identifier, keeping first occurrence."""
    seen: set[str] = set()
    result: list[EvidenceRef] = []
    for item in evidence:
        if item.identifier in seen:
            continue
        seen.add(item.identifier)
        result.append(item)
    return tuple(result)


def sort_evidence(evidence: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    """Order evidence by kind, path, locator, and title."""
    return tuple(
        sorted(
            evidence,
            key=lambda item: (
                EVIDENCE_KINDS.index(item.kind),
                item.source_path.casefold(),
                item.locator.casefold(),
                item.title.casefold(),
                item.identifier,
            ),
        )
    )


def evidence_for_finding(finding: Finding) -> tuple[EvidenceRef, ...]:
    """Return sorted, deduplicated evidence for one finding."""
    return sort_evidence(deduplicate_evidence(finding.evidence))


def with_excerpts(finding: Finding, *, width: int = 240) -> Finding:
    """Fill empty evidence excerpts from evidence content."""
    return replace(
        finding,
        evidence=tuple(
            replace(item, excerpt=item.excerpt or excerpt(item.content, width=width))
            for item in finding.evidence
        ),
    )


def evidence_missing(evidence: Sequence[EvidenceRef]) -> tuple[str, ...]:
    """Return identifiers of evidence with no citable content."""
    return tuple(
        item.identifier
        for item in evidence
        if not item.content.strip() and not item.excerpt.strip()
    )


def evidence_stats(findings: Iterable[Finding]) -> dict[str, int]:
    """Summarize evidence coverage across findings."""
    items = list(findings)
    all_evidence = [item for finding in items for item in finding.evidence]
    return {
        "findings": len(items),
        "findings_with_evidence": sum(1 for finding in items if finding.evidence),
        "evidence": len(all_evidence),
        "sensitive_evidence": sum(1 for item in all_evidence if item.sensitive),
        "notes": sum(1 for item in all_evidence if item.kind == "note"),
        "commands": sum(1 for item in all_evidence if item.kind == "command"),
        "artifacts": sum(1 for item in all_evidence if item.kind == "artifact"),
        "missing": len(evidence_missing(all_evidence)),
    }


def evidence_citations(evidence: Sequence[EvidenceRef]) -> tuple[str, ...]:
    """Return one citation label per evidence item."""
    return tuple(f"[{index}] {item.citation}" for index, item in enumerate(evidence, start=1))


def group_evidence_by_kind(
    evidence: Iterable[EvidenceRef],
) -> dict[str, tuple[EvidenceRef, ...]]:
    """Group evidence by kind in stable order."""
    grouped: dict[str, list[EvidenceRef]] = {kind: [] for kind in EVIDENCE_KINDS}
    for item in evidence:
        grouped[item.kind].append(item)
    return {kind: tuple(items) for kind, items in grouped.items() if items}


def command_evidence(text: str, *, title: str = "Command Log") -> EvidenceRef:
    """Create a command-log evidence item from a block of text."""
    lines = [match.group(1) for match in COMMAND_LINE_RE.finditer(text)]
    return EvidenceRef(
        identifier=f"commands-{digest_text(text)[:10]}",
        title=title,
        content="\n".join(lines) or text,
        kind="command",
        excerpt="\n".join(lines[:8]),
    )
