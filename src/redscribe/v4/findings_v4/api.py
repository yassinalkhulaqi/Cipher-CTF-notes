"""HTTP-facing handlers for the findings v4 slice.

Handlers return v4 envelopes built from the shared contracts and expose a small
synchronous dispatch surface so they can be exercised without a running web
server. Every request is capability-checked, paginated where it returns a list,
and translated into a structured error envelope on failure.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.contracts import (
    ApiError,
    Capability,
    CapabilitySet,
    ErrorCode,
    PageMeta,
    fail,
    new_entity_id,
    ok,
)
from redscribe.v4.pagination import etag_matches, paginate, weak_etag

from .service import FindingError, FindingService
from .types import (
    DEFAULT_VECTOR_TEXT,
    Finding,
    LifecycleState,
    RetestVerdict,
    Severity,
)

ERROR_CODE_MAP: dict[str, ErrorCode] = {
    "not_found": ErrorCode.NOT_FOUND,
    "forbidden": ErrorCode.FORBIDDEN,
    "illegal_transition": ErrorCode.CONFLICT,
    "invalid_vector": ErrorCode.INVALID_INPUT,
    "invalid_state": ErrorCode.INVALID_INPUT,
    "invalid_due": ErrorCode.INVALID_INPUT,
    "invalid_verdict": ErrorCode.INVALID_INPUT,
}
UPDATE_ACTIONS: frozenset[str] = frozenset({"score", "transition", "remediation", "retest"})


@dataclass(frozen=True, slots=True)
class FindingRequest:
    """A transport-agnostic request value for the findings API."""

    method: str
    path: str = "/findings"
    query: Mapping[str, str] = field(default_factory=dict)
    body: Mapping[str, Any] = field(default_factory=dict)
    capabilities: CapabilitySet = field(default_factory=CapabilitySet)
    request_id: str = field(default_factory=new_entity_id)
    if_none_match: str = ""


@dataclass(frozen=True, slots=True)
class FindingResponse:
    """A status code paired with a v4 envelope."""

    status: int
    payload: dict[str, Any]


Handler = Callable[[FindingRequest], tuple[int, dict[str, Any]]]


class FindingApi:
    """Capability-checked handlers that return v4 envelopes."""

    def __init__(
        self,
        service: FindingService,
        capabilities: CapabilitySet | None = None,
    ) -> None:
        self.service = service
        self.capabilities = capabilities or CapabilitySet.full()

    def _caps(self, request: FindingRequest) -> CapabilitySet:
        return request.capabilities if request.capabilities.granted else self.capabilities

    def _run(self, request: FindingRequest, handler: Handler) -> FindingResponse:
        try:
            gate = FeatureGate(self._caps(request))
            gate.require(FeatureFlag.CVSS_V4)
            status, payload = handler(request)
            return FindingResponse(status=status, payload=payload)
        except ApiError as exc:
            return FindingResponse(status=exc.code.http_status, payload=fail(exc))
        except FindingError as exc:
            code = ERROR_CODE_MAP.get(exc.code, ErrorCode.INVALID_INPUT)
            envelope = fail(ApiError(code=code, message=exc.message, details=(exc.code,)))
            return FindingResponse(status=code.http_status, payload=envelope)
        except PermissionError as exc:
            envelope = fail(ApiError(code=ErrorCode.FORBIDDEN, message=str(exc)))
            return FindingResponse(status=ErrorCode.FORBIDDEN.http_status, payload=envelope)

    def dispatch(self, request: FindingRequest) -> FindingResponse:
        """Dispatch a request by HTTP method."""
        method = request.method.upper()
        if method == "GET":
            if request.query.get("view") == "snapshot":
                return self.snapshot(request)
            return self.list_findings(request)
        if method == "POST":
            return self.create_finding(request)
        if method == "PUT":
            return self.update_finding(request)

        def unsupported(_: FindingRequest) -> tuple[int, dict[str, Any]]:
            raise ApiError(ErrorCode.INVALID_INPUT, f"unsupported method: {method}")

        return self._run(request, unsupported)

    @staticmethod
    def _int_param(
        query: Mapping[str, str], name: str, default: int, minimum: int, maximum: int
    ) -> int:
        raw = query.get(name)
        if raw is None or raw == "":
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, f"{name} must be an integer") from exc
        if not minimum <= value <= maximum:
            raise ApiError(
                ErrorCode.INVALID_INPUT,
                f"{name} must be between {minimum} and {maximum}",
            )
        return value

    @staticmethod
    def _severity_param(raw: str) -> Severity:
        try:
            return Severity(raw.lower())
        except ValueError as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, f"unknown severity: {raw}") from exc

    @staticmethod
    def _state_param(raw: str) -> LifecycleState:
        try:
            return LifecycleState(raw.lower())
        except ValueError as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, f"unknown lifecycle state: {raw}") from exc

    @staticmethod
    def _verdict_param(raw: str) -> RetestVerdict:
        try:
            return RetestVerdict(raw.lower())
        except ValueError as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, f"unknown retest verdict: {raw}") from exc

    def _meta(
        self,
        request: FindingRequest,
        page: int = 1,
        page_size: int = 1,
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

    def _filtered(self, query: Mapping[str, str]) -> list[Finding]:
        severity_raw = query.get("severity")
        state_raw = query.get("state")
        severity = self._severity_param(severity_raw) if severity_raw else None
        state = self._state_param(state_raw) if state_raw else None
        if severity is not None and state is not None:
            by_severity = {item.id for item in self.service.store.by_severity(severity)}
            return [item for item in self.service.store.by_state(state) if item.id in by_severity]
        if severity is not None:
            return list(self.service.store.by_severity(severity))
        if state is not None:
            return list(self.service.store.by_state(state))
        return self.service.store.all()

    def _list(self, request: FindingRequest) -> tuple[int, dict[str, Any]]:
        self._caps(request).require(Capability.READ)
        page = self._int_param(request.query, "page", 1, 1, 1000)
        page_size = self._int_param(request.query, "page_size", 50, 1, 500)
        result = paginate(self._filtered(request.query), page, page_size)
        etag = weak_etag(result.etag)
        meta = self._meta(request, page, page_size, etag, result.next_cursor)
        if request.if_none_match and etag_matches(request.if_none_match, etag):
            return 304, ok(None, meta)
        return 200, ok(result.to_dict(serialize=lambda item: item.to_dict()), meta)

    def list_findings(self, request: FindingRequest) -> FindingResponse:
        """GET /findings — list findings with filters and cursor pagination."""
        return self._run(request, self._list)

    def _create(self, request: FindingRequest) -> tuple[int, dict[str, Any]]:
        self._caps(request).require(Capability.WRITE)
        body = request.body
        title = str(body.get("title", ""))
        if not title.strip():
            raise ApiError(ErrorCode.INVALID_INPUT, "title is required")
        vector_text = str(body.get("vector", DEFAULT_VECTOR_TEXT))
        description = str(body.get("description", ""))
        finding = self.service.create(title, vector_text, description)
        score = self.service.score(finding.id)
        data = {"finding": finding.to_dict(), "score": score.to_dict()}
        return 201, ok(data, self._meta(request))

    def create_finding(self, request: FindingRequest) -> FindingResponse:
        """POST /findings — create and score a new finding."""
        return self._run(request, self._create)

    def _update(self, request: FindingRequest) -> tuple[int, dict[str, Any]]:
        self._caps(request).require(Capability.WRITE)
        body = request.body
        finding_id = str(body.get("id", ""))
        if not finding_id:
            raise ApiError(ErrorCode.INVALID_INPUT, "id is required")
        action = str(body.get("action", "score"))
        if action not in UPDATE_ACTIONS:
            raise ApiError(ErrorCode.INVALID_INPUT, f"unknown action: {action}")
        if action == "score":
            score = self.service.score(finding_id)
            finding = self.service.get(finding_id)
            data: dict[str, Any] = {
                "finding": finding.to_dict(),
                "score": score.to_dict(),
            }
        elif action == "transition":
            raw_state = body.get("state")
            if not isinstance(raw_state, str):
                raise ApiError(ErrorCode.INVALID_INPUT, "state is required")
            finding = self.service.transition(finding_id, self._state_param(raw_state))
            data = {"finding": finding.to_dict()}
        elif action == "remediation":
            raw_due = body.get("due")
            if not isinstance(raw_due, str):
                raise ApiError(ErrorCode.INVALID_INPUT, "due is required")
            finding = self.service.assign_remediation(
                finding_id, raw_due, str(body.get("notes", ""))
            )
            data = {"finding": finding.to_dict()}
        else:
            raw_verdict = body.get("verdict")
            if not isinstance(raw_verdict, str):
                raise ApiError(ErrorCode.INVALID_INPUT, "verdict is required")
            record = self.service.retest(
                finding_id,
                self._verdict_param(raw_verdict),
                str(body.get("note", "")),
            )
            data = {
                "retest": record.to_dict(),
                "finding": self.service.get(finding_id).to_dict(),
            }
        return 200, ok(data, self._meta(request))

    def update_finding(self, request: FindingRequest) -> FindingResponse:
        """PUT /findings — score, transition, assign remediation or retest."""
        return self._run(request, self._update)

    def _snapshot(self, request: FindingRequest) -> tuple[int, dict[str, Any]]:
        self._caps(request).require(Capability.EXPORT)
        return 200, ok(self.service.store.snapshot(), self._meta(request))

    def snapshot(self, request: FindingRequest) -> FindingResponse:
        """GET /findings?view=snapshot — export a JSON-safe snapshot."""
        return self._run(request, self._snapshot)

    def register(self, registry: RouteRegistry) -> None:
        """Register the findings route on a v4 route registry."""
        registry.register("/findings", "findings-v4", self.dispatch)
