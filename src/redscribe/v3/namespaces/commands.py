"""Command-center API routes registered through the additive V3 router."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.request_id import normalize_request_id, optional_str, require_str
from redscribe.v3.api.router import Handler, V3Router
from redscribe.v3.commands.capabilities import CommandDeniedError
from redscribe.v3.commands.focus import FocusError
from redscribe.v3.commands.macros import MacroError
from redscribe.v3.commands.service import CommandCenterService
from redscribe.v3.commands.types import CommandContext, CommandInvocation, PermissionLevel
from redscribe.v3.commands.workspace import PaneOrientation, WorkspaceError
from redscribe.v3.entities.ids import try_parse
from redscribe.v3.entities.types import EntityRef

_service: CommandCenterService | None = None


def get_service() -> CommandCenterService:
    """Return the shared service, creating it on first use."""
    global _service
    if _service is None:
        _service = CommandCenterService()
    return _service


def set_service(service: CommandCenterService | None) -> CommandCenterService | None:
    """Replace the shared service, returning the previous one."""
    global _service
    previous = _service
    _service = service
    return previous


def reset_service() -> None:
    """Drop the shared service (used by isolated tests)."""
    global _service
    _service = None


def _denial_error(error: CommandDeniedError) -> V3Error:
    """Map a command denial to a stable V3 error."""
    details: dict[str, object] = dict(error.denial.as_dict())
    return V3Error(
        V3ErrorCode.FORBIDDEN,
        error.denial.detail or error.denial.reason.value,
        context=details,
    )


def _parse_error(error: Exception) -> V3Error:
    """Map validation failures to a stable V3 error."""
    return V3Error(V3ErrorCode.INVALID_REQUEST, str(error))


def _limit(body: dict[str, Any], key: str, default: int) -> int:
    """Read a positive integer result limit."""
    raw = body.get(key, default)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise V3Error(
            V3ErrorCode.INVALID_REQUEST,
            f"'{key}' must be a positive integer",
            field=key,
        )
    return raw


def _request_id(headers: Mapping[str, str]) -> str:
    """Read or generate a request id."""
    return normalize_request_id(headers.get("x-request-id", headers.get("X-Request-ID", "")))


def _context(service: CommandCenterService, body: dict[str, Any]) -> CommandContext:
    """Build a command context from a request body."""
    pane_id = optional_str(body, "pane", default="", limit=80)
    raw_ref = optional_str(body, "ref", limit=200)
    parsed = try_parse(raw_ref) if raw_ref else None
    entity = (
        EntityRef(parsed, optional_str(body, "label", limit=200)) if parsed is not None else None
    )
    selection: tuple[EntityRef, ...] = ()
    raw_selection = body.get("selection", ())
    if isinstance(raw_selection, (list, tuple)):
        selection = tuple(
            EntityRef(item)
            for raw in raw_selection
            if isinstance(raw, str) and (item := try_parse(raw)) is not None
        )
    tags = (
        tuple(str(tag) for tag in body.get("tags", ()))
        if isinstance(body.get("tags", ()), (list, tuple))
        else ()
    )
    return service.resolve_context(pane_id, entity=entity, selection=selection, tags=tags)


def _invocation(body: dict[str, Any]) -> CommandInvocation:
    """Build a structured invocation from a request body."""
    command_id = require_str(body, "command_id", limit=120)
    raw_arguments = body.get("arguments", {})
    if not isinstance(raw_arguments, dict):
        raise V3Error(V3ErrorCode.INVALID_TYPE, "'arguments' must be an object", field="arguments")
    arguments: dict[str, str] = {}
    for key, value in raw_arguments.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise V3Error(
                V3ErrorCode.INVALID_TYPE, "Arguments must be string pairs", field="arguments"
            )
        arguments[key] = value
    return CommandInvocation(
        command_id=command_id,
        arguments=arguments,
        source=optional_str(body, "source", default="palette", limit=40),
        context_ref=optional_str(body, "context_ref", limit=200),
    )


def register(router: V3Router) -> None:
    """Register every command-center route on the supplied router."""

    def manifest(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return get_service().manifest()

    def list_commands(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        context = _context(service, body)
        return {
            "commands": [spec.as_dict() for spec in service.list_commands(context)],
            "context": context.as_dict(),
        }

    def suggest(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        query = optional_str(body, "query", limit=200)
        limit = _limit(body, "limit", 12)
        context = _context(service, body)
        return {
            "groups": [group.as_dict() for group in service.suggest(query, context, limit=limit)],
            "context": context.as_dict(),
        }

    def context(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {"context": _context(get_service(), body).as_dict()}

    def execute(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        try:
            result = service.execute(
                _invocation(body),
                _context(service, body),
                request_id=_request_id(headers),
            )
        except CommandDeniedError as error:
            raise _denial_error(error) from error
        except ValueError as error:
            raise _parse_error(error) from error
        return {"result": result.as_dict(), "focus": service.focus.status()}

    def usage_recent(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        limit = _limit(body, "limit", 10)
        return {"recent": [event.as_dict() for event in get_service().usage.recent(limit)]}

    def usage_frequent(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        limit = _limit(body, "limit", 10)
        rows = get_service().usage.frequent(limit)
        return {"frequent": [{"command_id": key, "count": count} for key, count in rows]}

    def usage_record(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        invocation = _invocation(body)
        event = service.usage.record(
            invocation,
            pane_id=optional_str(body, "pane", limit=80),
            context_ref=optional_str(body, "context_ref", limit=200),
        )
        return {"event": event.as_dict()}

    def macros_list(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        return {
            "macros": [macro.as_dict() for macro in service.library.all()],
            "recorder": service.recorder_status(),
        }

    def macros_start(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        name = require_str(body, "name", limit=120)
        try:
            service.recorder.start(name)
        except MacroError as error:
            raise _parse_error(error) from error
        return {"recorder": service.recorder_status()}

    def macros_stop(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        try:
            macro = service.stop_macro()
        except MacroError as error:
            raise _parse_error(error) from error
        return {"macro": macro.as_dict()}

    def macros_run(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        name = require_str(body, "name", limit=120)
        raw_values = body.get("values", {})
        if not isinstance(raw_values, dict):
            raise V3Error(V3ErrorCode.INVALID_TYPE, "'values' must be an object", field="values")
        values = {str(key): str(value) for key, value in raw_values.items()}
        try:
            invocations = service.run_macro(name, values)
        except MacroError as error:
            raise V3Error(V3ErrorCode.NOT_FOUND, str(error)) from error
        return {"steps": [invocation.as_dict() for invocation in invocations]}

    def macros_expand(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        name = require_str(body, "name", limit=120)
        raw_values = body.get("values", {})
        if not isinstance(raw_values, dict):
            raise V3Error(V3ErrorCode.INVALID_TYPE, "'values' must be an object", field="values")
        try:
            steps = service.run_macro(
                name, {str(key): str(value) for key, value in raw_values.items()}
            )
        except MacroError as error:
            raise V3Error(V3ErrorCode.NOT_FOUND, str(error)) from error
        return {"steps": [step.as_dict() for step in steps]}

    def macros_delete(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        macro_id = require_str(body, "macro_id", limit=120)
        return {"deleted": get_service().library.remove(macro_id)}

    def nav_breadcrumbs(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        ref = require_str(body, "ref", limit=200)
        return {"crumbs": [node.as_dict() for node in get_service().breadcrumbs(ref)]}

    def nav_neighbors(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        ref = require_str(body, "ref", limit=200)
        if not service.navigation.has(ref):
            raise V3Error(V3ErrorCode.NOT_FOUND, f"Unknown navigation node: {ref}")
        limit = _limit(body, "limit", 8)
        return {
            "neighbors": [node.as_dict() for node in service.navigation.neighbors(ref, limit=limit)]
        }

    def focus_status(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {"focus": get_service().focus.status()}

    def focus_start(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        label = optional_str(body, "label", default="Focus", limit=120)
        try:
            session = service.focus_start(
                label,
                target=optional_str(body, "target", limit=200),
                restore_pane=optional_str(body, "restore_pane", limit=80),
            )
        except (FocusError, ValueError) as error:
            raise _parse_error(error) from error
        return {"session": session.as_dict()}

    def focus_transition(action: str) -> Handler:
        def handler(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
            service = get_service()
            try:
                session = getattr(service.focus, action)()
            except (FocusError, ValueError) as error:
                raise _parse_error(error) from error
            return {"session": session.as_dict(), "focus": service.focus.status()}

        return handler

    def workspace_snapshot(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        return {
            "workspace": service.workspace.snapshot(),
            "panes": [pane.as_dict() for pane in service.workspace.panes()],
        }

    def _pane_change(body: dict[str, Any], action: str) -> dict[str, Any]:
        service = get_service()
        pane_id = optional_str(body, "pane", default=service.workspace.state.active_pane, limit=80)
        try:
            if action == "split":
                pane = service.workspace.split(
                    pane_id,
                    PaneOrientation.parse(
                        optional_str(body, "orientation", default="vertical", limit=20)
                    ),
                    new_pane_id=optional_str(body, "new_pane", limit=80),
                    title=optional_str(body, "title", limit=120),
                    ratio=float(body.get("ratio", 0.5) or 0.5),
                )
            elif action == "resize":
                service.workspace.resize(pane_id, float(body.get("size", 0.5) or 0.5))
                pane = service.workspace.active()
            elif action == "close":
                pane = service.workspace.close(pane_id)
            else:
                pane = service.workspace.activate(pane_id)
        except (WorkspaceError, ValueError) as error:
            raise _parse_error(error) from error
        return {
            "pane": pane.as_dict(),
            "panes": [item.as_dict() for item in service.workspace.panes()],
            "workspace": service.workspace.snapshot(),
        }

    def workspace_split(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _pane_change(body, "split")

    def workspace_resize(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _pane_change(body, "resize")

    def workspace_close(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _pane_change(body, "close")

    def workspace_activate(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return _pane_change(body, "activate")

    def workspace_context(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        pane_id = optional_str(body, "pane", default=service.workspace.state.active_pane, limit=80)
        try:
            pane = service.workspace.set_context(pane_id, require_str(body, "ref", limit=200))
        except WorkspaceError as error:
            raise _parse_error(error) from error
        return {"pane": pane.as_dict()}

    def workspace_restore(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        snapshot = body.get("workspace")
        if not isinstance(snapshot, dict):
            raise V3Error(
                V3ErrorCode.INVALID_TYPE, "'workspace' must be an object", field="workspace"
            )
        try:
            service.workspace.restore(snapshot)
        except WorkspaceError as error:
            raise _parse_error(error) from error
        return {"workspace": service.workspace.snapshot()}

    def state_snapshot(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {"snapshot": get_service().snapshot()}

    def state_restore(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        snapshot = body.get("snapshot")
        if not isinstance(snapshot, dict):
            raise V3Error(
                V3ErrorCode.INVALID_TYPE, "'snapshot' must be an object", field="snapshot"
            )
        get_service().restore(snapshot)
        return {"snapshot": get_service().snapshot()}

    def set_permission(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        service = get_service()
        value = require_str(body, "level", limit=20)
        try:
            level = PermissionLevel[value.strip().upper()]
        except KeyError as error:
            raise V3Error(
                V3ErrorCode.INVALID_CHOICE, f"Unknown permission level: {value}"
            ) from error
        service.actor_level = level
        return {"permission": level.value}

    router.add("commands", "manifest", manifest, public=True)
    router.add("commands", "list", list_commands)
    router.add("commands", "suggest", suggest)
    router.add("commands", "context", context)
    router.add("commands", "execute", execute)
    router.add("commands", "usage.recent", usage_recent)
    router.add("commands", "usage.frequent", usage_frequent)
    router.add("commands", "usage.record", usage_record)
    router.add("commands", "macros.list", macros_list)
    router.add("commands", "macros.start", macros_start)
    router.add("commands", "macros.stop", macros_stop)
    router.add("commands", "macros.run", macros_run)
    router.add("commands", "macros.expand", macros_expand)
    router.add("commands", "macros.delete", macros_delete)
    router.add("commands", "nav.breadcrumbs", nav_breadcrumbs)
    router.add("commands", "nav.neighbors", nav_neighbors)
    router.add("commands", "focus.status", focus_status)
    router.add("commands", "focus.start", focus_start)
    router.add("commands", "focus.pause", focus_transition("pause"))
    router.add("commands", "focus.resume", focus_transition("resume"))
    router.add("commands", "focus.end", focus_transition("end"))
    router.add("commands", "workspace.snapshot", workspace_snapshot)
    router.add("commands", "workspace.split", workspace_split)
    router.add("commands", "workspace.resize", workspace_resize)
    router.add("commands", "workspace.close", workspace_close)
    router.add("commands", "workspace.activate", workspace_activate)
    router.add("commands", "workspace.context", workspace_context)
    router.add("commands", "workspace.restore", workspace_restore)
    router.add("commands", "state.snapshot", state_snapshot)
    router.add("commands", "state.restore", state_restore)
    router.add("commands", "permission.set", set_permission)
