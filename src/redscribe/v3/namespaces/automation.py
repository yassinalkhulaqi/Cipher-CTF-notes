"""Automation namespace: compile, inspect, dry-run, run and roll back playbooks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.automation import (
    AutomationEngine,
    AutomationError,
    PlaybookDefinition,
    diff_runs,
    humanize,
    occurrences,
    timeline,
    validate_recurrence,
)
from redscribe.v3.automation.parsing import parse_playbook, parse_recurrence
from redscribe.v3.capabilities import CAP_AUTOMATION, CapabilityError
from redscribe.v3.config import default_config

_engine: AutomationEngine | None = None

Handler = Callable[[dict[str, Any], Mapping[str, str]], dict[str, Any]]


def get_engine() -> AutomationEngine:
    """Return the shared automation engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = AutomationEngine()
    return _engine


def set_engine(engine: AutomationEngine | None) -> None:
    """Replace the shared engine (used by tests and alternate services)."""
    global _engine
    _engine = engine


def _guard(handler: Handler) -> Handler:
    """Translate domain errors into stable V3 envelopes."""

    def wrapped(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        capability = headers.get("X-Capability", "").strip()
        if capability and capability.casefold() != CAP_AUTOMATION:
            raise V3Error(
                V3ErrorCode.FORBIDDEN,
                "This route requires the automation capability",
                field="X-Capability",
            )
        try:
            default_config.capabilities().require(CAP_AUTOMATION)
            return handler(body, headers)
        except CapabilityError as error:
            raise V3Error(V3ErrorCode.FORBIDDEN, str(error)) from error
        except AutomationError as error:
            raise V3Error(
                V3ErrorCode.INVALID_REQUEST,
                error.message,
                field=error.path,
                context={"code": error.code},
            ) from error
        except (KeyError, TypeError, ValueError) as error:
            raise V3Error(V3ErrorCode.INVALID_REQUEST, str(error)) from error

    return wrapped


def _values(body: dict[str, Any]) -> dict[str, Any]:
    """Read and validate the variable value map."""
    raw = body.get("values", {})
    if not isinstance(raw, dict):
        raise V3Error(V3ErrorCode.INVALID_TYPE, "'values' must be an object", field="values")
    return dict(raw)


def _playbook(engine: AutomationEngine, body: dict[str, Any]) -> PlaybookDefinition:
    """Resolve an inline playbook or a registered playbook reference."""
    if "playbook" in body:
        playbook = parse_playbook(body["playbook"])
        try:
            engine.registry.add(playbook)
        except AutomationError:
            engine.registry.replace(playbook)
        return playbook
    ref = body.get("playbook_ref")
    if not isinstance(ref, str) or not ref:
        raise V3Error(
            V3ErrorCode.MISSING_FIELD, "Provide 'playbook' or 'playbook_ref'", field="playbook_ref"
        )
    return engine.registry.get(ref)


def register(router: V3Router) -> None:
    """Register every automation route on the supplied router."""

    @_guard
    def validate(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        engine = get_engine()
        playbook = _playbook(engine, body)
        return engine.validate(playbook.ref, _values(body)).as_dict()

    @_guard
    def compile_playbook(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        engine = get_engine()
        playbook = _playbook(engine, body)
        return {"playbook_ref": playbook.ref, "dag": engine.compile(playbook.ref).as_dict()}

    @_guard
    def connect_steps(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        engine = get_engine()
        playbook = _playbook(engine, body)
        source = body.get("source")
        target = body.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            raise V3Error(V3ErrorCode.MISSING_FIELD, "'source' and 'target' are required")
        updated, problem = engine.connect(playbook.ref, source=source, target=target)
        if problem is not None:
            return {
                "accepted": False,
                "issue": problem.as_dict(),
                "playbook": playbook.as_dict(),
            }
        assert updated is not None
        engine.registry.replace(updated)
        return {"accepted": True, "playbook": updated.as_dict()}

    @_guard
    def dry_run(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        engine = get_engine()
        playbook = _playbook(engine, body)
        trace = engine.dry_run(playbook.ref, _values(body))
        return {"trace": trace.as_dict(), "timeline": list(timeline(trace))}

    @_guard
    def run(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        engine = get_engine()
        playbook = _playbook(engine, body)
        record = engine.run(playbook.ref, _values(body))
        return {"run": record.as_dict()}

    @_guard
    def runs(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        engine = get_engine()
        ref = body.get("playbook_ref")
        limit = body.get("limit", 100)
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise V3Error(V3ErrorCode.INVALID_TYPE, "'limit' must be an integer", field="limit")
        return {
            "runs": [
                record.as_dict()
                for record in engine.list_runs(playbook_ref=str(ref) if ref else None, limit=limit)
            ]
        }

    @_guard
    def run_get(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        engine = get_engine()
        run_id = body.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise V3Error(V3ErrorCode.MISSING_FIELD, "'run_id' is required", field="run_id")
        record = engine.get_run(run_id)
        return {"run": record.as_dict(), "timeline": list(timeline_from_entries(record))}

    @_guard
    def replay(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        engine = get_engine()
        run_id = body.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise V3Error(V3ErrorCode.MISSING_FIELD, "'run_id' is required", field="run_id")
        return {"replay": engine.replay(run_id, values=_values(body)).as_dict()}

    @_guard
    def rollback(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        engine = get_engine()
        run_id = body.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise V3Error(V3ErrorCode.MISSING_FIELD, "'run_id' is required", field="run_id")
        return {"rollback": engine.rollback(run_id).as_dict()}

    @_guard
    def recurrence(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        rule = parse_recurrence(body.get("rule", body))
        after = float(body.get("after", 0.0))
        before = float(body.get("before", 0.0))
        limit = int(body.get("limit", 20))
        return {
            "rule": rule.as_dict(),
            "description": humanize(rule),
            "issues": [item.as_dict() for item in validate_recurrence(rule)],
            "timestamps": list(occurrences(rule, after, before, limit=limit)),
        }

    @_guard
    def diff(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        engine = get_engine()
        left = engine.get_run(str(body.get("left", "")))
        right = engine.get_run(str(body.get("right", "")))
        return {"differences": [item.as_dict() for item in diff_runs(left, right)]}

    router.add("automation", "validate", validate)
    router.add("automation", "compile", compile_playbook)
    router.add("automation", "connect", connect_steps)
    router.add("automation", "dry_run", dry_run)
    router.add("automation", "run", run)
    router.add("automation", "runs", runs)
    router.add("automation", "run_get", run_get)
    router.add("automation", "replay", replay)
    router.add("automation", "rollback", rollback)
    router.add("automation", "recurrence", recurrence)
    router.add("automation", "diff", diff)


def timeline_from_entries(record: Any) -> tuple[dict[str, Any], ...]:
    """Render a persisted run's trace as a UI timeline."""
    from redscribe.v3.automation.types import DryRunTrace

    return timeline(
        DryRunTrace(
            playbook_ref=record.playbook_ref,
            mode=record.mode,
            entries=record.trace,
            variables=record.variables,
            digest=record.trace_digest,
        )
    )
