"""Evidence vault namespace for API v2.

Routes are registered additively through :func:`register`. The namespace is
installed automatically for every :class:`ApiV2` instance by
:func:`redscribe.ui.web.v2.namespaces.install_namespaces`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from redscribe.ui.web.v2.contracts import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Page,
    V2Error,
    V2ErrorCode,
    compute_etag,
)
from redscribe.ui.web.v2.routes import ApiV2, RouteResult
from redscribe.v2.evidence.errors import EvidenceError
from redscribe.v2.evidence.hashing import decode_base64_payload, encode_base64_payload
from redscribe.v2.evidence.models import (
    AcquisitionMethod,
    CustodyAction,
    DispositionAction,
    EvidenceKind,
    EvidenceStatus,
    LinkType,
    RetentionBasis,
)
from redscribe.v2.evidence.services import EvidenceVaultService
from redscribe.v2.evidence.thumbnails import thumbnail_metadata
from redscribe.v2.evidence.validation import (
    coerce_bool,
    normalize_tags,
    normalize_timestamp,
    now_iso,
    require_text,
    validate_evidence_id,
    validate_hex_digest,
    validate_limit,
    validate_offset,
)

Handler = Callable[[EvidenceVaultService, dict[str, Any]], RouteResult]

SERVICE_ATTR = "_evidence_service"
REGISTERED_ATTR = "_evidence_routes_registered"


def _as_v2_error(error: Exception) -> V2Error:
    if isinstance(error, V2Error):
        return error
    if isinstance(error, EvidenceError):
        return V2Error(
            error.status,
            error.code,
            error.message,
            details=error.details,
        )
    if isinstance(error, (ValueError, TypeError)):
        return V2Error(400, V2ErrorCode.INVALID_REQUEST, str(error) or "Invalid request")
    return V2Error(
        500,
        V2ErrorCode.INTERNAL,
        "Internal evidence vault error",
        retryable=True,
    )


def _field(field: str) -> dict[str, str]:
    return {"field": field}


def _choice(body: Mapping[str, Any], key: str, enum_type: Any, default: Any) -> Any:
    raw = body.get(key)
    if raw is None:
        return default
    if not isinstance(raw, str):
        raise V2Error(
            400, V2ErrorCode.INVALID_TYPE, f"'{key}' must be a string", details=_field(key)
        )
    candidate = raw.strip().casefold()
    for member in enum_type:
        if member.value == candidate or member.name.casefold() == candidate:
            return member
    allowed = ", ".join(member.value for member in enum_type)
    raise V2Error(
        400,
        V2ErrorCode.INVALID_CHOICE,
        f"Unknown {key}: {raw}",
        details={"field": key, "allowed": allowed},
    )


def _optional_id(body: Mapping[str, Any], key: str) -> str | None:
    value = body.get(key)
    if value is None:
        return None
    return validate_evidence_id(value, field=key)


def _page_limit(body: Mapping[str, Any]) -> int:
    raw = body.get("limit")
    if raw is None:
        return DEFAULT_PAGE_SIZE
    return min(validate_limit(raw, maximum=MAX_PAGE_SIZE), MAX_PAGE_SIZE)


def _body_bytes(body: Mapping[str, Any], *, max_bytes: int) -> tuple[bytes, str]:
    encoded = body.get("content_base64", body.get("content"))
    if not isinstance(encoded, str) or not encoded:
        raise V2Error(
            400,
            V2ErrorCode.MISSING_FIELD,
            "Missing 'content_base64'",
            details=_field("content_base64"),
        )
    try:
        data = decode_base64_payload(encoded, max_bytes=max_bytes)
    except ValueError as exc:
        raise V2Error(
            400, V2ErrorCode.INVALID_REQUEST, str(exc), details=_field("content_base64")
        ) from exc
    filename = require_text(
        body,
        "filename",
        default="evidence.bin",
        max_length=255,
    )
    return data, filename


def _service_of(api: ApiV2) -> EvidenceVaultService:
    service = getattr(api, SERVICE_ATTR, None)
    if not isinstance(service, EvidenceVaultService):
        raise V2Error(500, V2ErrorCode.INTERNAL, "Evidence vault service is unavailable")
    return service


def _success(data: Any, *, page: Page | None = None) -> RouteResult:
    etag = compute_etag({"data": data, "page": page.as_dict() if page else None})
    return RouteResult(data, page=page, etag=etag)


def handle_list(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """List evidence records with filters and paging."""
    kind = _choice(body, "kind", EvidenceKind, None)
    status = _choice(body, "status", EvidenceStatus, None)
    sort = require_text(body, "sort", default="created_at", max_length=40)
    direction = require_text(body, "direction", default="desc", max_length=10)
    raw_note_id = body.get("note_id")
    note_id = (
        raw_note_id if isinstance(raw_note_id, int) and not isinstance(raw_note_id, bool) else None
    )
    rows, meta = service.list_page(
        offset=validate_offset(body.get("offset")),
        limit=_page_limit(body),
        query=require_text(body, "query", default="", max_length=500),
        kind=kind,
        status=status,
        tag=require_text(body, "tag", default="", max_length=60),
        mime_type=require_text(body, "mime_type", default="", max_length=120),
        note_id=note_id,
        hash_prefix=require_text(body, "hash_prefix", default="", max_length=64),
        sort=sort,
        direction=direction,
    )
    page = Page(
        cursor=encode_offset(meta["offset"]),
        next=encode_offset(meta["next_offset"]) if meta["next_offset"] is not None else None,
        total=meta["total"],
        limit=meta["limit"],
        has_more=meta["has_more"],
    )
    return _success([row.summary() for row in rows], page=page)


def encode_offset(offset: int) -> str:
    """Encode a numeric offset as an opaque v2 cursor."""
    from redscribe.ui.web.v2.contracts import encode_cursor

    return encode_cursor({"offset": offset})


def handle_view(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Return a composite list payload with integrity badges."""
    payload = service.list_view(
        offset=validate_offset(body.get("offset")),
        limit=_page_limit(body),
        query=require_text(body, "query", default="", max_length=500),
        kind=_choice(body, "kind", EvidenceKind, None),
        status=_choice(body, "status", EvidenceStatus, None),
        tag=require_text(body, "tag", default="", max_length=60),
    )
    return _success(payload)


def handle_get(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Return one evidence record."""
    return _success(service.get_record(require_text(body, "id", max_length=80)).detail())


def handle_detail(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Return the composite evidence detail payload."""
    return _success(service.detail(require_text(body, "id", max_length=80)))


def handle_create(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Register evidence that is held outside the vault."""
    record = service.record_external(
        title=require_text(body, "title", max_length=200, min_length=1),
        description=require_text(body, "description", default="", max_length=4_000),
        source_path=require_text(body, "source_path", default="", max_length=500),
        kind=_choice(body, "kind", EvidenceKind, None),
        tags=normalize_tags(body.get("tags")),
        note_id=body.get("note_id")
        if isinstance(body.get("note_id"), int) and not isinstance(body.get("note_id"), bool)
        else None,
        operator=require_text(body, "operator", default="", max_length=120),
        case_reference=require_text(body, "case_reference", default="", max_length=120),
    )
    return _success(record.detail())


def handle_update(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Update editable record fields."""
    changes: dict[str, Any] = {}
    for key in ("title", "description", "original_filename"):
        if key in body and body[key] is not None:
            changes[key] = require_text(
                body, key, max_length=4_000 if key == "description" else 255
            )
    if "tags" in body:
        changes["tags"] = normalize_tags(body.get("tags"))
    if "kind" in body:
        changes["kind"] = _choice(body, "kind", EvidenceKind, None)
    if "note_id" in body:
        changes["note_id"] = body.get("note_id")
    if "custom_fields" in body:
        changes["custom_fields"] = body.get("custom_fields")
    return _success(
        service.update_record(require_text(body, "id", max_length=80), **changes).detail()
    )


def handle_status(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Move a record to a new lifecycle state."""
    record = service.set_status(
        require_text(body, "id", max_length=80),
        _choice(body, "status", EvidenceStatus, EvidenceStatus.ACQUIRED),
        actor=require_text(body, "actor", default="system", max_length=120),
        description=require_text(body, "description", default="", max_length=1_000),
        force=coerce_bool(body.get("force")),
    )
    return _success(record.summary())


def handle_delete(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Delete an evidence record and its metadata."""
    removed = service.delete_record(
        require_text(body, "id", max_length=80),
        remove_blob=coerce_bool(body.get("remove_blob"), default=True),
    )
    return _success({"id": body.get("id"), "deleted": removed})


def handle_ingest(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Ingest a base64-encoded file payload."""
    data, filename = _body_bytes(body, max_bytes=service.max_bytes)
    record = service.ingest_bytes(
        data,
        filename=filename,
        title=require_text(body, "title", default="", max_length=200),
        description=require_text(body, "description", default="", max_length=4_000),
        mime_type=require_text(body, "mime_type", default="", max_length=120),
        tags=normalize_tags(body.get("tags")),
        note_id=body.get("note_id")
        if isinstance(body.get("note_id"), int) and not isinstance(body.get("note_id"), bool)
        else None,
        method=_choice(body, "method", AcquisitionMethod, AcquisitionMethod.MANUAL_UPLOAD),
        actor=require_text(body, "actor", default="system", max_length=120),
        source_path=require_text(body, "source_path", default="", max_length=500),
        case_reference=require_text(body, "case_reference", default="", max_length=120),
        dedupe=coerce_bool(body.get("dedupe"), default=True),
    )
    return _success(record.detail())


def handle_ingest_path(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Ingest a local file by path."""
    path = require_text(body, "path", max_length=1_000, min_length=1)
    record = service.ingest_path(
        path,
        title=require_text(body, "title", default="", max_length=200),
        description=require_text(body, "description", default="", max_length=4_000),
        tags=normalize_tags(body.get("tags")),
        method=_choice(body, "method", AcquisitionMethod, AcquisitionMethod.FORENSIC_IMAGE),
        actor=require_text(body, "actor", default="system", max_length=120),
    )
    return _success(record.detail())


def handle_hash(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Compute digests for raw base64 bytes."""
    data, _ = _body_bytes(body, max_bytes=service.max_bytes)
    expected = body.get("expected_sha256")
    return _success(
        service.verify_digest(
            data,
            expected_sha256=validate_hex_digest(expected, length=64) if expected else "",
        )
    )


def handle_thumbnail(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Build thumbnail metadata for base64 bytes without ingesting them."""
    data, filename = _body_bytes(body, max_bytes=service.max_bytes)
    from redscribe.v2.evidence.hashing import sha256_hex
    from redscribe.v2.evidence.mime import detect_mime

    mime = detect_mime(
        data,
        filename=filename,
        declared=require_text(body, "mime_type", default="", max_length=120),
    )
    metadata = thumbnail_metadata(
        data,
        mime_type=mime.mime_type,
        source_sha256=sha256_hex(data),
        filename=filename,
    )
    return _success({"mime": mime.as_dict(), "thumbnail": metadata.as_dict()})


def handle_verify(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Verify one evidence item."""
    return _success(service.verify_record(require_text(body, "id", max_length=80)).as_dict())


def handle_verify_all(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Verify every evidence item."""
    return _success(
        service.verify_all(
            include_unavailable=coerce_bool(body.get("include_unavailable"), default=True)
        )
    )


def handle_custody_list(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Return a custody timeline for one item."""
    return _success(service.custody_view(require_text(body, "id", max_length=80)))


def handle_custody_add(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Append a custody event."""
    event = service.add_custody(
        require_text(body, "id", max_length=80),
        _choice(body, "action", CustodyAction, CustodyAction.RECEIVED),
        actor=require_text(body, "actor", default="system", max_length=120),
        timestamp=normalize_timestamp(body.get("timestamp")) or now_iso(),
        description=require_text(body, "description", default="", max_length=1_000),
        location=require_text(body, "location", default="", max_length=200),
        reference=require_text(body, "reference", default="", max_length=200),
        metadata=body.get("metadata") if isinstance(body.get("metadata"), Mapping) else None,
    )
    return _success(event.as_dict())


def handle_custody_verify(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Verify a custody chain."""
    valid, problems = service.verify_custody(require_text(body, "id", max_length=80))
    return _success({"valid": valid, "problems": problems})


def handle_provenance_get(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Return acquisition provenance for one item."""
    return _success(service.get_provenance(require_text(body, "id", max_length=80)))


def handle_provenance_update(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Update acquisition provenance fields."""
    changes: dict[str, Any] = {}
    for key in (
        "tool",
        "tool_version",
        "operator",
        "source_path",
        "source_description",
        "case_reference",
        "witness",
        "notes",
    ):
        if key in body:
            changes[key] = require_text(body, key, default="", max_length=2_000)
    if "method" in body:
        changes["method"] = _choice(
            body, "method", AcquisitionMethod, AcquisitionMethod.MANUAL_UPLOAD
        )
    if "acquired_at" in body:
        changes["acquired_at"] = normalize_timestamp(body.get("acquired_at")) or ""
    if "image_number" in body:
        raw = body.get("image_number")
        changes["image_number"] = raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
    return _success(service.set_provenance(require_text(body, "id", max_length=80), **changes))


def handle_links_list(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Return finding links, optionally grouped."""
    links = service.list_links(
        evidence_id=require_text(body, "id", default="", max_length=80),
        finding_id=require_text(body, "finding_id", default="", max_length=120),
    )
    return _success(
        {
            "links": [item.as_dict() for item in links],
            "summary": service.links_view(
                evidence_id=require_text(body, "id", default="", max_length=80),
                finding_id=require_text(body, "finding_id", default="", max_length=120),
            )["summary"],
        }
    )


def handle_links_add(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Create a finding link."""
    link = service.add_link(
        require_text(body, "id", max_length=80),
        require_text(body, "finding_id", max_length=120, min_length=1),
        finding_title=require_text(body, "finding_title", default="", max_length=200),
        link_type=_choice(body, "link_type", LinkType, LinkType.RELATED_TO),
        strength=float(body.get("strength", 0.5))
        if isinstance(body.get("strength"), (int, float))
        and not isinstance(body.get("strength"), bool)
        else 0.5,
        created_by=require_text(body, "created_by", default="system", max_length=120),
        note=require_text(body, "note", default="", max_length=1_000),
        allow_duplicate=coerce_bool(body.get("allow_duplicate")),
    )
    return _success(link.as_dict())


def handle_links_remove(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Remove a finding link."""
    raw = body.get("link_id", body.get("id"))
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise V2Error(400, V2ErrorCode.INVALID_TYPE, "'link_id' must be an integer")
    return _success({"link_id": raw, "deleted": service.remove_link(raw)})


def handle_links_view(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Return grouped link metadata."""
    return _success(
        service.links_view(
            evidence_id=require_text(body, "id", default="", max_length=80),
            finding_id=require_text(body, "finding_id", default="", max_length=120),
        )
    )


def handle_retention_get(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Return one retention policy and its decision."""
    return _success(
        service.get_retention(
            require_text(body, "id", max_length=80),
            now=normalize_timestamp(body.get("now")),
        )
    )


def handle_retention_set(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Create or update a retention policy."""
    changes: dict[str, Any] = {}
    if "basis" in body:
        changes["basis"] = _choice(body, "basis", RetentionBasis, RetentionBasis.CASE)
    if "retain_days" in body:
        raw = body.get("retain_days")
        changes["retain_days"] = raw if isinstance(raw, int) and not isinstance(raw, bool) else 365
    if "retain_until" in body:
        changes["retain_until"] = normalize_timestamp(body.get("retain_until")) or ""
    if "review_at" in body:
        changes["review_at"] = normalize_timestamp(body.get("review_at")) or ""
    if "disposition" in body:
        changes["disposition"] = _choice(
            body, "disposition", DispositionAction, DispositionAction.KEEP
        )
    if "reason" in body:
        changes["reason"] = require_text(body, "reason", default="", max_length=1_000)
    policy = service.set_retention(require_text(body, "id", max_length=80), **changes)
    return _success(policy.as_dict())


def handle_retention_hold(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Apply or release a legal hold."""
    policy = service.set_hold(
        require_text(body, "id", max_length=80),
        held=coerce_bool(body.get("held"), default=True),
        reason=require_text(body, "reason", default="", max_length=1_000),
    )
    return _success(policy.as_dict())


def handle_retention_plan(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """List retention decisions for all items."""
    return _success(service.retention_plan(now=normalize_timestamp(body.get("now"))))


def handle_retention_apply(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Apply retention decisions."""
    return _success(
        service.apply_retention(
            now=normalize_timestamp(body.get("now")),
            destroy=coerce_bool(body.get("destroy")),
        )
    )


def handle_manifest_export(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Export a manifest of the current vault."""
    manifest = service.export_manifest(
        case_reference=require_text(body, "case_reference", default="", max_length=120)
    )
    return _success(manifest.as_dict())


def handle_manifest_json(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Export a manifest as a JSON string."""
    return _success({"json": service.manifest_json()})


def handle_manifest_preview(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Preview an import without applying it."""
    return _success(
        service.preview_import(
            _manifest_payload(body),
            strategy=require_text(body, "strategy", default="skip", max_length=20),
        )
    )


def _manifest_payload(body: Mapping[str, Any]) -> dict[str, Any] | str:
    manifest = body.get("manifest")
    if isinstance(manifest, Mapping):
        return dict(manifest)
    raw_json = body.get("manifest_json")
    if isinstance(raw_json, str) and raw_json.strip():
        return raw_json
    raise V2Error(
        400,
        V2ErrorCode.MISSING_FIELD,
        "Missing 'manifest'",
        details=_field("manifest"),
    )


def handle_manifest_import(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Apply a manifest import."""
    return _success(
        service.import_manifest(
            _manifest_payload(body),
            strategy=require_text(body, "strategy", default="skip", max_length=20),
            actor=require_text(body, "actor", default="manifest-import", max_length=120),
        )
    )


def handle_stats(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Return evidence vault counters."""
    return _success(service.stats().as_dict())


def handle_search(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Search evidence by hash prefix, tag, or free text."""
    records = service.list_records(
        query=require_text(body, "query", default="", max_length=500),
        tag=require_text(body, "tag", default="", max_length=60),
        hash_prefix=require_text(body, "hash_prefix", default="", max_length=64),
    )
    return _success([item.summary() for item in records[: _page_limit(body)]])


def handle_export_bundle(service: EvidenceVaultService, body: dict[str, Any]) -> RouteResult:
    """Return a manifest plus base64 payloads for portable export."""
    manifest = service.export_manifest()
    files: dict[str, str] = {}
    for record in service._repository.all_records():
        if not record.stored_path:
            continue
        data = service.blobs.get(record.stored_path)
        if data is not None:
            files[record.id] = encode_base64_payload(data)
    return _success({"manifest": manifest.as_dict(), "files": files})


ROUTE_SPECS: tuple[tuple[str, str, Handler, tuple[str, ...], tuple[str, ...], bool, str], ...] = (
    (
        "evidence.list",
        "List evidence records with filters and cursor paging.",
        handle_list,
        (),
        ("query", "kind", "status", "tag", "sort", "direction", "offset", "limit"),
        False,
        "evidence",
    ),
    (
        "evidence.view",
        "Return list rows decorated with integrity badges.",
        handle_view,
        (),
        ("query", "kind", "status", "tag", "offset", "limit"),
        False,
        "evidence",
    ),
    (
        "evidence.get",
        "Return one evidence record by id.",
        handle_get,
        ("id",),
        (),
        False,
        "evidence",
    ),
    (
        "evidence.detail",
        "Return record, integrity, custody, links, and retention.",
        handle_detail,
        ("id",),
        (),
        False,
        "evidence",
    ),
    (
        "evidence.create",
        "Register evidence held outside the vault.",
        handle_create,
        ("title",),
        ("description", "source_path", "kind", "tags", "note_id", "operator", "case_reference"),
        True,
        "evidence",
    ),
    (
        "evidence.update",
        "Update editable evidence metadata.",
        handle_update,
        ("id",),
        ("title", "description", "tags", "kind", "note_id", "custom_fields"),
        True,
        "evidence",
    ),
    (
        "evidence.set_status",
        "Transition an evidence item to a new lifecycle state.",
        handle_status,
        ("id", "status"),
        ("actor", "description", "force"),
        True,
        "evidence",
    ),
    (
        "evidence.delete",
        "Delete one evidence item and its metadata.",
        handle_delete,
        ("id",),
        ("remove_blob",),
        True,
        "evidence",
    ),
    (
        "evidence.ingest",
        "Ingest a base64-encoded file as evidence.",
        handle_ingest,
        ("content_base64", "filename"),
        (
            "title",
            "description",
            "mime_type",
            "tags",
            "note_id",
            "method",
            "actor",
            "source_path",
            "case_reference",
            "dedupe",
        ),
        True,
        "evidence",
    ),
    (
        "evidence.ingest_path",
        "Ingest a local file path as evidence.",
        handle_ingest_path,
        ("path",),
        ("title", "description", "tags", "method", "actor"),
        True,
        "evidence",
    ),
    (
        "evidence.hash",
        "Compute SHA-256 and MD5 digests for base64 bytes.",
        handle_hash,
        ("content_base64",),
        ("expected_sha256",),
        False,
        "evidence",
    ),
    (
        "evidence.thumbnail",
        "Inspect MIME and thumbnail metadata for bytes.",
        handle_thumbnail,
        ("content_base64", "filename"),
        ("mime_type",),
        False,
        "evidence",
    ),
    (
        "evidence.verify",
        "Verify one evidence item against stored bytes.",
        handle_verify,
        ("id",),
        (),
        False,
        "evidence",
    ),
    (
        "evidence.verify_all",
        "Verify every evidence item and summarize results.",
        handle_verify_all,
        (),
        ("include_unavailable",),
        False,
        "evidence",
    ),
    (
        "evidence.custody.list",
        "Return a custody timeline for one item.",
        handle_custody_list,
        ("id",),
        (),
        False,
        "custody",
    ),
    (
        "evidence.custody.add",
        "Append an event to the chain of custody.",
        handle_custody_add,
        ("id", "action"),
        ("actor", "timestamp", "description", "location", "reference", "metadata"),
        True,
        "custody",
    ),
    (
        "evidence.custody.verify",
        "Verify a chain of custody.",
        handle_custody_verify,
        ("id",),
        (),
        False,
        "custody",
    ),
    (
        "evidence.provenance.get",
        "Return acquisition provenance for one item.",
        handle_provenance_get,
        ("id",),
        (),
        False,
        "provenance",
    ),
    (
        "evidence.provenance.update",
        "Update acquisition provenance fields.",
        handle_provenance_update,
        ("id",),
        (
            "method",
            "tool",
            "tool_version",
            "operator",
            "source_path",
            "source_description",
            "acquired_at",
            "case_reference",
            "witness",
            "image_number",
            "notes",
        ),
        True,
        "provenance",
    ),
    (
        "evidence.links.list",
        "List finding links for evidence or a finding.",
        handle_links_list,
        (),
        ("id", "finding_id"),
        False,
        "link",
    ),
    (
        "evidence.links.add",
        "Create a finding link.",
        handle_links_add,
        ("id", "finding_id"),
        ("finding_title", "link_type", "strength", "created_by", "note", "allow_duplicate"),
        True,
        "link",
    ),
    (
        "evidence.links.remove",
        "Remove a finding link.",
        handle_links_remove,
        ("link_id",),
        (),
        True,
        "link",
    ),
    (
        "evidence.links.view",
        "Return grouped finding link metadata.",
        handle_links_view,
        (),
        ("id", "finding_id"),
        False,
        "link",
    ),
    (
        "evidence.retention.get",
        "Return one retention policy and decision.",
        handle_retention_get,
        ("id",),
        ("now",),
        False,
        "retention",
    ),
    (
        "evidence.retention.set",
        "Create or update a retention policy.",
        handle_retention_set,
        ("id",),
        ("basis", "retain_days", "retain_until", "review_at", "disposition", "reason"),
        True,
        "retention",
    ),
    (
        "evidence.retention.hold",
        "Apply or release a legal hold.",
        handle_retention_hold,
        ("id",),
        ("held", "reason"),
        True,
        "retention",
    ),
    (
        "evidence.retention.plan",
        "List retention decisions for all items.",
        handle_retention_plan,
        (),
        ("now",),
        False,
        "retention",
    ),
    (
        "evidence.retention.apply",
        "Apply retention decisions.",
        handle_retention_apply,
        (),
        ("now", "destroy"),
        True,
        "retention",
    ),
    (
        "evidence.manifest.export",
        "Export a checksummed evidence manifest.",
        handle_manifest_export,
        (),
        ("case_reference",),
        False,
        "manifest",
    ),
    (
        "evidence.manifest.json",
        "Export a manifest as JSON text.",
        handle_manifest_json,
        (),
        (),
        False,
        "manifest",
    ),
    (
        "evidence.manifest.preview",
        "Preview a manifest import without changes.",
        handle_manifest_preview,
        ("manifest",),
        ("strategy",),
        False,
        "manifest",
    ),
    (
        "evidence.manifest.import",
        "Import records and metadata from a manifest.",
        handle_manifest_import,
        ("manifest",),
        ("strategy", "actor"),
        True,
        "manifest",
    ),
    (
        "evidence.manifest.bundle",
        "Export a manifest with base64 file payloads.",
        handle_export_bundle,
        (),
        (),
        False,
        "manifest",
    ),
    (
        "evidence.stats",
        "Return evidence vault aggregate counters.",
        handle_stats,
        (),
        (),
        False,
        "evidence",
    ),
    (
        "evidence.search",
        "Search evidence by text, tag, or hash prefix.",
        handle_search,
        (),
        ("query", "tag", "hash_prefix", "limit"),
        False,
        "evidence",
    ),
)


def register(api: ApiV2) -> EvidenceVaultService:
    """Register every evidence route on an API v2 instance."""
    if getattr(api, REGISTERED_ATTR, False):
        return _service_of(api)
    from redscribe.v2.evidence.services import create_service

    service = create_service(api.vault)
    setattr(api, SERVICE_ATTR, service)
    for name, description, handler, required, optional, mutating, entity_type in ROUTE_SPECS:

        def wrapped(
            body: dict[str, Any],
            _handler: Handler = handler,
            _service: EvidenceVaultService = service,
        ) -> RouteResult:
            try:
                return _handler(_service, body)
            except Exception as exc:
                raise _as_v2_error(exc) from exc

        api._register(
            name,
            wrapped,
            description,
            required=required,
            optional=optional,
            mutating=mutating,
            entity_type=entity_type,
        )
    setattr(api, REGISTERED_ATTR, True)
    return service


def routes() -> tuple[str, ...]:
    """Return all evidence route names."""
    return tuple(spec[0] for spec in ROUTE_SPECS)


__all__ = ["register", "routes"]
