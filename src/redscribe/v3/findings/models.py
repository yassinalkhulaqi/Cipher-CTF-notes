"""Immutable domain models for the V3 finding studio."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from redscribe.v3.entities.types import EntityId, EntityKind, EntityRef
from redscribe.v3.findings.cvss_v4 import (
    SeverityBand,
    cvss_v4_score,
    cvss_v4_severity,
)

_CWE_PATTERN = re.compile(r"^CWE-\d{1,6}$")
_CVE_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,7}$")
_HEX_PATTERN = re.compile(r"^[0-9a-f]{8,128}$")


class FindingState(str, Enum):
    """The five lifecycle states of a first-class finding."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    REMEDIATED = "remediated"
    RETESTED = "retested"
    CLOSED = "closed"

    @classmethod
    def parse(cls, value: str) -> FindingState:
        """Parse a state string with a stable error message."""
        normalized = value.strip().casefold()
        for state in cls:
            if state.value == normalized:
                return state
        raise ValueError(f"Unknown finding state: {value}")

    @property
    def is_open(self) -> bool:
        """Whether the finding still needs work."""
        return self not in (FindingState.CLOSED,)

    @property
    def rank(self) -> int:
        """Numeric lifecycle ordering."""
        return list(FindingState).index(self)


class ProofRole(str, Enum):
    """Why a proof block is attached to a finding."""

    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    CONTEXT = "context"

    @classmethod
    def parse(cls, value: str) -> ProofRole:
        """Parse a proof role string."""
        normalized = value.strip().casefold()
        for role in cls:
            if role.value == normalized:
                return role
        raise ValueError(f"Unknown proof role: {value}")


class TaskStatus(str, Enum):
    """Status of one remediation checklist item."""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SKIPPED = "skipped"

    @classmethod
    def parse(cls, value: str) -> TaskStatus:
        """Parse a task status string."""
        normalized = value.strip().casefold()
        for status in cls:
            if status.value == normalized:
                return status
        raise ValueError(f"Unknown task status: {value}")

    @property
    def is_settled(self) -> bool:
        """Whether the task no longer blocks remediation."""
        return self in (TaskStatus.DONE, TaskStatus.SKIPPED)


class RetestVerdict(str, Enum):
    """Outcome of a retest against a remediated finding."""

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"

    @classmethod
    def parse(cls, value: str) -> RetestVerdict:
        """Parse a retest verdict string."""
        normalized = value.strip().casefold()
        for verdict in cls:
            if verdict.value == normalized:
                return verdict
        raise ValueError(f"Unknown retest verdict: {value}")


def finding_id(value: str) -> EntityId:
    """Build a finding EntityId, validating the raw value."""
    return EntityId(EntityKind.FINDING, value)


def parse_finding_ref(raw: str) -> EntityId:
    """Parse a canonical ``finding:...`` reference."""
    parsed = EntityId.parse(raw)
    if parsed.kind is not EntityKind.FINDING:
        raise ValueError(f"Not a finding reference: {raw}")
    return parsed


def _validate_cwe(value: str) -> str:
    normalized = value.strip().upper()
    if not _CWE_PATTERN.match(normalized):
        raise ValueError(f"Invalid CWE identifier: {value}")
    return normalized


def _validate_cve(value: str) -> str:
    normalized = value.strip().upper()
    if not _CVE_PATTERN.match(normalized):
        raise ValueError(f"Invalid CVE identifier: {value}")
    return normalized


@dataclass(frozen=True, slots=True)
class CweMapping:
    """CWE catalog entry with remediation and framework mappings."""

    cwe_id: str
    name: str
    category: str
    description: str = ""
    owasp: tuple[str, ...] = ()
    capec: tuple[str, ...] = ()
    mitigations: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "cwe_id", _validate_cwe(self.cwe_id))
        if not self.name.strip():
            raise ValueError("CWE name cannot be blank")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "cwe_id": self.cwe_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "owasp": list(self.owasp),
            "capec": list(self.capec),
            "mitigations": list(self.mitigations),
            "references": list(self.references),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class FindingMappings:
    """Weakness and framework metadata attached to a finding."""

    cwes: tuple[str, ...] = ()
    cves: tuple[str, ...] = ()
    owasp: tuple[str, ...] = ()
    capec: tuple[str, ...] = ()
    mitre_attack: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "cwes", tuple(_validate_cwe(value) for value in self.cwes))
        object.__setattr__(self, "cves", tuple(_validate_cve(value) for value in self.cves))

    @property
    def primary_cwe(self) -> str:
        """First CWE, or an empty string."""
        return self.cwes[0] if self.cwes else ""

    def merge(self, other: FindingMappings) -> FindingMappings:
        """Return the union of two mapping sets."""
        return FindingMappings(
            cwes=tuple(dict.fromkeys((*self.cwes, *other.cwes))),
            cves=tuple(dict.fromkeys((*self.cves, *other.cves))),
            owasp=tuple(dict.fromkeys((*self.owasp, *other.owasp))),
            capec=tuple(dict.fromkeys((*self.capec, *other.capec))),
            mitre_attack=tuple(dict.fromkeys((*self.mitre_attack, *other.mitre_attack))),
            notes=other.notes or self.notes,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "cwes": list(self.cwes),
            "cves": list(self.cves),
            "owasp": list(self.owasp),
            "capec": list(self.capec),
            "mitre_attack": list(self.mitre_attack),
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ProofBlock:
    """An immutable, verifiable link from a finding to another entity."""

    block_id: str
    ref: EntityRef
    role: ProofRole = ProofRole.SUPPORTING
    excerpt: str = ""
    content_hash: str = ""
    captured_at: float = 0.0
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.block_id.strip() or len(self.block_id) > 120:
            raise ValueError("Proof block id must be 1-120 characters")
        if self.ref.kind not in (EntityKind.EVIDENCE, EntityKind.NOTE, EntityKind.SECTION):
            raise ValueError("Proof blocks must reference evidence, note, or section entities")
        if self.content_hash and not _HEX_PATTERN.match(self.content_hash):
            raise ValueError("Proof block hash must be a hex digest")
        if len(self.excerpt) > 8000:
            raise ValueError("Proof excerpt is too long")

    @property
    def target(self) -> str:
        """Canonical reference string of the linked entity."""
        return str(self.ref)

    @property
    def verified(self) -> bool:
        """Whether the stored hash matches the excerpt."""
        if not self.content_hash:
            return False
        return self.content_hash == hash_excerpt(self.excerpt)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "block_id": self.block_id,
            "ref": self.ref.as_dict(),
            "role": self.role.value,
            "excerpt": self.excerpt,
            "content_hash": self.content_hash,
            "captured_at": self.captured_at,
            "label": self.label,
            "verified": self.verified,
            "metadata": dict(self.metadata),
        }


def hash_excerpt(excerpt: str) -> str:
    """Hash a proof excerpt for tamper detection."""
    return hashlib.blake2b(excerpt.encode("utf-8"), digest_size=16).hexdigest()


@dataclass(frozen=True, slots=True)
class RemediationTask:
    """One item on a finding's remediation checklist."""

    task_id: str
    title: str
    detail: str = ""
    owner: str = ""
    status: TaskStatus = TaskStatus.TODO
    due_at: float = 0.0
    completed_at: float = 0.0
    proof_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_id.strip() or len(self.task_id) > 120:
            raise ValueError("Remediation task id must be 1-120 characters")
        if not self.title.strip():
            raise ValueError("Remediation task title cannot be blank")
        if len(self.title) > 240:
            raise ValueError("Remediation task title is too long")

    def with_status(
        self, status: TaskStatus, timestamp: float, proof_ref: str = ""
    ) -> RemediationTask:
        """Return a new task with an updated status."""
        proof_refs = self.proof_refs
        if proof_ref and proof_ref not in proof_refs:
            proof_refs = (*proof_refs, proof_ref)
        return replace(
            self,
            status=status,
            completed_at=timestamp if status.is_settled else 0.0,
            proof_refs=proof_refs,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "detail": self.detail,
            "owner": self.owner,
            "status": self.status.value,
            "due_at": self.due_at,
            "completed_at": self.completed_at,
            "proof_refs": list(self.proof_refs),
        }


@dataclass(frozen=True, slots=True)
class RetestRecord:
    """Evidence-backed retest of a remediated finding."""

    retest_id: str
    verdict: RetestVerdict
    tested_by: str
    timestamp: float
    notes: str = ""
    proof_refs: tuple[str, ...] = ()
    follow_up: str = ""

    def __post_init__(self) -> None:
        if not self.retest_id.strip() or len(self.retest_id) > 120:
            raise ValueError("Retest id must be 1-120 characters")
        if not self.tested_by.strip():
            raise ValueError("Retest actor cannot be blank")

    @property
    def passed(self) -> bool:
        """Whether the retest fully passed."""
        return self.verdict is RetestVerdict.PASS

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "retest_id": self.retest_id,
            "verdict": self.verdict.value,
            "tested_by": self.tested_by,
            "timestamp": self.timestamp,
            "notes": self.notes,
            "proof_refs": list(self.proof_refs),
            "follow_up": self.follow_up,
        }


@dataclass(frozen=True, slots=True)
class TransitionRecord:
    """One immutable lifecycle transition."""

    action: str
    source: FindingState
    target: FindingState
    actor: str
    timestamp: float
    note: str = ""
    retest_id: str = ""

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("Transition action cannot be blank")
        if not self.actor.strip():
            raise ValueError("Transition actor cannot be blank")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "action": self.action,
            "source": self.source.value,
            "target": self.target.value,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "note": self.note,
            "retest_id": self.retest_id,
        }


@dataclass(frozen=True, slots=True)
class Finding:
    """An immutable, versioned finding snapshot."""

    entity_id: EntityId
    title: str
    summary: str = ""
    state: FindingState = FindingState.DRAFT
    vector: str = ""
    owner: str = ""
    target_ref: EntityRef | None = None
    mappings: FindingMappings = field(default_factory=FindingMappings)
    proof_blocks: tuple[ProofBlock, ...] = ()
    remediation: tuple[RemediationTask, ...] = ()
    retests: tuple[RetestRecord, ...] = ()
    history: tuple[TransitionRecord, ...] = ()
    duplicate_of: EntityId | None = None
    tags: tuple[str, ...] = ()
    created_at: float = 0.0
    updated_at: float = 0.0
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.entity_id.kind is not EntityKind.FINDING:
            raise ValueError("Finding entity id must have kind 'finding'")
        if not self.title.strip():
            raise ValueError("Finding title cannot be blank")
        if len(self.title) > 240:
            raise ValueError("Finding title is too long")
        if self.version < 1:
            raise ValueError("Finding version must be at least 1")
        if self.vector:
            cvss_v4_score(self.vector)

    @property
    def ref(self) -> EntityRef:
        """Entity reference for this finding."""
        return EntityRef(self.entity_id, self.title)

    @property
    def ref_string(self) -> str:
        """Canonical reference string."""
        return str(self.entity_id)

    @property
    def score(self) -> float:
        """Final CVSS v4 score, or zero when unscored."""
        return cvss_v4_score(self.vector) if self.vector else 0.0

    @property
    def severity(self) -> SeverityBand:
        """Severity band derived from the vector or an explicit override."""
        override = self.metadata.get("severity_override", "")
        if override:
            return SeverityBand(override)
        return cvss_v4_severity(self.vector) if self.vector else SeverityBand.NONE

    @property
    def is_open(self) -> bool:
        """Whether this finding is still in an open lifecycle state."""
        return self.state.is_open and self.duplicate_of is None

    @property
    def latest_retest(self) -> RetestRecord | None:
        """Most recently recorded retest."""
        return self.retests[-1] if self.retests else None

    @property
    def remediation_progress(self) -> float:
        """Fraction of settled remediation tasks in the 0..1 range."""
        if not self.remediation:
            return 0.0
        settled = sum(1 for task in self.remediation if task.status.is_settled)
        return round(settled / len(self.remediation), 4)

    @property
    def verified_proof_count(self) -> int:
        """Number of proof blocks whose excerpt hash verifies."""
        return sum(1 for block in self.proof_blocks if block.verified)

    def evolve(self, **changes: Any) -> Finding:
        """Return a new version with the supplied field replacements."""
        allowed = {
            "title",
            "summary",
            "state",
            "vector",
            "owner",
            "target_ref",
            "mappings",
            "proof_blocks",
            "remediation",
            "retests",
            "history",
            "duplicate_of",
            "tags",
            "metadata",
            "updated_at",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unknown finding fields: {', '.join(sorted(unknown))}")
        updated = replace(self, **changes)
        return replace(updated, version=self.version + 1)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for the API and persistence."""
        return {
            "ref": self.ref_string,
            "title": self.title,
            "summary": self.summary,
            "state": self.state.value,
            "vector": self.vector,
            "score": self.score,
            "severity": self.severity.value,
            "owner": self.owner,
            "target_ref": self.target_ref.as_dict() if self.target_ref else None,
            "mappings": self.mappings.as_dict(),
            "proof_blocks": [block.as_dict() for block in self.proof_blocks],
            "remediation": [task.as_dict() for task in self.remediation],
            "retests": [retest.as_dict() for retest in self.retests],
            "history": [record.as_dict() for record in self.history],
            "duplicate_of": str(self.duplicate_of) if self.duplicate_of else "",
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "is_open": self.is_open,
            "remediation_progress": self.remediation_progress,
            "metadata": dict(self.metadata),
        }
