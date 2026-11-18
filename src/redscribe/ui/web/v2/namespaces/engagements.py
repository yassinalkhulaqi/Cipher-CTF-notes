"""Additive v2 API namespace for engagement-core operations.

The namespace never edits shared route tables. ``register(api)`` discovers the
host registry's ``_register`` hook and adds all engagement routes with stable
metadata so the existing v2 schema, idempotency, and audit mechanisms continue
to work unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.ui.web.v2.contracts import (
    MAX_PAGE_SIZE,
    V2Error,
    V2ErrorCode,
    compute_etag,
    optional_int,
    optional_str,
    paginate,
    require_int,
    require_str,
)
from redscribe.ui.web.v2.routes import RouteResult
from redscribe.v2.engagements.errors import EngagementError
from redscribe.v2.engagements.repositories import RepositoryError
from redscribe.v2.engagements.services import EngagementService

Handler = Callable[[dict[str, Any]], RouteResult]

DEFAULT_LIMIT = 50


@dataclass(frozen=True, slots=True)
class RouteSpec:
    """Declarative metadata for one engagement namespace route."""

    name: str
    handler: Handler
    description: str
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    mutating: bool = False
    entity_type: str = ""


def _to_v2_error(error: EngagementError | RepositoryError) -> V2Error:
    if isinstance(error, EngagementError):
        return V2Error(
            error.status,
            error.code.value,
            error.message,
            details=error.details,
        )
    return V2Error(404, V2ErrorCode.NOT_FOUND, str(error))


def _page_limit(body: Mapping[str, Any]) -> int:
    limit = optional_int(body, "limit")
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise V2Error(
            400,
            V2ErrorCode.INVALID_REQUEST,
            f"limit must be between 1 and {MAX_PAGE_SIZE}",
            details={"field": "limit"},
        )
    return limit


def _fields(body: Mapping[str, Any], names: Sequence[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in names:
        if name in body and body[name] is not None:
            result[name] = body[name]
    return result


def _text_fields(body: Mapping[str, Any], names: Sequence[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in names:
        value = optional_str(body, name)
        if value is not None:
            result[name] = value
    return result


def _list_result(body: Mapping[str, Any], items: Sequence[Any]) -> RouteResult:
    page_items, page = paginate(
        list(items), cursor=optional_str(body, "cursor"), limit=_page_limit(body)
    )
    etag = compute_etag({"items": page_items, "page": page.as_dict()})
    return RouteResult(list(page_items), page=page, etag=etag)


def _detail_result(data: Mapping[str, Any], *, status: int = 200) -> RouteResult:
    value = dict(data)
    return RouteResult(value, etag=compute_etag(value), status=status)


def _guarded(handler: Handler) -> Handler:
    def wrapped(body: dict[str, Any]) -> RouteResult:
        try:
            return handler(body)
        except EngagementError as exc:
            raise _to_v2_error(exc) from exc
        except RepositoryError as exc:
            raise _to_v2_error(exc) from exc

    return wrapped


class EngagementNamespace:
    """Route handlers bound to one engagement service instance."""

    def __init__(self, service: EngagementService | None = None) -> None:
        self.service = service if service is not None else EngagementService()

    def register(self, api: object) -> None:
        """Register every namespace route on a v2 API registry."""
        registrar = getattr(api, "_register", None)
        if not callable(registrar):
            raise TypeError("API registry does not expose a route registration hook")
        for spec in self.specs():
            registrar(
                spec.name,
                _guarded(spec.handler),
                spec.description,
                required=spec.required,
                optional=spec.optional,
                mutating=spec.mutating,
                entity_type=spec.entity_type,
            )

    def specs(self) -> tuple[RouteSpec, ...]:
        """Return the full route inventory for introspection and registration."""
        return (
            RouteSpec(
                "engagements.list",
                self.engagements_list,
                "List engagements with status, kind, owner, and text filters.",
                optional=("status", "kind", "owner", "query", "cursor", "limit"),
            ),
            RouteSpec(
                "engagements.get",
                self.engagements_get,
                "Return one engagement with relationship counts and actions.",
                required=("id",),
            ),
            RouteSpec(
                "engagements.create",
                self.engagements_create,
                "Create an engagement with validation and a stable key.",
                required=("name",),
                optional=(
                    "key",
                    "client",
                    "description",
                    "kind",
                    "status",
                    "owner",
                    "start_date",
                    "end_date",
                    "tags",
                ),
                mutating=True,
                entity_type="engagement",
            ),
            RouteSpec(
                "engagements.update",
                self.engagements_update,
                "Update engagement metadata.",
                required=("id",),
                optional=(
                    "name",
                    "key",
                    "client",
                    "description",
                    "kind",
                    "status",
                    "owner",
                    "start_date",
                    "end_date",
                    "tags",
                ),
                mutating=True,
                entity_type="engagement",
            ),
            RouteSpec(
                "engagements.transition",
                self.engagements_transition,
                "Apply an engagement lifecycle action.",
                required=("id", "action"),
                optional=("note", "report_signed_off"),
                mutating=True,
                entity_type="engagement",
            ),
            RouteSpec(
                "engagements.delete",
                self.engagements_delete,
                "Delete an engagement and its dependent records.",
                required=("id",),
                mutating=True,
                entity_type="engagement",
            ),
            RouteSpec(
                "engagements.dashboard",
                self.engagements_dashboard,
                "Return rollup, coverage, risk, and activity widgets.",
                required=("id",),
            ),
            RouteSpec(
                "engagements.portfolio",
                self.engagements_portfolio,
                "Return portfolio-wide rollup data.",
                optional=("cursor", "limit"),
            ),
            RouteSpec(
                "engagements.workflows",
                self.engagements_workflows,
                "Return all workflow state machines and allowed actions.",
            ),
            RouteSpec(
                "engagements.options",
                self.engagements_options,
                "Return enum values and form options.",
            ),
            RouteSpec(
                "engagements.activity",
                self.engagements_activity,
                "Return recent engagement activity.",
                required=("id",),
                optional=("limit", "cursor"),
            ),
            RouteSpec(
                "engagements.seed_demo",
                self.engagements_seed_demo,
                "Seed one deterministic demo engagement when empty.",
                mutating=True,
                entity_type="engagement",
            ),
            RouteSpec(
                "scope.list",
                self.scope_list,
                "List scope rules for an engagement.",
                required=("engagement_id",),
                optional=("cursor", "limit"),
            ),
            RouteSpec(
                "scope.add",
                self.scope_add,
                "Add an include or exclude scope rule.",
                required=("engagement_id", "value"),
                optional=("kind", "action", "notes"),
                mutating=True,
                entity_type="scope_rule",
            ),
            RouteSpec(
                "scope.remove",
                self.scope_remove,
                "Remove one scope rule.",
                required=("engagement_id", "id"),
                mutating=True,
                entity_type="scope_rule",
            ),
            RouteSpec(
                "scope.evaluate",
                self.scope_evaluate,
                "Evaluate a value against engagement scope rules.",
                required=("engagement_id", "value"),
            ),
            RouteSpec(
                "scope.import",
                self.scope_import,
                "Import scope rules while skipping exact duplicates.",
                required=("engagement_id", "rules"),
                mutating=True,
                entity_type="scope_rule",
            ),
            RouteSpec(
                "targets.list",
                self.targets_list,
                "List targets with scope, status, criticality, and text filters.",
                required=("engagement_id",),
                optional=("scope_status", "status", "criticality", "query", "cursor", "limit"),
            ),
            RouteSpec(
                "targets.get",
                self.targets_get,
                "Return one target.",
                required=("id",),
            ),
            RouteSpec(
                "targets.create",
                self.targets_create,
                "Create a target with automatic kind detection.",
                required=("engagement_id", "value"),
                optional=(
                    "name",
                    "kind",
                    "description",
                    "status",
                    "scope_status",
                    "criticality",
                    "tags",
                    "notes",
                ),
                mutating=True,
                entity_type="target",
            ),
            RouteSpec(
                "targets.update",
                self.targets_update,
                "Update target metadata.",
                required=("id",),
                optional=(
                    "value",
                    "name",
                    "kind",
                    "description",
                    "status",
                    "scope_status",
                    "criticality",
                    "tags",
                    "notes",
                ),
                mutating=True,
                entity_type="target",
            ),
            RouteSpec(
                "targets.transition",
                self.targets_transition,
                "Apply a target lifecycle action.",
                required=("id", "action"),
                optional=("reason",),
                mutating=True,
                entity_type="target",
            ),
            RouteSpec(
                "targets.scope_transition",
                self.targets_scope_transition,
                "Apply a manual scope review action.",
                required=("id", "action"),
                mutating=True,
                entity_type="target",
            ),
            RouteSpec(
                "targets.remove",
                self.targets_remove,
                "Delete a target and its dependent records.",
                required=("id",),
                mutating=True,
                entity_type="target",
            ),
            RouteSpec(
                "targets.coverage",
                self.targets_coverage,
                "Return coverage scores and gaps for an engagement.",
                required=("engagement_id",),
            ),
            RouteSpec(
                "assets.list",
                self.assets_list,
                "List assets with target and text filters.",
                required=("engagement_id",),
                optional=("target_id", "query", "cursor", "limit"),
            ),
            RouteSpec(
                "assets.get",
                self.assets_get,
                "Return one asset.",
                required=("id",),
            ),
            RouteSpec(
                "assets.create",
                self.assets_create,
                "Create an asset attached to a target.",
                required=("engagement_id", "target_id", "name"),
                optional=("kind", "identifier", "status", "criticality", "owner", "notes"),
                mutating=True,
                entity_type="asset",
            ),
            RouteSpec(
                "assets.update",
                self.assets_update,
                "Update asset metadata.",
                required=("id",),
                optional=(
                    "name",
                    "kind",
                    "identifier",
                    "status",
                    "criticality",
                    "owner",
                    "notes",
                    "target_id",
                ),
                mutating=True,
                entity_type="asset",
            ),
            RouteSpec(
                "assets.remove",
                self.assets_remove,
                "Delete an asset and clear references.",
                required=("id",),
                mutating=True,
                entity_type="asset",
            ),
            RouteSpec(
                "services.list",
                self.services_list,
                "List services with target, asset, port, and status filters.",
                required=("engagement_id",),
                optional=("target_id", "asset_id", "status", "port", "cursor", "limit"),
            ),
            RouteSpec(
                "services.get",
                self.services_get,
                "Return one service.",
                required=("id",),
            ),
            RouteSpec(
                "services.create",
                self.services_create,
                "Create a service on a target.",
                required=("engagement_id", "target_id", "name"),
                optional=("asset_id", "port", "protocol", "product", "version", "status", "notes"),
                mutating=True,
                entity_type="service",
            ),
            RouteSpec(
                "services.update",
                self.services_update,
                "Update service metadata.",
                required=("id",),
                optional=(
                    "name",
                    "port",
                    "protocol",
                    "product",
                    "version",
                    "status",
                    "notes",
                    "target_id",
                    "asset_id",
                ),
                mutating=True,
                entity_type="service",
            ),
            RouteSpec(
                "services.transition",
                self.services_transition,
                "Apply a service verification action.",
                required=("id", "action"),
                mutating=True,
                entity_type="service",
            ),
            RouteSpec(
                "services.remove",
                self.services_remove,
                "Delete a service and clear references.",
                required=("id",),
                mutating=True,
                entity_type="service",
            ),
            RouteSpec(
                "credentials.list",
                self.credentials_list,
                "List credentials with masked secret references.",
                required=("engagement_id",),
                optional=("target_id", "status", "kind", "cursor", "limit"),
            ),
            RouteSpec(
                "credentials.get",
                self.credentials_get,
                "Return one credential with a masked secret reference.",
                required=("id",),
            ),
            RouteSpec(
                "credentials.create",
                self.credentials_create,
                "Store a credential reference.",
                required=("engagement_id", "target_id", "secret_ref"),
                optional=("username", "kind", "status", "rotated_at", "notes"),
                mutating=True,
                entity_type="credential",
            ),
            RouteSpec(
                "credentials.update",
                self.credentials_update,
                "Update credential metadata.",
                required=("id",),
                optional=(
                    "username",
                    "secret_ref",
                    "kind",
                    "status",
                    "target_id",
                    "rotated_at",
                    "notes",
                ),
                mutating=True,
                entity_type="credential",
            ),
            RouteSpec(
                "credentials.rotate",
                self.credentials_rotate,
                "Rotate a credential and update its reference.",
                required=("id",),
                optional=("secret_ref",),
                mutating=True,
                entity_type="credential",
            ),
            RouteSpec(
                "credentials.transition",
                self.credentials_transition,
                "Apply a credential validation action.",
                required=("id", "action"),
                mutating=True,
                entity_type="credential",
            ),
            RouteSpec(
                "credentials.remove",
                self.credentials_remove,
                "Delete a credential.",
                required=("id",),
                mutating=True,
                entity_type="credential",
            ),
            RouteSpec(
                "findings.list",
                self.findings_list,
                "List findings with severity, status, confidence, and text filters.",
                required=("engagement_id",),
                optional=(
                    "status",
                    "severity",
                    "confidence",
                    "target_id",
                    "owner",
                    "query",
                    "tag",
                    "cursor",
                    "limit",
                ),
            ),
            RouteSpec(
                "findings.get",
                self.findings_get,
                "Return one finding with CVSS and duplicate data.",
                required=("id",),
            ),
            RouteSpec(
                "findings.create",
                self.findings_create,
                "Create a finding with CVSS, CWE, CVE, and lifecycle fields.",
                required=("engagement_id", "title"),
                optional=(
                    "target_id",
                    "asset_id",
                    "service_id",
                    "summary",
                    "severity",
                    "confidence",
                    "cvss_vector",
                    "cwe",
                    "cwes",
                    "cves",
                    "status",
                    "duplicate_of",
                    "owner",
                    "impact",
                    "remediation",
                    "reproduction_steps",
                    "references",
                    "tags",
                ),
                mutating=True,
                entity_type="finding",
            ),
            RouteSpec(
                "findings.update",
                self.findings_update,
                "Update finding editor fields.",
                required=("id",),
                optional=(
                    "title",
                    "summary",
                    "severity",
                    "confidence",
                    "cvss_vector",
                    "cwe",
                    "cwes",
                    "cves",
                    "status",
                    "owner",
                    "impact",
                    "remediation",
                    "reproduction_steps",
                    "references",
                    "tags",
                    "target_id",
                    "asset_id",
                    "service_id",
                ),
                mutating=True,
                entity_type="finding",
            ),
            RouteSpec(
                "findings.transition",
                self.findings_transition,
                "Apply a finding lifecycle action with guards.",
                required=("id", "action"),
                optional=("note", "evidence", "duplicate_of", "retested"),
                mutating=True,
                entity_type="finding",
            ),
            RouteSpec(
                "findings.duplicate",
                self.findings_duplicate,
                "Mark one finding as a duplicate of another.",
                required=("id", "canonical_id"),
                mutating=True,
                entity_type="finding",
            ),
            RouteSpec(
                "findings.link_cluster",
                self.findings_link_cluster,
                "Link several findings to one canonical finding.",
                required=("canonical_id", "duplicate_ids"),
                mutating=True,
                entity_type="finding",
            ),
            RouteSpec(
                "findings.duplicates",
                self.findings_duplicates,
                "Return ranked duplicate candidates for a finding.",
                required=("id",),
                optional=("threshold",),
            ),
            RouteSpec(
                "findings.clusters",
                self.findings_clusters,
                "Return duplicate clusters for an engagement.",
                required=("engagement_id",),
                optional=("threshold",),
            ),
            RouteSpec(
                "findings.remove",
                self.findings_remove,
                "Delete a finding and clear duplicate links.",
                required=("id",),
                mutating=True,
                entity_type="finding",
            ),
        )

    # ------------------------------------------------------------------
    # Engagement handlers
    # ------------------------------------------------------------------

    def engagements_list(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.list_engagements(
            status=optional_str(body, "status") or "",
            kind=optional_str(body, "kind") or "",
            owner=optional_str(body, "owner") or "",
            query=optional_str(body, "query") or "",
        )
        return _list_result(body, items)

    def engagements_get(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.engagement_detail(require_int(body, "id")))

    def engagements_create(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            (
                "name",
                "key",
                "client",
                "description",
                "kind",
                "status",
                "owner",
                "start_date",
                "end_date",
                "tags",
            ),
        )
        return _detail_result(self.service.create_engagement(data), status=201)

    def engagements_update(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            (
                "name",
                "key",
                "client",
                "description",
                "kind",
                "status",
                "owner",
                "start_date",
                "end_date",
                "tags",
            ),
        )
        return _detail_result(self.service.update_engagement(require_int(body, "id"), data))

    def engagements_transition(self, body: dict[str, Any]) -> RouteResult:
        signed_off = body.get("report_signed_off", False)
        if not isinstance(signed_off, bool):
            raise V2Error(
                400,
                V2ErrorCode.INVALID_TYPE,
                "'report_signed_off' must be a boolean",
                details={"field": "report_signed_off"},
            )
        result = self.service.transition_engagement(
            require_int(body, "id"),
            require_str(body, "action"),
            note=optional_str(body, "note") or "",
            report_signed_off=signed_off,
        )
        return _detail_result(result)

    def engagements_delete(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.delete_engagement(require_int(body, "id")))

    def engagements_dashboard(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.dashboard(require_int(body, "id")))

    def engagements_portfolio(self, body: dict[str, Any]) -> RouteResult:
        data = self.service.portfolio()
        engagements = data.get("engagements", [])
        if not isinstance(engagements, list):
            engagements = []
        page_items, page = paginate(
            engagements,
            cursor=optional_str(body, "cursor"),
            limit=_page_limit(body),
        )
        response = {**data, "engagements": page_items, "page": page.as_dict()}
        return RouteResult(response, page=page, etag=compute_etag(response))

    def engagements_workflows(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result({"workflows": self.service.workflows()})

    def engagements_options(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.status_options())

    def engagements_activity(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.activity(require_int(body, "id"), limit=_page_limit(body))
        return _list_result(body, items)

    def engagements_seed_demo(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.seed_demo())

    # ------------------------------------------------------------------
    # Scope handlers
    # ------------------------------------------------------------------

    def scope_list(self, body: dict[str, Any]) -> RouteResult:
        return _list_result(body, self.service.list_scope_rules(require_int(body, "engagement_id")))

    def scope_add(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(body, ("kind", "value", "action", "notes"))
        return _detail_result(
            self.service.add_scope_rule(require_int(body, "engagement_id"), data),
            status=201,
        )

    def scope_remove(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.remove_scope_rule(
                require_int(body, "engagement_id"),
                require_int(body, "id"),
            )
        )

    def scope_evaluate(self, body: dict[str, Any]) -> RouteResult:
        value = require_str(body, "value")
        return _detail_result(
            self.service.evaluate_scope(require_int(body, "engagement_id"), value)
        )

    def scope_import(self, body: dict[str, Any]) -> RouteResult:
        rules = body.get("rules")
        if not isinstance(rules, list) or not all(isinstance(item, dict) for item in rules):
            raise V2Error(
                400,
                V2ErrorCode.INVALID_TYPE,
                "'rules' must be a list of objects",
                details={"field": "rules"},
            )
        return _detail_result(
            self.service.import_scope_rules(require_int(body, "engagement_id"), rules),
            status=201,
        )

    # ------------------------------------------------------------------
    # Target handlers
    # ------------------------------------------------------------------

    def targets_list(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.list_targets(
            require_int(body, "engagement_id"),
            scope_status=optional_str(body, "scope_status") or "",
            status=optional_str(body, "status") or "",
            criticality=optional_str(body, "criticality") or "",
            query=optional_str(body, "query") or "",
        )
        return _list_result(body, items)

    def targets_get(self, body: dict[str, Any]) -> RouteResult:
        entity = self.service._require_in(
            self.service.store.targets,
            require_int(body, "id"),
            name="target",
        )
        return _detail_result(entity.as_dict())

    def targets_create(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            (
                "value",
                "name",
                "kind",
                "description",
                "status",
                "scope_status",
                "criticality",
                "tags",
                "notes",
            ),
        )
        return _detail_result(
            self.service.add_target(require_int(body, "engagement_id"), data),
            status=201,
        )

    def targets_update(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            (
                "value",
                "name",
                "kind",
                "description",
                "status",
                "scope_status",
                "criticality",
                "tags",
                "notes",
            ),
        )
        return _detail_result(self.service.update_target(require_int(body, "id"), data))

    def targets_transition(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.transition_target(
                require_int(body, "id"),
                require_str(body, "action"),
                reason=optional_str(body, "reason") or "",
            )
        )

    def targets_scope_transition(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.transition_target_scope(
                require_int(body, "id"), require_str(body, "action")
            )
        )

    def targets_remove(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.remove_target(require_int(body, "id")))

    def targets_coverage(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.coverage_report(require_int(body, "engagement_id")))

    # ------------------------------------------------------------------
    # Asset handlers
    # ------------------------------------------------------------------

    def assets_list(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.list_assets(
            require_int(body, "engagement_id"),
            target_id=optional_int(body, "target_id") or 0,
            query=optional_str(body, "query") or "",
        )
        return _list_result(body, items)

    def assets_get(self, body: dict[str, Any]) -> RouteResult:
        entity = self.service._require_in(
            self.service.store.assets, require_int(body, "id"), name="asset"
        )
        return _detail_result(entity.as_dict())

    def assets_create(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            ("target_id", "name", "kind", "identifier", "status", "criticality", "owner", "notes"),
        )
        return _detail_result(
            self.service.add_asset(require_int(body, "engagement_id"), data),
            status=201,
        )

    def assets_update(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            ("name", "kind", "identifier", "status", "criticality", "owner", "notes", "target_id"),
        )
        return _detail_result(self.service.update_asset(require_int(body, "id"), data))

    def assets_remove(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.remove_asset(require_int(body, "id")))

    # ------------------------------------------------------------------
    # Service handlers
    # ------------------------------------------------------------------

    def services_list(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.list_services(
            require_int(body, "engagement_id"),
            target_id=optional_int(body, "target_id") or 0,
            asset_id=optional_int(body, "asset_id") or 0,
            status=optional_str(body, "status") or "",
            port=optional_int(body, "port") or 0,
        )
        return _list_result(body, items)

    def services_get(self, body: dict[str, Any]) -> RouteResult:
        entity = self.service._require_in(
            self.service.store.services, require_int(body, "id"), name="service"
        )
        return _detail_result(entity.as_dict())

    def services_create(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            (
                "target_id",
                "asset_id",
                "name",
                "port",
                "protocol",
                "product",
                "version",
                "status",
                "notes",
            ),
        )
        return _detail_result(
            self.service.add_service(require_int(body, "engagement_id"), data),
            status=201,
        )

    def services_update(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            (
                "name",
                "port",
                "protocol",
                "product",
                "version",
                "status",
                "notes",
                "target_id",
                "asset_id",
            ),
        )
        return _detail_result(self.service.update_service(require_int(body, "id"), data))

    def services_transition(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.transition_service(require_int(body, "id"), require_str(body, "action"))
        )

    def services_remove(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.remove_service(require_int(body, "id")))

    # ------------------------------------------------------------------
    # Credential handlers
    # ------------------------------------------------------------------

    def credentials_list(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.list_credentials(
            require_int(body, "engagement_id"),
            target_id=optional_int(body, "target_id") or 0,
            status=optional_str(body, "status") or "",
            kind=optional_str(body, "kind") or "",
        )
        return _list_result(body, items)

    def credentials_get(self, body: dict[str, Any]) -> RouteResult:
        entity = self.service._require_in(
            self.service.store.credentials,
            require_int(body, "id"),
            name="credential",
        )
        return _detail_result(entity.safe_dict())

    def credentials_create(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            ("target_id", "secret_ref", "username", "kind", "status", "rotated_at", "notes"),
        )
        return _detail_result(
            self.service.add_credential(require_int(body, "engagement_id"), data),
            status=201,
        )

    def credentials_update(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            ("username", "secret_ref", "kind", "status", "target_id", "rotated_at", "notes"),
        )
        return _detail_result(self.service.update_credential(require_int(body, "id"), data))

    def credentials_rotate(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.rotate_credential(
                require_int(body, "id"),
                secret_ref=optional_str(body, "secret_ref") or "",
            )
        )

    def credentials_transition(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.transition_credential(require_int(body, "id"), require_str(body, "action"))
        )

    def credentials_remove(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.remove_credential(require_int(body, "id")))

    # ------------------------------------------------------------------
    # Finding handlers
    # ------------------------------------------------------------------

    def findings_list(self, body: dict[str, Any]) -> RouteResult:
        items = self.service.list_findings(
            require_int(body, "engagement_id"),
            status=optional_str(body, "status") or "",
            severity=optional_str(body, "severity") or "",
            confidence=optional_str(body, "confidence") or "",
            target_id=optional_int(body, "target_id") or 0,
            owner=optional_str(body, "owner") or "",
            query=optional_str(body, "query") or "",
            tag=optional_str(body, "tag") or "",
        )
        return _list_result(body, items)

    def findings_get(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.finding_detail(require_int(body, "id")))

    def findings_create(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            (
                "title",
                "target_id",
                "asset_id",
                "service_id",
                "summary",
                "severity",
                "confidence",
                "cvss_vector",
                "cwe",
                "cwes",
                "cves",
                "status",
                "duplicate_of",
                "owner",
                "impact",
                "remediation",
                "reproduction_steps",
                "references",
                "tags",
            ),
        )
        return _detail_result(
            self.service.create_finding(require_int(body, "engagement_id"), data),
            status=201,
        )

    def findings_update(self, body: dict[str, Any]) -> RouteResult:
        data = _fields(
            body,
            (
                "title",
                "summary",
                "severity",
                "confidence",
                "cvss_vector",
                "cwe",
                "cwes",
                "cves",
                "status",
                "owner",
                "impact",
                "remediation",
                "reproduction_steps",
                "references",
                "tags",
                "target_id",
                "asset_id",
                "service_id",
            ),
        )
        return _detail_result(self.service.update_finding(require_int(body, "id"), data))

    def findings_transition(self, body: dict[str, Any]) -> RouteResult:
        retested = body.get("retested", False)
        if not isinstance(retested, bool):
            raise V2Error(
                400,
                V2ErrorCode.INVALID_TYPE,
                "'retested' must be a boolean",
                details={"field": "retested"},
            )
        duplicate_of = optional_int(body, "duplicate_of") or 0
        return _detail_result(
            self.service.transition_finding(
                require_int(body, "id"),
                require_str(body, "action"),
                note=optional_str(body, "note") or "",
                evidence=optional_str(body, "evidence") or "",
                duplicate_of=duplicate_of,
                retested=retested,
            )
        )

    def findings_duplicate(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(
            self.service.mark_finding_duplicate(
                require_int(body, "id"),
                require_int(body, "canonical_id"),
            )
        )

    def findings_link_cluster(self, body: dict[str, Any]) -> RouteResult:
        duplicate_ids = body.get("duplicate_ids")
        if not isinstance(duplicate_ids, list) or not all(
            isinstance(item, int) and not isinstance(item, bool) for item in duplicate_ids
        ):
            raise V2Error(
                400,
                V2ErrorCode.INVALID_TYPE,
                "'duplicate_ids' must be a list of integers",
                details={"field": "duplicate_ids"},
            )
        return _detail_result(
            self.service.link_duplicate_cluster(require_int(body, "canonical_id"), duplicate_ids)
        )

    def findings_duplicates(self, body: dict[str, Any]) -> RouteResult:
        threshold = optional_int(body, "threshold")
        value = 0.62 if threshold is None else threshold / 100.0
        return _detail_result(
            {
                "candidates": self.service.find_duplicates_for(
                    require_int(body, "id"), threshold=value
                )
            }
        )

    def findings_clusters(self, body: dict[str, Any]) -> RouteResult:
        threshold = optional_int(body, "threshold")
        value = 0.62 if threshold is None else threshold / 100.0
        return _detail_result(
            {
                "clusters": self.service.finding_clusters(
                    require_int(body, "engagement_id"),
                    threshold=value,
                )
            }
        )

    def findings_remove(self, body: dict[str, Any]) -> RouteResult:
        return _detail_result(self.service.remove_finding(require_int(body, "id")))


_active_namespace = EngagementNamespace()


def configure(service: EngagementService | None = None) -> EngagementNamespace:
    """Configure the process-wide namespace used by bare ``register(api)``."""
    global _active_namespace
    _active_namespace = EngagementNamespace(service)
    return _active_namespace


def register(api: object, service: EngagementService | None = None) -> EngagementNamespace:
    """Register engagement routes on a v2 API registry.

    When ``service`` is omitted, the configured process-wide service is used.
    """
    namespace = EngagementNamespace(service) if service is not None else _active_namespace
    try:
        namespace.register(api)
    except EngagementError as exc:
        raise _to_v2_error(exc) from exc
    except RepositoryError as exc:
        raise _to_v2_error(exc) from exc
    return namespace


def route_names() -> tuple[str, ...]:
    """Return all engagement route names without instantiating a service."""
    return tuple(spec.name for spec in _active_namespace.specs())
