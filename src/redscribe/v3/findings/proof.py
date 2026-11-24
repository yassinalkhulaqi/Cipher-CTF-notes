"""Proof-block integrity and EntityRef link helpers for findings."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from redscribe.v3.entities.links import LinkGraph
from redscribe.v3.entities.types import (
    EntityId,
    EntityKind,
    EntityLink,
    EntityRef,
    LinkKind,
)
from redscribe.v3.findings.models import (
    Finding,
    ProofBlock,
    ProofRole,
    hash_excerpt,
)

ALLOWED_PROOF_KINDS: tuple[EntityKind, ...] = (
    EntityKind.EVIDENCE,
    EntityKind.NOTE,
    EntityKind.SECTION,
)


class ProofError(ValueError):
    """Raised when a proof link is malformed or cannot be verified."""


@dataclass(frozen=True, slots=True)
class ProofIssue:
    """A single integrity problem found in a proof chain."""

    block_id: str
    code: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-safe representation."""
        return {"block_id": self.block_id, "code": self.code, "detail": self.detail}


def validate_ref(ref: EntityRef) -> None:
    """Ensure a proof reference points at an allowed entity kind."""
    if ref.kind not in ALLOWED_PROOF_KINDS:
        raise ProofError(
            "Proof blocks may only link evidence, note, or section entities, got " + ref.kind.value
        )


def make_proof(
    block_id: str,
    ref: EntityRef,
    *,
    excerpt: str = "",
    role: ProofRole = ProofRole.SUPPORTING,
    captured_at: float = 0.0,
    label: str = "",
    metadata: dict[str, Any] | None = None,
) -> ProofBlock:
    """Build a proof block with a content hash for tamper detection."""
    validate_ref(ref)
    return ProofBlock(
        block_id=block_id,
        ref=ref,
        role=role,
        excerpt=excerpt,
        content_hash=hash_excerpt(excerpt) if excerpt else "",
        captured_at=captured_at,
        label=label,
        metadata=dict(metadata or {}),
    )


def proof_link(finding: Finding, block: ProofBlock) -> EntityLink:
    """Create the typed graph edge represented by a proof block."""
    validate_ref(block.ref)
    return EntityLink(
        source=finding.entity_id,
        target=block.ref.entity_id,
        kind=LinkKind.EVIDENCES,
        label=block.role.value,
        weight=1.0,
        metadata={"block_id": block.block_id, "hash": block.content_hash},
    )


def add_proof_block(finding: Finding, block: ProofBlock, *, timestamp: float) -> Finding:
    """Attach a proof block to a finding and bump its version."""
    existing = {item.block_id for item in finding.proof_blocks}
    if block.block_id in existing:
        raise ProofError(f"Duplicate proof block id: {block.block_id}")
    return finding.evolve(
        proof_blocks=(*finding.proof_blocks, block),
        updated_at=timestamp,
    )


def proof_blocks_for(finding: Finding, role: ProofRole | None = None) -> tuple[ProofBlock, ...]:
    """Return proof blocks, optionally filtered by role."""
    if role is None:
        return finding.proof_blocks
    return tuple(block for block in finding.proof_blocks if block.role is role)


def proof_targets(finding: Finding) -> tuple[EntityRef, ...]:
    """Return unique entity references linked by proof blocks."""
    seen: set[str] = set()
    refs: list[EntityRef] = []
    for block in finding.proof_blocks:
        if block.target in seen:
            continue
        seen.add(block.target)
        refs.append(block.ref)
    return tuple(refs)


def verify_chain(finding: Finding) -> tuple[ProofIssue, ...]:
    """Check every proof block for structural and content integrity."""
    issues: list[ProofIssue] = []
    ids: set[str] = set()
    for block in finding.proof_blocks:
        if block.block_id in ids:
            issues.append(ProofIssue(block.block_id, "duplicate_id", "Proof block id is repeated"))
        ids.add(block.block_id)
        if block.ref.kind not in ALLOWED_PROOF_KINDS:
            issues.append(
                ProofIssue(
                    block.block_id, "invalid_kind", f"Kind {block.ref.kind.value} is not allowed"
                )
            )
        if not block.excerpt:
            issues.append(ProofIssue(block.block_id, "empty_excerpt", "Proof excerpt is empty"))
        elif not block.verified:
            issues.append(
                ProofIssue(block.block_id, "hash_mismatch", "Content hash does not match excerpt")
            )
    return tuple(issues)


def reconcile_links(
    graph: LinkGraph,
    findings: Iterable[Finding],
) -> tuple[int, int]:
    """Count evidence links present and expected for a set of findings.

    The caller owns link insertion into :class:`EntityService`; this helper is a
    read-only consistency check used by the API and tests.
    """
    expected = 0
    present = 0
    existing = {link.key for link in graph.links()}
    for finding in findings:
        for block in finding.proof_blocks:
            expected += 1
            key = (
                str(finding.entity_id),
                str(block.ref.entity_id),
                LinkKind.EVIDENCES.value,
            )
            if key in existing:
                present += 1
    return present, expected


def proof_ref_from_node(node: EntityId, label: str = "") -> EntityRef:
    """Build a proof reference from any entity id (kind checked by validate_ref)."""
    return EntityRef(node, label)


def proof_summary(finding: Finding) -> dict[str, Any]:
    """Return a UI-ready proof summary."""
    issues = verify_chain(finding)
    return {
        "total": len(finding.proof_blocks),
        "verified": finding.verified_proof_count,
        "supporting": len(proof_blocks_for(finding, ProofRole.SUPPORTING)),
        "contradicting": len(proof_blocks_for(finding, ProofRole.CONTRADICTING)),
        "context": len(proof_blocks_for(finding, ProofRole.CONTEXT)),
        "targets": [str(ref) for ref in proof_targets(finding)],
        "issues": [issue.as_dict() for issue in issues],
        "integrity": not issues,
    }
