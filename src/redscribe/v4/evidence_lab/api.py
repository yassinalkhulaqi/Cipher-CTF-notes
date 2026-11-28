"""v4 HTTP-shaped handlers for the evidence inspection lab.

Handlers accept a small request value object and always return a v4 envelope:
``ok(...)`` on success or ``fail(ApiError(...))`` on any handled failure. They
never raise for invalid client input, never read files, and never execute data.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v4.api_v4 import RouteRegistry, global_registry, register_routes
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.clock import SYSTEM_CLOCK, Clock
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
from redscribe.v4.pagination import PageResult, apply_cursor, paginate, weak_etag

from .service import CustodyGraph, HashVerifier, HexDumper, StringExtractor
from .storage import EvidenceStore, StoreError
from .types import (
    CustodyEntry,
    EvidenceRecord,
    HashAlgorithm,
    HashVerification,
    InspectionResult,
    ValidationError,
    normalize_tags,
    require_int,
    require_text,
)

ROUTE_PREFIX = "/evidence"
ROUTE_NAME = "evidence-lab"
MAX_BYTES_HEX = 65536


def _as_str(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _as_int(value: object, default: int) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ApiError(ErrorCode.INVALID_INPUT, "expected integer")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ApiError(ErrorCode.INVALID_INPUT, f"expected integer, got {value!r}") from exc
    return parsed


def decode_bytes_hex(value: object) -> bytes:
    """Decode caller-supplied hex data without touching the filesystem."""
    text = _as_str(value).strip().casefold().replace(" ", "").replace("\n", "")
    if len(text) > MAX_BYTES_HEX * 2:
        raise ApiError(ErrorCode.INVALID_INPUT, "hex payload exceeds lab limit")
    if len(text) % 2:
        raise ApiError(ErrorCode.INVALID_INPUT, "hex payload has odd length")
    try:
        return bytes.fromhex(text)
    except ValueError as exc:
        raise ApiError(ErrorCode.INVALID_INPUT, "hex payload is not hexadecimal") from exc


@dataclass(slots=True)
class EvidenceRequest:
    """A transport-agnostic request for evidence-lab handlers."""

    method: str = "GET"
    path: str = ROUTE_PREFIX
    query: Mapping[str, object] = field(default_factory=dict)
    body: Mapping[str, object] = field(default_factory=dict)
    capabilities: CapabilitySet = field(default_factory=CapabilitySet.full)
    request_id: str = field(default_factory=new_entity_id)
    feature_gate: FeatureGate | None = None

    def param(self, name: str, default: str = "") -> str:
        return _as_str(self.query.get(name), default)

    def require_gate(self) -> None:
        gate = self.feature_gate or FeatureGate(self.capabilities)
        if not gate.is_enabled(FeatureFlag.EVIDENCE_LAB):
            raise ApiError(ErrorCode.FORBIDDEN, "feature disabled: evidence_lab")

    def require(self, capability: Capability) -> None:
        try:
            self.capabilities.require(capability)
        except ApiError:
            raise ApiError(ErrorCode.FORBIDDEN, f"missing capability: {capability.value}") from None


class EvidenceApi:
    """Handler collection wired to a store, event bus, and capability set."""

    def __init__(
        self,
        store: EvidenceStore | None = None,
        bus: EventBus | None = None,
        clock: Clock | None = None,
        capabilities: CapabilitySet | None = None,
    ) -> None:
        self.clock = clock or SYSTEM_CLOCK
        self.store = store or EvidenceStore(clock=self.clock)
        self.bus = bus or EventBus()
        self.capabilities = capabilities or CapabilitySet.full()
        self.dumper = HexDumper()
        self.extractor = StringExtractor()
        self.verifier = HashVerifier()

    def _meta(
        self,
        request: EvidenceRequest,
        page: int,
        page_size: int,
        etag: str = "",
        next_cursor: str = "",
    ) -> PageMeta:
        return PageMeta(
            request_id=request.request_id,
            page=page,
            page_size=page_size,
            etag=etag,
            next_cursor=next_cursor,
        )

    def _page_arguments(self, request: EvidenceRequest) -> tuple[int, int]:
        page = _as_int(request.query.get("page"), 1)
        page_size = _as_int(request.query.get("page_size"), 50)
        if page < 1 or not 1 <= page_size <= 500:
            raise ApiError(ErrorCode.INVALID_INPUT, "invalid pagination window")
        return page, page_size

    def _emit(
        self, kind: EventKind, record: EvidenceRecord, payload: Mapping[str, object]
    ) -> DomainEvent:
        event = DomainEvent(
            kind=kind,
            aggregate_id=record.id,
            aggregate_kind=EntityKind.EVIDENCE,
            occurred_at=self.clock.iso(),
            payload=dict(payload),
        )
        self.bus.publish(event)
        return event

    def list_evidence(self, request: EvidenceRequest) -> dict[str, Any]:
        request.require_gate()
        request.require(Capability.READ)
        page, page_size = self._page_arguments(request)
        tag = request.param("tag").casefold()
        items: Sequence[EvidenceRecord] = self.store.by_tag(tag) if tag else self.store.all()
        items = apply_cursor(list(items), request.param("cursor") or None)
        result: PageResult[EvidenceRecord] = paginate(list(items), page, page_size)
        etag = weak_etag("|".join(f"{item.id}:{item.sha256}" for item in result.items))
        meta = self._meta(
            request, result.page, result.page_size, etag=etag, next_cursor=result.next_cursor
        )
        payload = result.to_dict(lambda record: record.to_dict())
        if_none_match = request.param("if_none_match")
        if if_none_match and if_none_match.strip('W/"') == etag.strip('W/"'):
            payload["items"] = []
            payload["not_modified"] = True
        else:
            payload["not_modified"] = False
        return ok(payload, meta)

    def create_evidence(self, request: EvidenceRequest) -> dict[str, Any]:
        request.require_gate()
        request.require(Capability.WRITE)
        body = request.body
        identifier = _as_str(body.get("id")) or new_entity_id()
        if self.store.contains(identifier):
            raise ApiError(ErrorCode.CONFLICT, f"evidence already exists: {identifier}")
        name = require_text(body.get("name"), "name")
        size = require_int(body.get("size"), "size")
        acquired_at = _as_str(body.get("acquired_at")) or self.clock.iso()
        raw_tags = body.get("tags", ())
        tags = normalize_tags(raw_tags if isinstance(raw_tags, (list, tuple)) else ())
        raw_hex = body.get("bytes_hex")
        data = decode_bytes_hex(raw_hex) if raw_hex is not None else b""
        expected = _as_str(body.get("sha256")) or (
            self.verifier.compute(data, HashAlgorithm.SHA256) if data else ""
        )
        record = EvidenceRecord.create(
            name=name,
            size=size,
            sha256=expected,
            acquired_at=acquired_at,
            tags=tags,
            identifier=identifier,
        )
        self.store.add(record)
        self._emit(EventKind.EVIDENCE_ADDED, record, {"name": record.name, "size": record.size})
        verification: HashVerification | None = None
        if data:
            verification = self.verifier.verify(data, HashAlgorithm.SHA256, record.sha256)
            self._emit(
                EventKind.EVIDENCE_HASHED,
                record,
                {"algorithm": HashAlgorithm.SHA256.value, "matches": verification.matches},
            )
            self._emit(EventKind.EVIDENCE_HASHED, record, {"algorithm": "all"})
        payload: dict[str, Any] = {"evidence": record.to_dict()}
        if verification is not None:
            payload["verification"] = verification.to_dict()
        return ok(payload, self._meta(request, 1, 1, etag=weak_etag(record.sha256)))

    def get_evidence(self, request: EvidenceRequest, identifier: str) -> dict[str, Any]:
        request.require_gate()
        request.require(Capability.READ)
        record = self.store.get(identifier)
        return ok(record.to_dict(), self._meta(request, 1, 1, etag=weak_etag(record.sha256)))

    def inspect(self, request: EvidenceRequest, identifier: str) -> dict[str, Any]:
        request.require_gate()
        request.require(Capability.READ)
        record = self.store.get(identifier)
        cached = self.store.inspection(identifier)
        if cached is None:
            raw_hex = request.body.get("bytes_hex")
            data = decode_bytes_hex(raw_hex) if raw_hex is not None else b""
            max_rows = _as_int(request.query.get("max_rows"), 32)
            rows = self.dumper.rows(data, max_rows=max(0, max_rows))
            cached = InspectionResult(
                evidence_id=record.id,
                hex_rows=rows,
                strings=self.extractor.scan(data),
                verifications=self.verifier.verify_record(record, data),
                custody=self.store.custody_for(identifier),
                generated_at=self.clock.iso(),
            )
            self.store.cache_inspection(cached)
        payload = cached.to_dict()
        payload["summary"] = cached.summary()
        return ok(payload, self._meta(request, 1, 1, etag=weak_etag(cached.generated_at)))

    def custody(self, request: EvidenceRequest, identifier: str) -> dict[str, Any]:
        request.require_gate()
        request.require(Capability.READ)
        record = self.store.get(identifier)
        entries: Sequence[CustodyEntry] = self.store.custody_for(identifier)
        graph = CustodyGraph.from_entries(record.id, entries)
        verification = graph.verify()
        return ok(
            {
                "evidence_id": record.id,
                "entries": [entry.to_dict() for entry in entries],
                "verification": verification.to_dict(),
            },
            self._meta(request, 1, 1, etag=weak_etag(graph.last_hash)),
        )

    def manifest(self, request: EvidenceRequest) -> dict[str, Any]:
        request.require_gate()
        request.require(Capability.EXPORT)
        payload = self.store.export_manifest()
        return ok(payload, self._meta(request, 1, 1, etag=weak_etag(payload["generated_at"])))

    def dispatch(self, request: EvidenceRequest) -> dict[str, Any]:
        """Route a request to the correct handler, converting errors to envelopes."""
        try:
            method = request.method.upper()
            path = request.path.rstrip("/") or ROUTE_PREFIX
            if method == "GET" and path == ROUTE_PREFIX:
                return self.list_evidence(request)
            if method == "POST" and path == ROUTE_PREFIX:
                return self.create_evidence(request)
            if method == "GET" and path.startswith(f"{ROUTE_PREFIX}/"):
                identifier = path[len(ROUTE_PREFIX) + 1 :].split("/")[0]
                suffix = path[len(ROUTE_PREFIX) + 1 + len(identifier) :].strip("/")
                if not identifier:
                    raise ApiError(ErrorCode.NOT_FOUND, "missing evidence id")
                if suffix == "inspect":
                    return self.inspect(request, identifier)
                if suffix == "custody":
                    return self.custody(request, identifier)
                if suffix == "manifest":
                    return self.manifest(request)
                return self.get_evidence(request, identifier)
            if method == "GET" and path == "/evidence-manifest":
                return self.manifest(request)
            raise ApiError(ErrorCode.NOT_FOUND, f"unknown route: {request.path}")
        except ApiError as exc:
            return fail(exc)
        except StoreError as exc:
            return fail(ApiError(ErrorCode.NOT_FOUND, str(exc)))
        except ValidationError as exc:
            return fail(ApiError(ErrorCode.INVALID_INPUT, str(exc)))
        except (ValueError, TypeError, IndexError) as exc:
            return fail(ApiError(ErrorCode.INVALID_INPUT, str(exc)))


_DEFAULT_API = EvidenceApi()


def handle_get(request: EvidenceRequest) -> dict[str, Any]:
    """Registry handler for ``GET /api/v4/evidence``."""
    return _DEFAULT_API.dispatch(request)


def handle_post(request: EvidenceRequest) -> dict[str, Any]:
    """Registry handler for ``POST /api/v4/evidence``."""
    return _DEFAULT_API.dispatch(request)


def register(api: RouteRegistry | object) -> None:
    """Register evidence routes on any registry exposing ``register``."""
    registrar = getattr(api, "register", None)
    if callable(registrar):
        for prefix, name, handler in (
            (ROUTE_PREFIX, ROUTE_NAME, handle_get),
            (f"{ROUTE_PREFIX}/create", f"{ROUTE_NAME}-create", handle_post),
        ):
            with contextlib.suppress(ValueError):
                registrar(prefix, name, handler)
        return
    for prefix, name, handler in (
        (ROUTE_PREFIX, ROUTE_NAME, handle_get),
        (f"{ROUTE_PREFIX}/create", f"{ROUTE_NAME}-create", handle_post),
    ):
        if global_registry().get(f"/api/v4{prefix}") is None:
            register_routes(prefix, name, handler)
