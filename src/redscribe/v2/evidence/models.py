"""Domain models for the evidence vault.

Evidence models are immutable value objects. Repositories own persistence and
services own state transitions, which keeps the API surface deterministic and
makes manifests straightforward to serialize.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 4_000
MAX_NAME_LENGTH = 255
MAX_TAG_LENGTH = 60
MAX_TAGS = 24
MAX_TEXT_FIELD = 2_000


class EvidenceKind(str, Enum):
    """Broad evidentiary categories used for filtering and icons."""

    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    ARCHIVE = "archive"
    EXECUTABLE = "executable"
    LOG = "log"
    MEMORY_IMAGE = "memory_image"
    NETWORK_CAPTURE = "network_capture"
    DISK_IMAGE = "disk_image"
    OTHER = "other"


class EvidenceStatus(str, Enum):
    """Lifecycle states for one evidence item."""

    DISCOVERED = "discovered"
    ACQUIRED = "acquired"
    ANALYZED = "analyzed"
    VERIFIED = "verified"
    SEALED = "sealed"
    ARCHIVED = "archived"
    DISPOSED = "disposed"


class IntegrityState(str, Enum):
    """Result bucket produced by integrity verification."""

    VERIFIED = "verified"
    MISMATCH = "mismatch"
    MISSING = "missing"
    UNVERIFIED = "unverified"
    ERROR = "error"


class IntegritySeverity(str, Enum):
    """Severity attached to an individual integrity finding."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class CustodyAction(str, Enum):
    """Actions that may appear in the chain of custody."""

    CREATED = "created"
    ACQUIRED = "acquired"
    RECEIVED = "received"
    TRANSFERRED = "transferred"
    ANALYZED = "analyzed"
    COPIED = "copied"
    VERIFIED = "verified"
    SEALED = "sealed"
    RELEASED = "released"
    EXPORTED = "exported"
    IMPORTED = "imported"
    DESTROYED = "destroyed"


class LinkType(str, Enum):
    """Semantic relationship between evidence and a finding."""

    SUPPORTS = "supports"
    REFUTES = "refutes"
    DERIVED_FROM = "derived_from"
    RELATED_TO = "related_to"
    CONTAINS = "contains"
    DUPLICATE_OF = "duplicate_of"


class AcquisitionMethod(str, Enum):
    """How an item was obtained from its source."""

    DIRECT_COPY = "direct_copy"
    FORENSIC_IMAGE = "forensic_image"
    SCREEN_CAPTURE = "screen_capture"
    NETWORK_CAPTURE = "network_capture"
    MANUAL_UPLOAD = "manual_upload"
    EXTERNAL_TOOL = "external_tool"


class RetentionBasis(str, Enum):
    """Reason an item is retained."""

    CASE = "case"
    LEGAL_HOLD = "legal_hold"
    REGULATORY = "regulatory"
    SHORT_TERM = "short_term"
    INDEFINITE = "indefinite"


class DispositionAction(str, Enum):
    """Outcome recommended by a retention review."""

    KEEP = "keep"
    REVIEW = "review"
    ARCHIVE = "archive"
    DESTROY = "destroy"


class MimeSource(str, Enum):
    """Origin of a MIME classification."""

    MAGIC = "magic"
    EXTENSION = "extension"
    DECLARED = "declared"
    TEXT_SNIFF = "text_sniff"
    DEFAULT = "default"


class ManifestFormat(str, Enum):
    """Supported manifest encodings."""

    JSON = "json"
    JSONL = "jsonl"


ALLOWED_STATUS_TRANSITIONS: dict[EvidenceStatus, frozenset[EvidenceStatus]] = {
    EvidenceStatus.DISCOVERED: frozenset(
        {EvidenceStatus.ACQUIRED, EvidenceStatus.ARCHIVED, EvidenceStatus.DISPOSED}
    ),
    EvidenceStatus.ACQUIRED: frozenset(
        {
            EvidenceStatus.ANALYZED,
            EvidenceStatus.VERIFIED,
            EvidenceStatus.SEALED,
            EvidenceStatus.ARCHIVED,
        }
    ),
    EvidenceStatus.ANALYZED: frozenset(
        {EvidenceStatus.VERIFIED, EvidenceStatus.SEALED, EvidenceStatus.ARCHIVED}
    ),
    EvidenceStatus.VERIFIED: frozenset(
        {EvidenceStatus.SEALED, EvidenceStatus.ARCHIVED, EvidenceStatus.ANALYZED}
    ),
    EvidenceStatus.SEALED: frozenset({EvidenceStatus.ARCHIVED}),
    EvidenceStatus.ARCHIVED: frozenset({EvidenceStatus.DISPOSED}),
    EvidenceStatus.DISPOSED: frozenset(),
}

TERMINAL_STATUSES: frozenset[EvidenceStatus] = frozenset({EvidenceStatus.DISPOSED})


def _text(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _integer(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _boolean(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.casefold() in {"1", "true", "yes", "on"}
    return default


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, Sequence):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _enum(value: object, enum_type: type[Enum], default: Enum) -> Any:
    if isinstance(value, enum_type):
        return value
    candidate = _text(value)
    try:
        return enum_type(candidate)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class DigestSet:
    """Cryptographic and compatibility digests for one byte stream."""

    sha256: str
    md5: str
    size_bytes: int
    computed_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "md5": self.md5,
            "size_bytes": self.size_bytes,
            "computed_at": self.computed_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> DigestSet:
        payload = _mapping(value)
        return cls(
            sha256=_text(payload.get("sha256")),
            md5=_text(payload.get("md5")),
            size_bytes=_integer(payload.get("size_bytes")),
            computed_at=_text(payload.get("computed_at")),
        )

    @property
    def display(self) -> str:
        return f"sha256:{self.sha256}"


@dataclass(frozen=True, slots=True)
class MimeInfo:
    """Detected media type and the strength of the detection."""

    mime_type: str
    source: MimeSource
    confidence: float
    extension: str
    category: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "mime_type": self.mime_type,
            "source": self.source.value,
            "confidence": self.confidence,
            "extension": self.extension,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> MimeInfo:
        payload = _mapping(value)
        return cls(
            mime_type=_text(payload.get("mime_type"), "application/octet-stream"),
            source=_enum(payload.get("source"), MimeSource, MimeSource.DEFAULT),
            confidence=_number(payload.get("confidence"), 0.1),
            extension=_text(payload.get("extension")),
            category=_text(payload.get("category"), "other"),
        )


@dataclass(frozen=True, slots=True)
class ThumbnailMetadata:
    """Description of a generated (or unavailable) preview."""

    available: bool
    preview_kind: str
    width: int = 0
    height: int = 0
    page_count: int = 0
    duration_seconds: float = 0.0
    source_sha256: str = ""
    generated_at: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "preview_kind": self.preview_kind,
            "width": self.width,
            "height": self.height,
            "page_count": self.page_count,
            "duration_seconds": self.duration_seconds,
            "source_sha256": self.source_sha256,
            "generated_at": self.generated_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ThumbnailMetadata:
        payload = _mapping(value)
        return cls(
            available=_boolean(payload.get("available")),
            preview_kind=_text(payload.get("preview_kind"), "none"),
            width=_integer(payload.get("width")),
            height=_integer(payload.get("height")),
            page_count=_integer(payload.get("page_count")),
            duration_seconds=_number(payload.get("duration_seconds")),
            source_sha256=_text(payload.get("source_sha256")),
            generated_at=_text(payload.get("generated_at")),
            note=_text(payload.get("note")),
        )


@dataclass(frozen=True, slots=True)
class AcquisitionProvenance:
    """Context captured while acquiring an item."""

    evidence_id: str
    method: AcquisitionMethod
    tool: str
    tool_version: str
    operator: str
    source_path: str
    source_description: str
    acquired_at: str
    case_reference: str
    witness: str
    image_number: int
    notes: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "method": self.method.value,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "operator": self.operator,
            "source_path": self.source_path,
            "source_description": self.source_description,
            "acquired_at": self.acquired_at,
            "case_reference": self.case_reference,
            "witness": self.witness,
            "image_number": self.image_number,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> AcquisitionProvenance:
        payload = _mapping(value)
        return cls(
            evidence_id=_text(payload.get("evidence_id")),
            method=_enum(payload.get("method"), AcquisitionMethod, AcquisitionMethod.MANUAL_UPLOAD),
            tool=_text(payload.get("tool"), "redscribe"),
            tool_version=_text(payload.get("tool_version")),
            operator=_text(payload.get("operator")),
            source_path=_text(payload.get("source_path")),
            source_description=_text(payload.get("source_description")),
            acquired_at=_text(payload.get("acquired_at")),
            case_reference=_text(payload.get("case_reference")),
            witness=_text(payload.get("witness")),
            image_number=_integer(payload.get("image_number")),
            notes=_text(payload.get("notes")),
        )

    def completeness(self) -> float:
        fields = (
            self.tool,
            self.tool_version,
            self.operator,
            self.source_path,
            self.acquired_at,
            self.case_reference,
        )
        filled = sum(1 for item in fields if item.strip())
        return round(filled / len(fields), 3)


@dataclass(frozen=True, slots=True)
class CustodyEvent:
    """One append-only entry in an evidence chain of custody."""

    id: int
    evidence_id: str
    action: CustodyAction
    actor: str
    timestamp: str
    description: str
    location: str
    reference: str
    previous_hash: str
    event_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "evidence_id": self.evidence_id,
            "action": self.action.value,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "description": self.description,
            "location": self.location,
            "reference": self.reference,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CustodyEvent:
        payload = _mapping(value)
        return cls(
            id=_integer(payload.get("id")),
            evidence_id=_text(payload.get("evidence_id")),
            action=_enum(payload.get("action"), CustodyAction, CustodyAction.RECEIVED),
            actor=_text(payload.get("actor")),
            timestamp=_text(payload.get("timestamp")),
            description=_text(payload.get("description")),
            location=_text(payload.get("location")),
            reference=_text(payload.get("reference")),
            previous_hash=_text(payload.get("previous_hash")),
            event_hash=_text(payload.get("event_hash")),
            metadata=_mapping(payload.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class FindingLink:
    """A typed relationship between an evidence item and a finding."""

    id: int
    evidence_id: str
    finding_id: str
    finding_title: str
    link_type: LinkType
    strength: float
    created_at: str
    created_by: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "evidence_id": self.evidence_id,
            "finding_id": self.finding_id,
            "finding_title": self.finding_title,
            "link_type": self.link_type.value,
            "strength": self.strength,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> FindingLink:
        payload = _mapping(value)
        return cls(
            id=_integer(payload.get("id")),
            evidence_id=_text(payload.get("evidence_id")),
            finding_id=_text(payload.get("finding_id")),
            finding_title=_text(payload.get("finding_title")),
            link_type=_enum(payload.get("link_type"), LinkType, LinkType.RELATED_TO),
            strength=_number(payload.get("strength"), 0.5),
            created_at=_text(payload.get("created_at")),
            created_by=_text(payload.get("created_by")),
            note=_text(payload.get("note")),
        )


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """Retention and legal-hold settings for one evidence item."""

    evidence_id: str
    basis: RetentionBasis
    retain_days: int
    retain_until: str
    legal_hold: bool
    review_at: str
    disposition: DispositionAction
    updated_at: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "basis": self.basis.value,
            "retain_days": self.retain_days,
            "retain_until": self.retain_until,
            "legal_hold": self.legal_hold,
            "review_at": self.review_at,
            "disposition": self.disposition.value,
            "updated_at": self.updated_at,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RetentionPolicy:
        payload = _mapping(value)
        return cls(
            evidence_id=_text(payload.get("evidence_id")),
            basis=_enum(payload.get("basis"), RetentionBasis, RetentionBasis.CASE),
            retain_days=_integer(payload.get("retain_days"), 365),
            retain_until=_text(payload.get("retain_until")),
            legal_hold=_boolean(payload.get("legal_hold")),
            review_at=_text(payload.get("review_at")),
            disposition=_enum(
                payload.get("disposition"), DispositionAction, DispositionAction.KEEP
            ),
            updated_at=_text(payload.get("updated_at")),
            reason=_text(payload.get("reason")),
        )


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """The canonical description of one acquired evidence item."""

    id: str
    title: str
    description: str
    kind: EvidenceKind
    status: EvidenceStatus
    original_filename: str
    stored_path: str
    mime: MimeInfo
    digests: DigestSet
    thumbnail: ThumbnailMetadata
    provenance: AcquisitionProvenance
    tags: tuple[str, ...]
    note_id: int | None
    created_at: str
    updated_at: str
    acquired_at: str
    custom_fields: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "kind": self.kind.value,
            "status": self.status.value,
            "original_filename": self.original_filename,
            "stored_path": self.stored_path,
            "mime": self.mime.as_dict(),
            "digests": self.digests.as_dict(),
            "thumbnail": self.thumbnail.as_dict(),
            "provenance": self.provenance.as_dict(),
            "tags": list(self.tags),
            "note_id": self.note_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "acquired_at": self.acquired_at,
            "custom_fields": dict(self.custom_fields),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> EvidenceRecord:
        payload = _mapping(value)
        raw_note_id = payload.get("note_id")
        valid_note_id = isinstance(raw_note_id, int) and not isinstance(raw_note_id, bool)
        note_id = raw_note_id if valid_note_id else None
        provenance = payload.get("provenance")
        evidence_id = _text(payload.get("id"))
        return cls(
            id=evidence_id,
            title=_text(payload.get("title"), "Untitled evidence"),
            description=_text(payload.get("description")),
            kind=_enum(payload.get("kind"), EvidenceKind, EvidenceKind.OTHER),
            status=_enum(payload.get("status"), EvidenceStatus, EvidenceStatus.DISCOVERED),
            original_filename=_text(payload.get("original_filename")),
            stored_path=_text(payload.get("stored_path")),
            mime=MimeInfo.from_dict(payload.get("mime") or {}),
            digests=DigestSet.from_dict(payload.get("digests") or {}),
            thumbnail=ThumbnailMetadata.from_dict(payload.get("thumbnail") or {}),
            provenance=(
                AcquisitionProvenance.from_dict(provenance)
                if isinstance(provenance, Mapping)
                else AcquisitionProvenance(
                    evidence_id=evidence_id,
                    method=AcquisitionMethod.MANUAL_UPLOAD,
                    tool="redscribe",
                    tool_version="",
                    operator="",
                    source_path="",
                    source_description="",
                    acquired_at=_text(payload.get("acquired_at")),
                    case_reference="",
                    witness="",
                    image_number=0,
                    notes="",
                )
            ),
            tags=_strings(payload.get("tags")),
            note_id=note_id,
            created_at=_text(payload.get("created_at")),
            updated_at=_text(payload.get("updated_at")),
            acquired_at=_text(payload.get("acquired_at")),
            custom_fields=_mapping(payload.get("custom_fields")),
        )

    @property
    def sha256(self) -> str:
        return self.digests.sha256

    @property
    def md5(self) -> str:
        return self.digests.md5

    @property
    def size_bytes(self) -> int:
        return self.digests.size_bytes

    def search_text(self) -> str:
        parts = (
            self.id,
            self.title,
            self.description,
            self.original_filename,
            self.mime.mime_type,
            self.digests.sha256,
            self.digests.md5,
            " ".join(self.tags),
            self.provenance.operator,
            self.provenance.case_reference,
        )
        return " ".join(parts).casefold()

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind.value,
            "status": self.status.value,
            "original_filename": self.original_filename,
            "mime_type": self.mime.mime_type,
            "sha256": self.sha256,
            "md5": self.md5,
            "size_bytes": self.size_bytes,
            "tags": list(self.tags),
            "note_id": self.note_id,
            "preview_kind": self.thumbnail.preview_kind,
            "has_thumbnail": self.thumbnail.available,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def detail(self) -> dict[str, Any]:
        payload = self.as_dict()
        payload["search_text"] = self.search_text()
        return payload


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    """One specific integrity problem found during verification."""

    code: str
    severity: IntegritySeverity
    message: str
    field: str = ""
    expected: str = ""
    actual: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "field": self.field,
            "expected": self.expected,
            "actual": self.actual,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> IntegrityIssue:
        payload = _mapping(value)
        return cls(
            code=_text(payload.get("code"), "unknown"),
            severity=_enum(payload.get("severity"), IntegritySeverity, IntegritySeverity.WARNING),
            message=_text(payload.get("message")),
            field=_text(payload.get("field")),
            expected=_text(payload.get("expected")),
            actual=_text(payload.get("actual")),
        )


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    """Aggregated verification result for one item or the whole vault."""

    evidence_id: str
    state: IntegrityState
    checked_at: str
    digest_match: bool
    custody_valid: bool
    manifest_match: bool
    issues: tuple[IntegrityIssue, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "state": self.state.value,
            "checked_at": self.checked_at,
            "digest_match": self.digest_match,
            "custody_valid": self.custody_valid,
            "manifest_match": self.manifest_match,
            "issues": [issue.as_dict() for issue in self.issues],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> IntegrityReport:
        payload = _mapping(value)
        raw_issues = payload.get("issues")
        issues = (
            tuple(
                IntegrityIssue.from_dict(item) for item in raw_issues if isinstance(item, Mapping)
            )
            if isinstance(raw_issues, Sequence)
            else ()
        )
        return cls(
            evidence_id=_text(payload.get("evidence_id")),
            state=_enum(payload.get("state"), IntegrityState, IntegrityState.UNVERIFIED),
            checked_at=_text(payload.get("checked_at")),
            digest_match=_boolean(payload.get("digest_match")),
            custody_valid=_boolean(payload.get("custody_valid")),
            manifest_match=_boolean(payload.get("manifest_match")),
            issues=issues,
        )

    @property
    def is_verified(self) -> bool:
        return self.state is IntegrityState.VERIFIED

    @property
    def critical_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity is IntegritySeverity.CRITICAL)


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """One row in an evidence manifest."""

    evidence_id: str
    filename: str
    sha256: str
    md5: str
    size_bytes: int
    stored_path: str
    kind: str
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "filename": self.filename,
            "sha256": self.sha256,
            "md5": self.md5,
            "size_bytes": self.size_bytes,
            "stored_path": self.stored_path,
            "kind": self.kind,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ManifestEntry:
        payload = _mapping(value)
        return cls(
            evidence_id=_text(payload.get("evidence_id")),
            filename=_text(payload.get("filename")),
            sha256=_text(payload.get("sha256")),
            md5=_text(payload.get("md5")),
            size_bytes=_integer(payload.get("size_bytes")),
            stored_path=_text(payload.get("stored_path")),
            kind=_text(payload.get("kind"), "other"),
            status=_text(payload.get("status"), "discovered"),
        )


@dataclass(frozen=True, slots=True)
class EvidenceManifest:
    """A portable, checksummed snapshot of evidence metadata."""

    version: int
    generated_at: str
    generator: str
    case_reference: str
    records: tuple[dict[str, Any], ...]
    entries: tuple[ManifestEntry, ...]
    custody: tuple[dict[str, Any], ...]
    links: tuple[dict[str, Any], ...]
    retention: tuple[dict[str, Any], ...]
    checksum: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": ManifestFormat.JSON.value,
            "version": self.version,
            "generated_at": self.generated_at,
            "generator": self.generator,
            "case_reference": self.case_reference,
            "records": [dict(record) for record in self.records],
            "entries": [entry.as_dict() for entry in self.entries],
            "custody": [dict(event) for event in self.custody],
            "links": [dict(link) for link in self.links],
            "retention": [dict(policy) for policy in self.retention],
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> EvidenceManifest:
        payload = _mapping(value)
        entries = payload.get("entries")
        return cls(
            version=_integer(payload.get("version"), 1),
            generated_at=_text(payload.get("generated_at")),
            generator=_text(payload.get("generator"), "redscribe"),
            case_reference=_text(payload.get("case_reference")),
            records=tuple(
                _mapping(item) for item in payload.get("records", []) if isinstance(item, Mapping)
            ),
            entries=tuple(
                ManifestEntry.from_dict(item) for item in entries if isinstance(item, Mapping)
            )
            if isinstance(entries, Sequence)
            else (),
            custody=tuple(
                _mapping(item) for item in payload.get("custody", []) if isinstance(item, Mapping)
            ),
            links=tuple(
                _mapping(item) for item in payload.get("links", []) if isinstance(item, Mapping)
            ),
            retention=tuple(
                _mapping(item) for item in payload.get("retention", []) if isinstance(item, Mapping)
            ),
            checksum=_text(payload.get("checksum")),
        )

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(entry.evidence_id for entry in self.entries)


@dataclass(frozen=True, slots=True)
class ImportPlan:
    """Decision record for one imported manifest."""

    strategy: str
    create: tuple[str, ...]
    update: tuple[str, ...]
    skip: tuple[str, ...]
    conflicts: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "create": list(self.create),
            "update": list(self.update),
            "skip": list(self.skip),
            "conflicts": list(self.conflicts),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class RetentionDecision:
    """Recommendation produced by a retention review."""

    evidence_id: str
    action: DispositionAction
    reason: str
    days_remaining: int
    legal_hold: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "action": self.action.value,
            "reason": self.reason,
            "days_remaining": self.days_remaining,
            "legal_hold": self.legal_hold,
        }


@dataclass(frozen=True, slots=True)
class EvidenceStats:
    """Aggregate counters for the evidence feature."""

    total: int
    by_status: dict[str, int]
    by_kind: dict[str, int]
    total_bytes: int
    verified: int
    alerts: int
    custody_events: int
    links: int
    legal_holds: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "by_status": dict(self.by_status),
            "by_kind": dict(self.by_kind),
            "total_bytes": self.total_bytes,
            "verified": self.verified,
            "alerts": self.alerts,
            "custody_events": self.custody_events,
            "links": self.links,
            "legal_holds": self.legal_holds,
        }
