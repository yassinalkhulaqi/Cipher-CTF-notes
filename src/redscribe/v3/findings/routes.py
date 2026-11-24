"""API v3 route handlers for the findings namespace."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from redscribe.v3.api import (
    DEFAULT_PAGE_SIZE,
    IdempotencyGuard,
    V3Error,
    V3ErrorCode,
    compute_etag,
    etag_matches,
    filter_hash,
    optional_str,
    optional_tags,
    paginate,
    require_choice,
    require_str,
)
from redscribe.v3.api.pagination import PageRequest
from redscribe.v3.findings.cvss_v4 import (
    SeverityBand,
    cvss_v4_breakdown,
    cvss_v4_score,
    parse_cvss_v4_vector,
)
from redscribe.v3.findings.duplicates import DEFAULT_THRESHOLD
from redscribe.v3.findings.lifecycle import ACTIONS, transition_graph
from redscribe.v3.findings.mappings import cwe_catalog, lookup_cwe, search_cwe
from redscribe.v3.findings.models import RetestVerdict, TaskStatus
from redscribe.v3.findings.service import (
    FindingConflictError,
    FindingService,
    FindingServiceError,
)

F = TypeVar("F", bound=Callable[..., dict[str, Any]])


def _error_for(exc: Exception) -> V3Error:
    if isinstance(exc, FindingServiceError):
        return V3Error.not_found("finding")
    if isinstance(exc, FindingConflictError):
        return V3Error(V3ErrorCode.CONFLICT, str(exc))
    if isinstance(exc, ValueError):
        return V3Error.invalid("request", str(exc))
    return V3Error(V3ErrorCode.INTERNAL, "Unexpected finding service error")


def guard(handler: F) -> F:
    """Translate domain errors into stable V3 API errors."""
    from functools import wraps

    @wraps(handler)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return handler(*args, **kwargs)
        except V3Error:
            raise
        except Exception as error:
            raise _error_for(error) from error

    return wrapped  # type: ignore[return-value]


class FindingRoutes:
    """Stateless handlers bound to one finding service."""

    def __init__(self, service: FindingService | None = None) -> None:
        self.service = service or FindingService()
        self.idempotency = IdempotencyGuard()

    def _actor(self, headers: Mapping[str, str]) -> str:
        return headers.get("X-Actor", "local")[:120] or "local"

    @guard
    def create(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Create a draft finding; repeated idempotency keys return the first result."""
        key = headers.get("Idempotency-Key", "")
        if key:
            result, replayed = self.idempotency.execute(
                key, body, lambda: self._create(body, headers)
            )
            return {**result, "replayed": replayed}
        return self._create(body, headers)

    def _create(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        from redscribe.v3.entities.types import EntityId, EntityKind, EntityRef

        target_raw = optional_str(body, "target_ref", limit=240)
        target_ref = EntityRef(EntityId.parse(target_raw)) if target_raw else None
        if target_ref is not None and target_ref.kind is EntityKind.FINDING:
            raise V3Error.invalid("target_ref", "A finding cannot target itself")
        finding = self.service.create(
            title=require_str(body, "title", limit=240),
            summary=optional_str(body, "summary", limit=4000),
            vector=optional_str(body, "vector", limit=400),
            owner=optional_str(body, "owner", limit=120),
            target_ref=target_ref,
            cwes=tuple(body.get("cwes", ())),
            cves=tuple(body.get("cves", ())),
            tags=optional_tags(body),
            actor=self._actor(headers),
        )
        return {"finding": finding.as_dict()}

    @guard
    def get(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Get a single finding."""
        return {"finding": self.service.get(require_str(body, "ref", limit=240)).as_dict()}

    @guard
    def detail(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Get a full editor payload for one finding."""
        return self.service.detail(require_str(body, "ref", limit=240))

    @guard
    def list(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """List findings with cursor pagination, filters, and a stable ETag."""
        page = PageRequest.parse(
            offset=body.get("offset"),
            size=body.get("size", DEFAULT_PAGE_SIZE),
            cursor=optional_str(body, "cursor", limit=400),
        )
        state = optional_str(body, "state", limit=40)
        severity = optional_str(body, "severity", limit=40)
        if state:
            from redscribe.v3.findings.models import FindingState

            require_choice(body, "state", tuple(item.value for item in FindingState))
        if severity:
            require_choice(body, "severity", tuple(item.value for item in SeverityBand))
        threat_raw = body.get("has_threat")
        has_threat = None if threat_raw is None else bool(threat_raw)
        items = self.service.list(
            query=optional_str(body, "query", limit=240),
            state=state,
            severity=severity,
            owner=optional_str(body, "owner", limit=120),
            tag=optional_str(body, "tag", limit=80),
            vector_has_threat=has_threat,
        )
        filter_key = filter_hash(
            optional_str(body, "query", limit=240),
            tuple(value for value in (state, severity) if value),
        )
        window, page_meta, next_cursor = paginate(items, page, filter_hash=filter_key)
        etag = compute_etag([item.as_dict() for item in window])
        if_none_match = headers.get("If-None-Match", "")
        if if_none_match and etag_matches(if_none_match, etag):
            return {"items": [], "not_modified": True, "etag": etag, "page": page_meta.as_dict()}
        return {
            "items": [item.as_dict() for item in window],
            "next_cursor": next_cursor,
            "etag": etag,
            "page": page_meta.as_dict(),
            "filter_hash": filter_key,
        }

    @guard
    def update(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Update finding metadata."""
        fields: dict[str, Any] = {}
        for key in ("title", "summary", "owner"):
            if key in body:
                fields[key] = require_str(body, key, limit=240 if key == "title" else 4000)
        if "tags" in body:
            fields["tags"] = optional_tags(body)
        finding = self.service.update(
            require_str(body, "ref", limit=240), actor=self._actor(headers), **fields
        )
        return {"finding": finding.as_dict()}

    @guard
    def score(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Set a CVSS v4 vector on a finding."""
        finding = self.service.set_score(
            require_str(body, "ref", limit=240),
            require_str(body, "vector", limit=400),
            actor=self._actor(headers),
        )
        return {"finding": finding.as_dict(), "score": cvss_v4_breakdown(finding.vector)}

    @guard
    def score_preview(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Score a vector without changing a finding."""
        return cvss_v4_breakdown(require_str(body, "vector", limit=400))

    @guard
    def severity_bands(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """List severity bands and their score ranges."""
        return {
            "bands": [
                {
                    "value": band.value,
                    "minimum": minimum,
                    "rank": band.rank,
                    "color": band.color_token,
                }
                for band, minimum in (
                    (SeverityBand.NONE, 0.0),
                    (SeverityBand.LOW, 0.1),
                    (SeverityBand.MEDIUM, 4.0),
                    (SeverityBand.HIGH, 7.0),
                    (SeverityBand.CRITICAL, 9.0),
                )
            ]
        }

    @guard
    def actions(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Return the lifecycle graph and actions available on one finding."""
        ref = optional_str(body, "ref", limit=240)
        return {
            "graph": transition_graph(),
            "actions": list(ACTIONS),
            "available": list(self.service.available_actions(ref)) if ref else [],
        }

    @guard
    def transition(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Apply a guarded lifecycle transition."""
        finding, record = self.service.transition(
            require_str(body, "ref", limit=240),
            require_choice(body, "action", ACTIONS),
            actor=self._actor(headers),
            note=optional_str(body, "note", limit=1000),
        )
        return {"finding": finding.as_dict(), "transition": record.as_dict()}

    @guard
    def remediation_add(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Add remediation tasks from a title or pasted checklist."""
        finding = self.service.add_remediation(
            require_str(body, "ref", limit=240),
            task_id=optional_str(body, "task_id", limit=120),
            title=optional_str(body, "title", limit=240),
            detail=optional_str(body, "detail", limit=2000),
            owner=optional_str(body, "owner", limit=120),
            lines=optional_str(body, "lines", limit=8000),
            actor=self._actor(headers),
        )
        return {"remediation": self.service.remediation(finding.ref_string)}

    @guard
    def remediation_update(
        self, body: dict[str, Any], headers: Mapping[str, str]
    ) -> dict[str, Any]:
        """Change a checklist item's status."""
        finding = self.service.update_remediation_task(
            require_str(body, "ref", limit=240),
            require_str(body, "task_id", limit=120),
            require_choice(body, "status", tuple(item.value for item in TaskStatus)),
            proof_ref=optional_str(body, "proof_ref", limit=240),
            actor=self._actor(headers),
        )
        return {"remediation": self.service.remediation(finding.ref_string)}

    @guard
    def remediation(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Read a finding's remediation checklist."""
        return {"remediation": self.service.remediation(require_str(body, "ref", limit=240))}

    @guard
    def retest(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Record a retest verdict with optional proof references."""
        record = self.service.record_retest(
            require_str(body, "ref", limit=240),
            verdict=require_choice(body, "verdict", tuple(item.value for item in RetestVerdict)),
            tested_by=require_str(body, "tested_by", limit=120),
            notes=optional_str(body, "notes", limit=4000),
            proof_refs=tuple(body.get("proof_refs", ())),
            follow_up=optional_str(body, "follow_up", limit=2000),
            actor=self._actor(headers),
        )
        return {"retest": record.as_dict()}

    @guard
    def proof_add(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Attach a proof block to a finding."""
        block = self.service.add_proof(
            require_str(body, "ref", limit=240),
            block_id=require_str(body, "block_id", limit=120),
            target=require_str(body, "target", limit=240),
            excerpt=optional_str(body, "excerpt", limit=8000),
            role=optional_str(body, "role", limit=40) or "supporting",
            label=optional_str(body, "label", limit=240),
            actor=self._actor(headers),
        )
        return {"proof": block.as_dict()}

    @guard
    def proof_report(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Check proof-chain integrity."""
        return {"proof": self.service.proof_report(require_str(body, "ref", limit=240))}

    @guard
    def duplicates(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Suggest duplicate findings using V2 fingerprinting plus V3 controls."""
        raw_threshold = body.get("threshold", DEFAULT_THRESHOLD)
        try:
            threshold = float(raw_threshold)
        except (TypeError, ValueError) as error:
            raise V3Error.invalid("threshold", "Must be a number") from error
        return self.service.duplicate_report(
            require_str(body, "ref", limit=240), threshold=threshold
        )

    @guard
    def mark_duplicate(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Link a finding to its canonical duplicate."""
        finding = self.service.mark_duplicate(
            require_str(body, "ref", limit=240),
            require_str(body, "canonical", limit=240),
            actor=self._actor(headers),
            note=optional_str(body, "note", limit=1000),
        )
        return {"finding": finding.as_dict()}

    @guard
    def cwe_catalog(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Return CWE catalog entries, optionally filtered by search text."""
        query = optional_str(body, "query", limit=120)
        category = optional_str(body, "category", limit=120)
        entries = search_cwe(query, category=category) if query or category else cwe_catalog()
        return {"entries": [entry.as_dict() for entry in entries]}

    @guard
    def cwe_lookup(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Resolve one CWE identifier."""
        return {"resolution": lookup_cwe(require_str(body, "cwe_id", limit=40)).as_dict()}

    @guard
    def summary(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Return studio-wide counters."""
        return self.service.summary()

    @guard
    def validate_vector(self, body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        """Validate a vector string and return its final score."""
        vector = parse_cvss_v4_vector(require_str(body, "vector", limit=400))
        score = cvss_v4_score(vector)
        return {
            "valid": True,
            "vector": vector.render(),
            "score": score,
            "severity": SeverityBand.for_score(score).value,
        }

    def handlers(self) -> dict[str, Callable[[dict[str, Any], Mapping[str, str]], dict[str, Any]]]:
        """Return action-to-handler bindings for namespace registration."""
        return {
            "create": self.create,
            "get": self.get,
            "detail": self.detail,
            "list": self.list,
            "update": self.update,
            "score": self.score,
            "score_preview": self.score_preview,
            "severity_bands": self.severity_bands,
            "actions": self.actions,
            "transition": self.transition,
            "remediation_add": self.remediation_add,
            "remediation_update": self.remediation_update,
            "remediation": self.remediation,
            "retest": self.retest,
            "proof_add": self.proof_add,
            "proof_report": self.proof_report,
            "duplicates": self.duplicates,
            "mark_duplicate": self.mark_duplicate,
            "cwe_catalog": self.cwe_catalog,
            "cwe_lookup": self.cwe_lookup,
            "summary": self.summary,
            "validate_vector": self.validate_vector,
        }


__all__ = ["FindingRoutes", "guard"]
