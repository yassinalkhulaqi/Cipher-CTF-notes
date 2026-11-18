"""Evidence record construction, updates, filtering, and validation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from redscribe.domain.utils import slug_hash
from redscribe.v2.evidence.errors import ConflictError, ValidationError
from redscribe.v2.evidence.mime import evidence_kind_for_mime, normalize_mime
from redscribe.v2.evidence.models import (
    ALLOWED_STATUS_TRANSITIONS,
    MAX_NAME_LENGTH,
    MAX_TITLE_LENGTH,
    TERMINAL_STATUSES,
    AcquisitionMethod,
    AcquisitionProvenance,
    DigestSet,
    EvidenceKind,
    EvidenceRecord,
    EvidenceStatus,
    MimeInfo,
    ThumbnailMetadata,
)
from redscribe.v2.evidence.validation import (
    normalize_metadata,
    normalize_tags,
    now_iso,
    sanitize_filename,
    validate_evidence_id,
    validate_hex_digest,
)

UNSET: object = object()

SORT_FIELDS = ("created_at", "updated_at", "title", "size_bytes", "status", "kind")
SORT_DIRECTIONS = ("asc", "desc")


def generate_evidence_id(seed: str, *, existing: Iterable[str] = ()) -> str:
    """Return a stable evidence id derived from a seed and collision counter."""
    base = slug_hash(seed or "evidence", length=10)
    taken = set(existing)
    candidate = f"ev_{base}"
    counter = 2
    while candidate in taken:
        suffix = f"{counter:x}"
        candidate = f"ev_{slug_hash(seed + suffix, length=10)}"
        counter += 1
        if counter > 1_000:
            raise ValidationError("Unable to allocate a unique evidence id")
    return candidate


def default_provenance(evidence_id: str, *, acquired_at: str = "") -> AcquisitionProvenance:
    """Return the minimal provenance attached to a new record."""
    return AcquisitionProvenance(
        evidence_id=evidence_id,
        method=AcquisitionMethod.MANUAL_UPLOAD,
        tool="redscribe",
        tool_version="",
        operator="",
        source_path="",
        source_description="",
        acquired_at=acquired_at or now_iso(),
        case_reference="",
        witness="",
        image_number=0,
        notes="",
    )


def build_record(
    *,
    evidence_id: str,
    title: str,
    digests: DigestSet,
    mime: MimeInfo,
    description: str = "",
    kind: EvidenceKind | None = None,
    status: EvidenceStatus = EvidenceStatus.DISCOVERED,
    original_filename: str = "",
    stored_path: str = "",
    thumbnail: ThumbnailMetadata | None = None,
    provenance: AcquisitionProvenance | None = None,
    tags: Sequence[str] | str = (),
    note_id: int | None = None,
    custom_fields: Mapping[str, Any] | None = None,
    created_at: str = "",
    acquired_at: str = "",
) -> EvidenceRecord:
    """Construct and validate a new evidence record."""
    record_id = validate_evidence_id(evidence_id)
    clean_title = title.strip() or original_filename or "Untitled evidence"
    if len(clean_title) > MAX_TITLE_LENGTH:
        clean_title = clean_title[:MAX_TITLE_LENGTH]
    timestamp = created_at or now_iso()
    resolved_kind = kind or mime_kind(mime, original_filename)
    return EvidenceRecord(
        id=record_id,
        title=clean_title,
        description=description[:4_000],
        kind=resolved_kind,
        status=status,
        original_filename=original_filename[:MAX_NAME_LENGTH],
        stored_path=stored_path,
        mime=mime,
        digests=digests,
        thumbnail=thumbnail or ThumbnailMetadata(available=False, preview_kind="icon"),
        provenance=provenance or default_provenance(record_id, acquired_at=acquired_at),
        tags=normalize_tags(tags),
        note_id=note_id,
        created_at=timestamp,
        updated_at=timestamp,
        acquired_at=acquired_at or timestamp,
        custom_fields=normalize_metadata(custom_fields),
    )


def mime_kind(mime: MimeInfo, filename: str = "") -> EvidenceKind:
    """Choose an evidence kind using MIME data and the original filename."""
    normalized = normalize_mime(mime.mime_type)
    if normalized == "text/plain" and filename.casefold().endswith((".log", ".jsonl")):
        return EvidenceKind.LOG
    if normalized == "application/octet-stream" and filename.casefold().endswith(
        (".img", ".dd", ".raw", ".001")
    ):
        return EvidenceKind.DISK_IMAGE
    return evidence_kind_for_mime(normalized)


def apply_update(
    record: EvidenceRecord,
    *,
    title: object = UNSET,
    description: object = UNSET,
    kind: object = UNSET,
    status: object = UNSET,
    original_filename: object = UNSET,
    tags: object = UNSET,
    note_id: object = UNSET,
    custom_fields: object = UNSET,
    stored_path: object = UNSET,
    updated_at: str = "",
) -> EvidenceRecord:
    """Return a new record with validated field updates applied."""
    changes: dict[str, Any] = {}
    if title is not UNSET:
        if not isinstance(title, str) or not title.strip():
            raise ValidationError("'title' must not be empty", details={"field": "title"})
        changes["title"] = title.strip()[:MAX_TITLE_LENGTH]
    if description is not UNSET:
        if description is None:
            changes["description"] = ""
        elif isinstance(description, str):
            changes["description"] = description.strip()[:4_000]
        else:
            raise ValidationError(
                "'description' must be a string", details={"field": "description"}
            )
    if kind is not UNSET:
        if not isinstance(kind, EvidenceKind):
            raise ValidationError("'kind' must be an evidence kind", details={"field": "kind"})
        changes["kind"] = kind
    if status is not UNSET:
        if not isinstance(status, EvidenceStatus):
            raise ValidationError(
                "'status' must be an evidence status", details={"field": "status"}
            )
        changes["status"] = status
    if original_filename is not UNSET:
        if not isinstance(original_filename, str):
            raise ValidationError(
                "'original_filename' must be a string", details={"field": "original_filename"}
            )
        changes["original_filename"] = sanitize_filename(original_filename)
    if tags is not UNSET:
        changes["tags"] = normalize_tags(tags)
    if note_id is not UNSET:
        if note_id is None:
            changes["note_id"] = None
        elif isinstance(note_id, int) and not isinstance(note_id, bool) and note_id > 0:
            changes["note_id"] = note_id
        else:
            raise ValidationError(
                "'note_id' must be a positive integer", details={"field": "note_id"}
            )
    if custom_fields is not UNSET:
        changes["custom_fields"] = normalize_metadata(custom_fields)
    if stored_path is not UNSET:
        if not isinstance(stored_path, str):
            raise ValidationError(
                "'stored_path' must be a string", details={"field": "stored_path"}
            )
        changes["stored_path"] = stored_path
    if not changes:
        return record
    payload = record.as_dict()
    payload.update(
        {key: value.value if hasattr(value, "value") else value for key, value in changes.items()}
    )
    payload["tags"] = list(changes.get("tags", record.tags))
    payload["updated_at"] = updated_at or now_iso()
    return EvidenceRecord.from_dict(payload)


def transition_status(
    record: EvidenceRecord,
    target: EvidenceStatus,
    *,
    timestamp: str = "",
    force: bool = False,
) -> EvidenceRecord:
    """Move a record to a new lifecycle state when the transition is legal."""
    if target is record.status:
        return record
    if record.status in TERMINAL_STATUSES:
        raise ConflictError(
            f"Cannot transition a disposed evidence item to {target.value}",
            details={"from": record.status.value, "to": target.value},
        )
    allowed = ALLOWED_STATUS_TRANSITIONS.get(record.status, frozenset())
    if target not in allowed and not force:
        raise ConflictError(
            f"Cannot transition {record.status.value} to {target.value}",
            details={
                "from": record.status.value,
                "to": target.value,
                "allowed": sorted(item.value for item in allowed),
            },
        )
    return apply_update(record, status=target, updated_at=timestamp)


def validate_record(record: EvidenceRecord) -> None:
    """Raise when a record has structurally invalid fields."""
    validate_evidence_id(record.id)
    if not record.title.strip():
        raise ValidationError("Evidence title must not be empty", details={"field": "title"})
    validate_hex_digest(record.digests.sha256, length=64, field="sha256")
    validate_hex_digest(record.digests.md5, length=32, field="md5")
    if record.digests.size_bytes < 0:
        raise ValidationError("Evidence size cannot be negative", details={"field": "size_bytes"})
    if not record.mime.mime_type:
        raise ValidationError("Evidence MIME type is required", details={"field": "mime_type"})


def record_matches(
    record: EvidenceRecord,
    *,
    query: str = "",
    kind: EvidenceKind | None = None,
    status: EvidenceStatus | None = None,
    tag: str = "",
    mime_type: str = "",
    note_id: int | None = None,
    hash_prefix: str = "",
) -> bool:
    """Return whether a record satisfies a set of list filters."""
    if kind is not None and record.kind is not kind:
        return False
    if status is not None and record.status is not status:
        return False
    if tag and tag.casefold() not in {item.casefold() for item in record.tags}:
        return False
    if mime_type and mime_type.casefold() not in record.mime.mime_type.casefold():
        return False
    if note_id is not None and record.note_id != note_id:
        return False
    if hash_prefix and not record.sha256.casefold().startswith(hash_prefix.casefold()):
        return False
    if query:
        needle = query.strip().casefold()
        if needle and needle not in record.search_text():
            return False
    return True


def filter_records(
    records: Iterable[EvidenceRecord],
    *,
    query: str = "",
    kind: EvidenceKind | None = None,
    status: EvidenceStatus | None = None,
    tag: str = "",
    mime_type: str = "",
    note_id: int | None = None,
    hash_prefix: str = "",
    sort: str = "created_at",
    direction: str = "desc",
) -> list[EvidenceRecord]:
    """Filter and deterministically sort evidence records."""
    if sort not in SORT_FIELDS:
        raise ValidationError(f"Unsupported sort field: {sort}", details={"field": "sort"})
    if direction not in SORT_DIRECTIONS:
        raise ValidationError(
            f"Unsupported sort direction: {direction}", details={"field": "direction"}
        )
    selected = [
        record
        for record in records
        if record_matches(
            record,
            query=query,
            kind=kind,
            status=status,
            tag=tag,
            mime_type=mime_type,
            note_id=note_id,
            hash_prefix=hash_prefix,
        )
    ]
    return sorted(selected, key=lambda item: sort_key(item, sort), reverse=direction == "desc")


def sort_key(record: EvidenceRecord, field_name: str) -> Any:
    """Return a comparable sort key for one record field."""
    if field_name == "size_bytes":
        return record.size_bytes
    if field_name in {"created_at", "updated_at"}:
        return getattr(record, field_name)
    if field_name == "status":
        return record.status.value
    if field_name == "kind":
        return record.kind.value
    return record.title.casefold()


def paginate_records(
    records: Sequence[EvidenceRecord],
    *,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    """Slice a record list and report deterministic pagination metadata."""
    start = min(max(0, offset), len(records))
    end = min(start + limit, len(records))
    return list(records[start:end]), {
        "offset": start,
        "limit": limit,
        "total": len(records),
        "has_more": end < len(records),
        "next_offset": end if end < len(records) else None,
    }


def record_hash_index(records: Iterable[EvidenceRecord]) -> dict[str, str]:
    """Map both SHA-256 and MD5 digests to their evidence id."""
    index: dict[str, str] = {}
    for record in records:
        index[record.sha256] = record.id
        index[record.md5] = record.id
    return index


def record_fingerprint(record: EvidenceRecord) -> str:
    """Return a short stable fingerprint for display in compact tables."""
    return f"{record.id}:{record.sha256[:12]}"
