"""v4 HTTP handlers for the professional block editor.

Handlers own request parsing, capability enforcement, envelope construction,
and error translation. Domain rules stay in the service and storage layers.
Registration is additive and safe to call repeatedly during namespace
discovery.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import wraps
from typing import Any, TypeVar

from redscribe.v4.api_v4 import Route, global_registry
from redscribe.v4.blocks_pro.service import (
    BlockValidator,
    CodecError,
    DiffError,
    DocumentInvalidError,
    MarkdownCodec,
    SnapshotError,
)
from redscribe.v4.blocks_pro.storage import (
    BlockStore,
    ConflictError,
    DocumentNotFoundError,
    DuplicateDocumentError,
    RevisionNotFoundError,
    StorageError,
)
from redscribe.v4.blocks_pro.types import (
    BlockDocument,
    BlockOp,
    EditOperation,
)
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.contracts import (
    ApiError,
    Capability,
    CapabilitySet,
    EntityKind,
    ErrorCode,
    PageMeta,
    fail,
    new_entity_id,
    ok,
)
from redscribe.v4.events import DomainEvent, EventBus, EventKind
from redscribe.v4.pagination import etag_matches, paginate, weak_etag

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200
MAX_BODY_BYTES = 2_000_000
ROUTE_SPECS: tuple[tuple[str, str, str], ...] = (
    ("/blocks", "blocks.get", "GET"),
    ("/blocks/document", "blocks.put", "PUT"),
    ("/blocks/patch", "blocks.patch", "PATCH"),
    ("/blocks/history", "blocks.history", "GET"),
    ("/blocks/snapshots", "blocks.snapshots", "GET"),
)

F = TypeVar("F", bound=Callable[..., dict[str, Any]])


def require_str(body: Mapping[str, Any], key: str, limit: int = 240) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be a non-empty string", (key,))
    result = value.strip()
    if len(result) > limit:
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} exceeds {limit} characters", (key,))
    return result


def optional_str(body: Mapping[str, Any], key: str, limit: int = 240) -> str:
    value = body.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be a string", (key,))
    result = value.strip()
    if len(result) > limit:
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} exceeds {limit} characters", (key,))
    return result


def optional_int(body: Mapping[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = body.get(key)
    if value is None or value == "":
        return default
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be an integer", (key,))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ApiError(ErrorCode.INVALID_INPUT, f"{key} must be an integer", (key,)) from exc
    if not low <= parsed <= high:
        raise ApiError(
            ErrorCode.INVALID_INPUT,
            f"{key} must be between {low} and {high}",
            (key,),
        )
    return parsed


def error_envelope(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ApiError):
        return fail(exc)
    if isinstance(exc, DocumentNotFoundError):
        return fail(ApiError(ErrorCode.NOT_FOUND, str(exc)))
    if isinstance(exc, (DuplicateDocumentError, ConflictError)):
        return fail(ApiError(ErrorCode.CONFLICT, str(exc)))
    if isinstance(exc, (RevisionNotFoundError, SnapshotError)):
        return fail(ApiError(ErrorCode.NOT_FOUND, str(exc)))
    if isinstance(
        exc, (CodecError, DiffError, DocumentInvalidError, StorageError, ValueError, TypeError)
    ):
        return fail(ApiError(ErrorCode.INVALID_INPUT, str(exc)))
    return fail(ApiError(ErrorCode.INTERNAL, "unexpected block editor error"))


def as_api_error(exc: Exception) -> ApiError:
    payload = error_envelope(exc)
    error = payload["error"]
    assert isinstance(error, dict)
    return ApiError(
        code=ErrorCode(str(error["code"])),
        message=str(error["message"]),
        details=tuple(str(item) for item in error["details"]),
    )


def guard(handler: F) -> F:
    @wraps(handler)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return handler(*args, **kwargs)
        except ApiError:
            raise
        except Exception as exc:
            raise as_api_error(exc) from exc

    return wrapped  # type: ignore[return-value]


class BlockRoutes:
    """Stateless handlers bound to one store and capability set."""

    def __init__(
        self,
        store: BlockStore | None = None,
        capabilities: CapabilitySet | None = None,
        bus: EventBus | None = None,
        request_id_factory: Callable[[], str] = new_entity_id,
        codec: MarkdownCodec | None = None,
        validator: BlockValidator | None = None,
    ) -> None:
        self.store = store or BlockStore()
        self.capabilities = capabilities or CapabilitySet.full()
        self.gate = FeatureGate(self.capabilities)
        self.bus = bus
        self.request_id_factory = request_id_factory
        self.codec = codec or MarkdownCodec(annotate_ids=True)
        self.validator = validator or BlockValidator()

    def _meta(
        self,
        headers: Mapping[str, str],
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        etag: str = "",
        next_cursor: str = "",
    ) -> PageMeta:
        return PageMeta(
            request_id=headers.get("X-Request-ID") or self.request_id_factory(),
            page=page,
            page_size=page_size,
            etag=etag,
            next_cursor=next_cursor,
        )

    def _require(self, capability: Capability) -> None:
        try:
            self.gate.require(FeatureFlag.BLOCKS_PRO)
            self.capabilities.require(capability)
        except PermissionError as exc:
            raise ApiError(ErrorCode.FORBIDDEN, str(exc)) from exc

    def _emit(
        self,
        document: BlockDocument,
        actor: str,
        operations: Sequence[EditOperation] = (),
    ) -> None:
        if self.bus is None:
            return
        payload: dict[str, Any] = {
            "document_id": document.id,
            "title": document.title,
            "block_count": len(document.blocks),
            "checksum": document.checksum(),
            "operations": [item.label for item in operations],
            "actor": actor or "local",
        }
        self.bus.publish(
            DomainEvent(
                kind=EventKind.BLOCK_EDITED,
                aggregate_id=document.id,
                aggregate_kind=EntityKind.NOTE,
                payload=payload,
            )
        )

    def _document_from_body(self, body: Mapping[str, Any]) -> BlockDocument:
        raw = body.get("document")
        if isinstance(raw, Mapping):
            document = BlockDocument.from_dict(raw)
        elif isinstance(raw, str):
            document = self.codec.decode_with_id(raw, require_str(body, "id"))
        else:
            raise ApiError(
                ErrorCode.INVALID_INPUT, "document must be an object or markdown", ("document",)
            )
        issues = [issue for issue in self.validator.validate(document) if "duplicate" in issue.code]
        if issues:
            raise ApiError(ErrorCode.CONFLICT, issues[0].message)
        return document

    @guard
    def get(
        self,
        query: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        head = headers or {}
        self._require(Capability.READ)
        document_id = optional_str(query, "id")
        if document_id:
            document = self.store.get(document_id)
            etag = weak_etag(document.checksum())
            data = {
                "document": document.to_dict(),
                "checksum": document.checksum(),
                "word_count": document.word_count,
                "revision": self.store.latest_revision(document_id).number,
                "not_modified": etag_matches(head.get("If-None-Match", ""), etag),
            }
            return ok(data, self._meta(head, etag=etag))
        page = optional_int(query, "page", 1, 1, 10000)
        page_size = optional_int(query, "page_size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
        needle = optional_str(query, "query", 240)
        documents = self.store.search(needle) if needle else self.store.list()
        result = paginate(documents, page, page_size)
        data = result.to_dict(serialize=lambda item: item.to_dict())
        fingerprint = "|".join(f"{item.id}{item.checksum()}" for item in result.items)
        etag = weak_etag(f"{needle}:{page}:{page_size}:{fingerprint}")
        if etag_matches(head.get("If-None-Match", ""), etag):
            data["not_modified"] = True
            data["items"] = []
        data["query"] = needle
        return ok(data, self._meta(head, page, page_size, etag, result.next_cursor))

    @guard
    def put(
        self,
        body: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        head = headers or {}
        self._require(Capability.WRITE)
        document = self._document_from_body(body)
        expected = optional_str(body, "expected_checksum", 80)
        author = optional_str(head, "X-Actor", 120) or "local"
        created = not self.store.exists(document.id)
        revision = self.store.save(document, author, expected)
        self._emit(document, author)
        data = {
            "document": document.to_dict(),
            "created": created,
            "revision": revision.number,
            "checksum": revision.checksum,
        }
        return ok(data, self._meta(head, etag=weak_etag(revision.checksum)))

    @guard
    def patch(
        self,
        body: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        head = headers or {}
        self._require(Capability.WRITE)
        document_id = require_str(body, "id")
        raw_ops = body.get("operations")
        if not isinstance(raw_ops, (list, tuple)):
            raise ApiError(ErrorCode.INVALID_INPUT, "operations must be a list", ("operations",))
        operations = tuple(EditOperation.from_dict(item) for item in raw_ops)
        expected = optional_str(body, "expected_checksum", 80)
        author = optional_str(head, "X-Actor", 120) or "local"
        revision, applied = self.store.apply(document_id, operations, author, expected)
        self._emit(revision.document, author, applied)
        summary = {kind.value: 0 for kind in BlockOp}
        for operation in applied:
            summary[operation.op.value] += 1
        data = {
            "document": revision.document.to_dict(),
            "revision": revision.number,
            "checksum": revision.checksum,
            "applied": [item.to_dict() for item in applied],
            "summary": summary,
        }
        return ok(data, self._meta(head, etag=weak_etag(revision.checksum)))

    @guard
    def history(
        self,
        query: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        head = headers or {}
        self._require(Capability.READ)
        document_id = require_str(query, "id")
        page = optional_int(query, "page", 1, 1, 10000)
        page_size = optional_int(query, "page_size", DEFAULT_PAGE_SIZE, 1, MAX_PAGE_SIZE)
        revisions = self.store.history(document_id)
        result = paginate(revisions, page, page_size)
        data = result.to_dict(serialize=lambda item: item.to_dict())
        return ok(data, self._meta(head, page, page_size, result.etag, result.next_cursor))

    @guard
    def snapshots(
        self,
        body: Mapping[str, Any],
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        head = headers or {}
        document_id = require_str(body, "id")
        action = optional_str(body, "action", 40)
        if action == "restore":
            self._require(Capability.WRITE)
            snapshot_id = require_str(body, "snapshot_id")
            author = optional_str(head, "X-Actor", 120) or "local"
            revision = self.store.restore_snapshot(
                document_id,
                snapshot_id,
                optional_str(body, "expected_checksum", 80),
                author,
            )
            self._emit(revision.document, author)
            data = {
                "document": revision.document.to_dict(),
                "revision": revision.number,
                "restored_from": snapshot_id,
            }
            return ok(data, self._meta(head, etag=weak_etag(revision.checksum)))
        self._require(Capability.READ)
        reason = optional_str(body, "reason", 60)
        if action == "create":
            self._require(Capability.WRITE)
            snapshot = self.store.snapshot(document_id, reason or "manual")
            items = [snapshot.to_dict()]
        else:
            items = [item.to_dict() for item in self.store.snapshots(document_id)]
        data = {"snapshots": items, "count": len(items), "document_id": document_id}
        return ok(data, self._meta(head, etag=weak_etag(str(items))))


def register(api: object | None = None) -> tuple[Route, ...]:
    """Register block routes on ``api`` (or the global registry)."""
    target = api if api is not None else global_registry()
    register_hook = getattr(target, "register", None)
    lookup_hook = getattr(target, "get", None)
    hooks: tuple[Callable[..., Any], Callable[..., Any]] | None = None
    if callable(register_hook) and callable(lookup_hook):
        hooks = (register_hook, lookup_hook)
    registered: list[Route] = []
    for prefix, name, _method in ROUTE_SPECS:
        route = Route(prefix=prefix, name=name)
        if hooks is not None and hooks[1](route.full_path) is None:
            route = hooks[0](prefix, name)
        registered.append(route)
    return tuple(registered)


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "ROUTE_SPECS",
    "BlockRoutes",
    "as_api_error",
    "error_envelope",
    "guard",
    "optional_int",
    "optional_str",
    "register",
    "require_str",
]
