"""Sync and portability namespace for API v2.

The module is additive: ``register(api)`` attaches sync routes to an existing
``ApiV2`` registry without editing shared transport or route tables.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.contracts import (
    V2Error,
    V2ErrorCode,
    compute_etag,
    optional_str,
    require_str,
)
from redscribe.ui.web.v2.routes import RouteResult
from redscribe.v2.sync.errors import SyncError
from redscribe.v2.sync.portable import (
    compatibility_matrix,
    detect_bundle,
    get_profile,
    list_profiles,
    portability_summary,
    read_portable_records,
)
from redscribe.v2.sync.reports import (
    dry_run_summary,
    portability_health,
    summarize_conflicts,
)
from redscribe.v2.sync.service import SyncService
from redscribe.v2.sync.state import SyncStateStore

Handler = Callable[[dict[str, Any]], RouteResult]


class Registrar(Protocol):
    """Minimal route registration surface required by this namespace."""

    @property
    def vault(self) -> Vault: ...

    def register(
        self,
        name: str,
        handler: Handler,
        description: str,
        *,
        required: tuple[str, ...] = (),
        optional: tuple[str, ...] = (),
        mutating: bool = False,
        entity_type: str = "",
    ) -> None: ...


def _to_v2_error(error: SyncError) -> V2Error:
    details = dict(error.details)
    details.setdefault("sync_code", error.code)
    return V2Error(error.status, error.code, error.message, details=details)


def _guard(handler: Handler) -> Handler:
    def wrapped(body: dict[str, Any]) -> RouteResult:
        try:
            return handler(body)
        except SyncError as exc:
            raise _to_v2_error(exc) from exc
        except (TypeError, ValueError) as exc:
            raise V2Error(400, V2ErrorCode.INVALID_REQUEST, str(exc) or "Invalid request") from exc

    return wrapped


def _payload(body: Mapping[str, Any], exclude: Sequence[str] = ()) -> dict[str, Any]:
    blocked = set(exclude)
    return {key: value for key, value in body.items() if key not in blocked}


def _result(data: Any, *, status: int = 200) -> RouteResult:
    return RouteResult(data, etag=compute_etag(data), status=status)


ROUTE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "action": "health",
        "description": "Report sync availability, formats, strategies, and vault stats.",
        "required": (),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "snapshot",
        "description": "Capture a portable snapshot manifest and record set.",
        "required": (),
        "optional": ("include_deleted",),
        "mutating": False,
    },
    {
        "action": "backup.plan",
        "description": "Build a backup plan and dry-run description.",
        "required": ("destination",),
        "optional": (
            "include_settings",
            "include_deleted",
            "include_snippets",
            "include_manifest",
            "include_history",
            "format",
            "dry_run",
            "label",
        ),
        "mutating": False,
    },
    {
        "action": "backup.create",
        "description": "Create a backup artifact and manifest.",
        "required": ("destination",),
        "optional": (
            "include_settings",
            "include_deleted",
            "include_snippets",
            "include_manifest",
            "include_history",
            "format",
            "dry_run",
            "label",
        ),
        "mutating": True,
        "entity_type": "backup",
    },
    {
        "action": "backup.inspect",
        "description": "Inspect a backup file and its manifest.",
        "required": ("path",),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "restore.plan",
        "description": "Inspect a restore source and compatibility.",
        "required": ("source",),
        "optional": ("mode", "verify_checksums", "dry_run", "allow_incompatible"),
        "mutating": False,
    },
    {
        "action": "restore.apply",
        "description": "Restore a backup or portable snapshot.",
        "required": ("source",),
        "optional": ("mode", "verify_checksums", "dry_run", "allow_incompatible"),
        "mutating": True,
        "entity_type": "restore",
    },
    {
        "action": "export.plan",
        "description": "Plan an export pipeline and summarize record counts.",
        "required": ("destination",),
        "optional": ("format", "include_deleted", "include_settings", "dry_run", "label"),
        "mutating": False,
    },
    {
        "action": "export.run",
        "description": "Run an export pipeline and write a manifest.",
        "required": ("destination",),
        "optional": ("format", "include_deleted", "include_settings", "dry_run", "label"),
        "mutating": True,
        "entity_type": "export",
    },
    {
        "action": "import.plan",
        "description": "Preview an import and report merge/conflict impact.",
        "required": ("source",),
        "optional": ("format", "strategy", "verify_checksums", "dry_run", "parent_id"),
        "mutating": False,
    },
    {
        "action": "import.run",
        "description": "Import a snapshot with merge strategy and optional resolutions.",
        "required": ("source",),
        "optional": (
            "format",
            "strategy",
            "verify_checksums",
            "dry_run",
            "parent_id",
            "resolutions",
        ),
        "mutating": True,
        "entity_type": "import",
    },
    {
        "action": "dry_run",
        "description": "Run a dry-run planner for backup, restore, export, import, or migration.",
        "required": ("operation",),
        "optional": ("payload",),
        "mutating": False,
    },
    {
        "action": "checksums.verify",
        "description": "Compare expected and actual checksums or compute file checksums.",
        "required": (),
        "optional": ("expected", "actual", "path"),
        "mutating": False,
    },
    {
        "action": "conflicts.detect",
        "description": "Detect conflicts and changes between local and remote snapshots.",
        "required": (),
        "optional": ("remote", "source", "strategy"),
        "mutating": False,
    },
    {
        "action": "conflicts.resolve",
        "description": "Apply manual or strategy-based conflict resolutions.",
        "required": (),
        "optional": ("remote", "source", "resolutions", "strategy"),
        "mutating": False,
    },
    {
        "action": "conflicts.session.create",
        "description": "Create a conflict resolution session for interactive review.",
        "required": ("operation",),
        "optional": ("remote", "source", "strategy", "metadata"),
        "mutating": True,
        "entity_type": "conflict_session",
    },
    {
        "action": "conflicts.session.get",
        "description": "Return a stored conflict resolution session.",
        "required": ("session_id",),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "conflicts.session.list",
        "description": "List stored conflict resolution sessions.",
        "required": (),
        "optional": ("limit",),
        "mutating": False,
    },
    {
        "action": "conflicts.session.resolve",
        "description": "Update conflict resolutions in a stored session.",
        "required": ("session_id", "resolutions"),
        "optional": (),
        "mutating": True,
        "entity_type": "conflict_session",
    },
    {
        "action": "conflicts.session.discard",
        "description": "Discard a stored conflict resolution session.",
        "required": ("session_id",),
        "optional": (),
        "mutating": True,
        "entity_type": "conflict_session",
    },
    {
        "action": "merge.preview",
        "description": "Preview merge results for local and remote snapshots.",
        "required": (),
        "optional": ("remote", "source", "strategy", "resolutions"),
        "mutating": False,
    },
    {
        "action": "journal.diff",
        "description": "Build a change journal comparing local and remote snapshots.",
        "required": (),
        "optional": ("remote", "source"),
        "mutating": False,
    },
    {
        "action": "journal.report",
        "description": "Summarize actionable journal changes.",
        "required": (),
        "optional": ("remote", "source"),
        "mutating": False,
    },
    {
        "action": "vectors.compare",
        "description": "Compare local and remote version vectors.",
        "required": ("local", "remote"),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "migration.check",
        "description": "Check snapshot manifest compatibility and migration plan.",
        "required": ("manifest",),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "progress.report",
        "description": "Normalize progress steps into a report summary.",
        "required": ("steps",),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "portability.profiles",
        "description": "List built-in portability profiles.",
        "required": (),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "portability.profile",
        "description": "Return one portability profile by name.",
        "required": ("name",),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "portability.detect",
        "description": "Detect a portable snapshot bundle format.",
        "required": ("path",),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "portability.records",
        "description": "Read and summarize portable records from a source.",
        "required": ("path",),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "portability.matrix",
        "description": "Return supported portability formats and recommendations.",
        "required": (),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "state.stats",
        "description": "Return sync operation and conflict-session state stats.",
        "required": (),
        "optional": (),
        "mutating": False,
    },
    {
        "action": "state.operations",
        "description": "List tracked sync operations.",
        "required": (),
        "optional": ("limit",),
        "mutating": False,
    },
)


class SyncHandlers:
    """Handlers bound to a vault-backed sync service."""

    def __init__(self, service: SyncService, state: SyncStateStore | None = None) -> None:
        self.service = service
        self.state = state or SyncStateStore()

    def health(self, body: dict[str, Any]) -> RouteResult:
        data = self.service.health()
        data["portability"] = portability_health(data)
        data["state"] = self.state.stats()
        return _result(data)

    def snapshot(self, body: dict[str, Any]) -> RouteResult:
        include_deleted = bool(body.get("include_deleted", False))
        return _result(self.service.snapshot(include_deleted=include_deleted))

    def backup_plan(self, body: dict[str, Any]) -> RouteResult:
        return _result(self.service.backup_plan(_payload(body)))

    def backup_create(self, body: dict[str, Any]) -> RouteResult:
        op = self.state.create_operation("backup", details={"destination": body.get("destination")})
        try:
            result = self.service.backup_create(_payload(body))
            self.state.complete_operation(op.operation_id, details={"path": result.get("path")})
            result["operation_id"] = op.operation_id
            return _result(result)
        except Exception as exc:
            self.state.fail_operation(op.operation_id, str(exc))
            raise

    def backup_inspect(self, body: dict[str, Any]) -> RouteResult:
        return _result(self.service.backup_inspect(require_str(body, "path")))

    def restore_plan(self, body: dict[str, Any]) -> RouteResult:
        return _result(self.service.restore_plan(_payload(body)))

    def restore_apply(self, body: dict[str, Any]) -> RouteResult:
        op = self.state.create_operation("restore", details={"source": body.get("source")})
        try:
            result = self.service.restore_apply(_payload(body))
            self.state.complete_operation(
                op.operation_id, details={"restored_path": result.get("restored_path")}
            )
            result["operation_id"] = op.operation_id
            return _result(result)
        except Exception as exc:
            self.state.fail_operation(op.operation_id, str(exc))
            raise

    def export_plan(self, body: dict[str, Any]) -> RouteResult:
        return _result(self.service.export_plan(_payload(body)))

    def export_run(self, body: dict[str, Any]) -> RouteResult:
        op = self.state.create_operation("export", details={"destination": body.get("destination")})
        try:
            result = self.service.export_run(_payload(body))
            self.state.complete_operation(op.operation_id, details={"path": result.get("path")})
            result["operation_id"] = op.operation_id
            return _result(result)
        except Exception as exc:
            self.state.fail_operation(op.operation_id, str(exc))
            raise

    def import_plan(self, body: dict[str, Any]) -> RouteResult:
        return _result(self.service.import_plan(_payload(body)))

    def import_run(self, body: dict[str, Any]) -> RouteResult:
        op = self.state.create_operation("import", details={"source": body.get("source")})
        try:
            result = self.service.import_run(_payload(body))
            self.state.complete_operation(op.operation_id, details={"source": body.get("source")})
            result["operation_id"] = op.operation_id
            return _result(result)
        except Exception as exc:
            self.state.fail_operation(op.operation_id, str(exc))
            raise

    def dry_run(self, body: dict[str, Any]) -> RouteResult:
        operation = require_str(body, "operation")
        payload = body.get("payload")
        if payload is None:
            payload = _payload(body, exclude=("operation",))
        if not isinstance(payload, Mapping):
            raise V2Error(400, V2ErrorCode.INVALID_REQUEST, "payload must be an object")
        report = self.service.dry_runs.from_operation(operation, payload)
        data = report.as_dict()
        data["report_summary"] = dry_run_summary(report)
        return _result(data)

    def checksums_verify(self, body: dict[str, Any]) -> RouteResult:
        expected = body.get("expected")
        actual = body.get("actual")
        path = optional_str(body, "path")
        data = self.service.verify_checksums(
            expected=expected if isinstance(expected, Mapping) else None,
            actual=actual if isinstance(actual, Mapping) else None,
            path=path,
        )
        return _result(data)

    def conflicts_detect(self, body: dict[str, Any]) -> RouteResult:
        remote = body.get("remote")
        source = optional_str(body, "source")
        strategy = optional_str(body, "strategy", default="merge") or "merge"
        data = self.service.detect_conflicts(
            remote=remote if isinstance(remote, list) else None,
            source=source,
            strategy=strategy,
        )
        from redscribe.v2.sync.models import ConflictRecord

        conflicts = [
            ConflictRecord(
                key=str(item.get("key", "")),
                kind=str(item.get("kind", "content")),
                path=str(item.get("path", "")),
                title=str(item.get("title", "")),
                local_checksum=str(item.get("local_checksum", "")),
                remote_checksum=str(item.get("remote_checksum", "")),
                local_updated_at=str(item.get("local_updated_at", "")),
                remote_updated_at=str(item.get("remote_updated_at", "")),
                resolution=str(item.get("resolution", "unresolved")),
                details=dict(item.get("details", {})),
                suggested=str(item.get("suggested", "")),
            )
            for item in data.get("conflicts", [])
            if isinstance(item, dict)
        ]
        data["summary"]["details"] = summarize_conflicts(conflicts)
        return _result(data)

    def conflicts_resolve(self, body: dict[str, Any]) -> RouteResult:
        remote = body.get("remote")
        source = optional_str(body, "source")
        resolutions = body.get("resolutions")
        strategy = optional_str(body, "strategy", default="merge") or "merge"
        data = self.service.resolve_conflicts(
            remote=remote if isinstance(remote, list) else None,
            source=source,
            resolutions=resolutions if isinstance(resolutions, Mapping) else {},
            strategy=strategy,
        )
        return _result(data)

    def conflicts_session_create(self, body: dict[str, Any]) -> RouteResult:
        operation = require_str(body, "operation")
        remote = body.get("remote")
        source = optional_str(body, "source")
        strategy = optional_str(body, "strategy", default="merge") or "merge"
        detection = self.service.detect_conflicts(
            remote=remote if isinstance(remote, list) else None,
            source=source,
            strategy=strategy,
        )
        conflicts = []
        for item in detection.get("conflicts", []):
            from redscribe.v2.sync.models import ConflictRecord

            conflicts.append(
                ConflictRecord(
                    key=str(item.get("key", "")),
                    kind=str(item.get("kind", "content")),
                    path=str(item.get("path", "")),
                    title=str(item.get("title", "")),
                    local_checksum=str(item.get("local_checksum", "")),
                    remote_checksum=str(item.get("remote_checksum", "")),
                    local_updated_at=str(item.get("local_updated_at", "")),
                    remote_updated_at=str(item.get("remote_updated_at", "")),
                    resolution=str(item.get("resolution", "unresolved")),
                    details=dict(item.get("details", {})),
                    suggested=str(item.get("suggested", "")),
                )
            )
        raw_metadata = body.get("metadata")
        metadata: dict[str, Any] = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
        session = self.state.create_conflict_session(operation, conflicts, metadata=metadata)
        data = session.as_dict()
        data["detection"] = detection
        return _result(data)

    def conflicts_session_get(self, body: dict[str, Any]) -> RouteResult:
        return _result(self.state.get_conflict_session(require_str(body, "session_id")).as_dict())

    def conflicts_session_list(self, body: dict[str, Any]) -> RouteResult:
        limit = body.get("limit", 50)
        if isinstance(limit, bool) or not isinstance(limit, int):
            limit = 50
        return _result({"sessions": self.state.list_conflict_sessions(limit=limit)})

    def conflicts_session_resolve(self, body: dict[str, Any]) -> RouteResult:
        resolutions = body.get("resolutions")
        if not isinstance(resolutions, Mapping):
            raise V2Error(400, V2ErrorCode.INVALID_REQUEST, "resolutions must be an object")
        session = self.state.resolve_conflict_session(
            require_str(body, "session_id"),
            {str(k): str(v) for k, v in resolutions.items()},
        )
        return _result(session.as_dict())

    def conflicts_session_discard(self, body: dict[str, Any]) -> RouteResult:
        return _result(self.state.discard_conflict_session(require_str(body, "session_id")))

    def merge_preview(self, body: dict[str, Any]) -> RouteResult:
        remote = body.get("remote")
        source = optional_str(body, "source")
        strategy = optional_str(body, "strategy", default="merge") or "merge"
        resolutions = body.get("resolutions")
        data = self.service.merge_preview(
            remote=remote if isinstance(remote, list) else None,
            source=source,
            strategy=strategy,
            resolutions=resolutions if isinstance(resolutions, Mapping) else {},
        )
        return _result(data)

    def journal_diff(self, body: dict[str, Any]) -> RouteResult:
        remote = body.get("remote")
        source = optional_str(body, "source")
        data = self.service.diff_journal(
            remote=remote if isinstance(remote, list) else None,
            source=source,
        )
        return _result(data)

    def journal_report(self, body: dict[str, Any]) -> RouteResult:
        local = self.service.journal.capture_vault(self.service.vault)
        remote = self.service._load_remote(
            remote=body.get("remote") if isinstance(body.get("remote"), list) else None,
            source=optional_str(body, "source"),
        )
        from redscribe.v2.sync.reports import journal_report

        return _result(journal_report(local, remote))

    def vectors_compare(self, body: dict[str, Any]) -> RouteResult:
        local = body.get("local")
        remote = body.get("remote")
        if not isinstance(local, Mapping) or not isinstance(remote, Mapping):
            raise V2Error(400, V2ErrorCode.INVALID_REQUEST, "local and remote must be objects")
        return _result(self.service.compare_vectors(local, remote))

    def migration_check(self, body: dict[str, Any]) -> RouteResult:
        manifest = body.get("manifest")
        if not isinstance(manifest, Mapping):
            raise V2Error(400, V2ErrorCode.INVALID_REQUEST, "manifest must be an object")
        return _result(self.service.migration_check(manifest))

    def progress_report(self, body: dict[str, Any]) -> RouteResult:
        steps = body.get("steps")
        if not isinstance(steps, list):
            raise V2Error(400, V2ErrorCode.INVALID_REQUEST, "steps must be an array")
        normalized = [item for item in steps if isinstance(item, Mapping)]
        return _result(self.service.progress_report(normalized))

    def portability_profiles(self, body: dict[str, Any]) -> RouteResult:
        return _result({"profiles": list_profiles(), "matrix": compatibility_matrix()})

    def portability_profile(self, body: dict[str, Any]) -> RouteResult:
        return _result(get_profile(require_str(body, "name")).as_dict())

    def portability_detect(self, body: dict[str, Any]) -> RouteResult:
        return _result(detect_bundle(require_str(body, "path")))

    def portability_records(self, body: dict[str, Any]) -> RouteResult:
        records = read_portable_records(require_str(body, "path"))
        return _result({"records": records, "summary": portability_summary(records)})

    def portability_matrix(self, body: dict[str, Any]) -> RouteResult:
        return _result(compatibility_matrix())

    def state_stats(self, body: dict[str, Any]) -> RouteResult:
        return _result(self.state.stats())

    def state_operations(self, body: dict[str, Any]) -> RouteResult:
        limit = body.get("limit", 50)
        if isinstance(limit, bool) or not isinstance(limit, int):
            limit = 50
        return _result({"operations": self.state.list_operations(limit=limit)})

    def handler_map(self) -> dict[str, Handler]:
        return {
            "health": self.health,
            "snapshot": self.snapshot,
            "backup.plan": self.backup_plan,
            "backup.create": self.backup_create,
            "backup.inspect": self.backup_inspect,
            "restore.plan": self.restore_plan,
            "restore.apply": self.restore_apply,
            "export.plan": self.export_plan,
            "export.run": self.export_run,
            "import.plan": self.import_plan,
            "import.run": self.import_run,
            "dry_run": self.dry_run,
            "checksums.verify": self.checksums_verify,
            "conflicts.detect": self.conflicts_detect,
            "conflicts.resolve": self.conflicts_resolve,
            "conflicts.session.create": self.conflicts_session_create,
            "conflicts.session.get": self.conflicts_session_get,
            "conflicts.session.list": self.conflicts_session_list,
            "conflicts.session.resolve": self.conflicts_session_resolve,
            "conflicts.session.discard": self.conflicts_session_discard,
            "merge.preview": self.merge_preview,
            "journal.diff": self.journal_diff,
            "journal.report": self.journal_report,
            "vectors.compare": self.vectors_compare,
            "migration.check": self.migration_check,
            "progress.report": self.progress_report,
            "portability.profiles": self.portability_profiles,
            "portability.profile": self.portability_profile,
            "portability.detect": self.portability_detect,
            "portability.records": self.portability_records,
            "portability.matrix": self.portability_matrix,
            "state.stats": self.state_stats,
            "state.operations": self.state_operations,
        }


class SyncNamespace:
    """Registered sync namespace."""

    def __init__(self, service: SyncService, state: SyncStateStore | None = None) -> None:
        self.service = service
        self.handlers = SyncHandlers(service, state=state)

    def register(self, api: Any) -> tuple[str, ...]:
        registrar = getattr(api, "register", None)
        if registrar is None:
            registrar = getattr(api, "_register", None)
        if not callable(registrar):
            raise TypeError("API does not expose a route registration method")
        handlers = self.handlers.handler_map()
        names = []
        for spec in ROUTE_SPECS:
            action = str(spec["action"])
            route_name = f"sync.{action}"
            handler = handlers[action]
            registrar(
                route_name,
                _guard(handler),
                str(spec["description"]),
                required=tuple(spec.get("required", ())),
                optional=tuple(spec.get("optional", ())),
                mutating=bool(spec.get("mutating", False)),
                entity_type=str(spec.get("entity_type", "")),
            )
            names.append(route_name)
        return tuple(names)

    def routes(self) -> tuple[str, ...]:
        return tuple(f"sync.{spec['action']}" for spec in ROUTE_SPECS)


def register(api: Registrar | Any) -> SyncNamespace:
    """Register sync routes on an existing API registry."""
    vault = getattr(api, "vault", None)
    if not isinstance(vault, Vault):
        raise TypeError("API registry must expose a Vault instance as .vault")
    namespace = SyncNamespace(SyncService(vault))
    namespace.register(api)
    return namespace


def register_with_vault(vault: Vault) -> SyncNamespace:
    """Create a namespace without attaching it to an API registry."""
    return SyncNamespace(SyncService(vault))


def route_names() -> tuple[str, ...]:
    return tuple(f"sync.{spec['action']}" for spec in ROUTE_SPECS)


def route_specs() -> tuple[dict[str, Any], ...]:
    return tuple(dict(spec) for spec in ROUTE_SPECS)
