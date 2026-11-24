"""Data-only scripting: JSON plans of read-first SDK calls, never code."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.api_sdk.client import SdkClient
from redscribe.v3.api_sdk.errors import ReadOnlyViolationError, ScriptError, SdkError
from redscribe.v3.api_sdk.models import require_name

STEP_FIELDS: frozenset[str] = frozenset(
    {
        "label",
        "namespace",
        "action",
        "body",
        "capability",
        "etag",
        "idempotency_key",
        "write",
    }
)
PLAN_FIELDS: frozenset[str] = frozenset({"name", "allow_write", "steps"})
MAX_STEPS = 100


@dataclass(frozen=True, slots=True)
class ScriptStep:
    """One declarative API call inside a script."""

    namespace: str
    action: str
    body: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    capability: str = ""
    etag: str = ""
    idempotency_key: str = ""
    write: bool = False

    def __post_init__(self) -> None:
        require_name(self.namespace, "namespace")
        require_name(self.action, "action")
        if not isinstance(self.write, bool):
            raise ScriptError("'write' must be a boolean", field="write")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, index: int = 0) -> ScriptStep:
        """Parse and validate one step from a JSON object."""
        if not isinstance(raw, Mapping):
            raise ScriptError(f"steps[{index}] must be an object", field="steps")
        for key in raw:
            if key not in STEP_FIELDS:
                raise ScriptError(f"steps[{index}] has unknown field '{key}'", field="steps")
        namespace = raw.get("namespace")
        action = raw.get("action")
        if not isinstance(namespace, str) or not isinstance(action, str):
            raise ScriptError(f"steps[{index}] requires string namespace and action", field="steps")
        body = raw.get("body", {})
        if not isinstance(body, Mapping):
            raise ScriptError(f"steps[{index}].body must be an object", field="body")
        label = raw.get("label", "")
        if not isinstance(label, str) or len(label) > 240:
            raise ScriptError(f"steps[{index}].label must be a short string", field="label")
        capability = raw.get("capability", "")
        etag = raw.get("etag", "")
        idempotency_key = raw.get("idempotency_key", "")
        for key, value in (
            ("capability", capability),
            ("etag", etag),
            ("idempotency_key", idempotency_key),
        ):
            if not isinstance(value, str) or len(value) > 200:
                raise ScriptError(f"steps[{index}].{key} must be a short string", field=key)
        return cls(
            namespace=namespace,
            action=action,
            body=dict(body),
            label=label,
            capability=capability,
            etag=etag,
            idempotency_key=idempotency_key,
            write=raw.get("write", False) is True,
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "label": self.label,
            "namespace": self.namespace,
            "action": self.action,
            "body": dict(self.body),
            "capability": self.capability,
            "etag": self.etag,
            "idempotency_key": self.idempotency_key,
            "write": self.write,
        }


@dataclass(frozen=True, slots=True)
class ScriptPlan:
    """A validated, data-only sequence of calls."""

    name: str
    steps: tuple[ScriptStep, ...] = ()
    allow_write: bool = False

    @classmethod
    def from_document(cls, raw: Mapping[str, Any]) -> ScriptPlan:
        """Parse a script document, rejecting unknown fields."""
        if not isinstance(raw, Mapping):
            raise ScriptError("Script must be an object", field="script")
        for key in raw:
            if key not in PLAN_FIELDS:
                raise ScriptError(f"Unknown script field '{key}'", field="script")
        name = raw.get("name", "")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ScriptError("Script name must be 1-120 characters", field="name")
        steps = raw.get("steps", ())
        if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
            raise ScriptError("Script steps must be a list", field="steps")
        if not steps:
            raise ScriptError("Script must declare at least one step", field="steps")
        if len(steps) > MAX_STEPS:
            raise ScriptError(f"Script supports at most {MAX_STEPS} steps", field="steps")
        parsed = tuple(ScriptStep.from_dict(step, index=index) for index, step in enumerate(steps))
        return cls(
            name=name.strip(),
            steps=parsed,
            allow_write=raw.get("allow_write", False) is True,
        )

    @property
    def read_only(self) -> bool:
        """Return whether every step is a read."""
        return not any(step.write for step in self.steps)

    @property
    def write_steps(self) -> tuple[ScriptStep, ...]:
        """Return steps that mutate state."""
        return tuple(step for step in self.steps if step.write)

    def validate(self, *, allow_write: bool = False) -> None:
        """Fail before any step runs when writes lack an explicit opt-in."""
        if self.write_steps and not (self.allow_write or allow_write):
            raise ReadOnlyViolationError(
                f"Script '{self.name}' contains {len(self.write_steps)} write step(s); "
                "pass --allow-write to opt in",
                field="allow_write",
            )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "name": self.name,
            "allow_write": self.allow_write,
            "steps": [step.as_dict() for step in self.steps],
        }


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """Result of one script step."""

    index: int
    label: str
    namespace: str
    action: str
    status: int
    ok: bool
    error_code: str
    data: Any
    request_id: str = ""
    cached: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "index": self.index,
            "label": self.label,
            "route": f"/api/v3/{self.namespace}/{self.action}",
            "status": self.status,
            "ok": self.ok,
            "error_code": self.error_code,
            "data": self.data,
            "request_id": self.request_id,
            "cached": self.cached,
        }


@dataclass(frozen=True, slots=True)
class ScriptResult:
    """Outcome of an entire script run."""

    name: str
    outcomes: tuple[StepOutcome, ...]
    stopped_early: bool = False

    @property
    def success(self) -> bool:
        """Return whether every step succeeded."""
        return all(item.ok for item in self.outcomes)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "name": self.name,
            "success": self.success,
            "stopped_early": self.stopped_early,
            "steps": [item.as_dict() for item in self.outcomes],
        }


class ScriptRunner:
    """Executes declarative steps through a typed SDK client."""

    def __init__(self, client: SdkClient) -> None:
        self.client = client

    def run(
        self,
        plan: ScriptPlan,
        *,
        allow_write: bool = False,
        continue_on_error: bool = False,
    ) -> ScriptResult:
        """Run every step, enforcing the write opt-in before starting."""
        plan.validate(allow_write=allow_write)
        outcomes: list[StepOutcome] = []
        stopped = False
        for index, step in enumerate(plan.steps):
            try:
                response = self.client.call(
                    step.namespace,
                    step.action,
                    step.body,
                    capability=step.capability,
                    etag=step.etag,
                    idempotency_key=step.idempotency_key,
                    allow_errors=True,
                )
                outcome = StepOutcome(
                    index=index,
                    label=step.label or f"{step.namespace}.{step.action}",
                    namespace=step.namespace,
                    action=step.action,
                    status=response.status,
                    ok=response.ok,
                    error_code=response.code,
                    data=response.data,
                    request_id=response.request_id,
                    cached=response.cached,
                )
            except SdkError as error:
                outcome = StepOutcome(
                    index=index,
                    label=step.label or f"{step.namespace}.{step.action}",
                    namespace=step.namespace,
                    action=step.action,
                    status=error.status,
                    ok=False,
                    error_code=error.code,
                    data={"message": error.message},
                    request_id=error.request_id,
                )
            outcomes.append(outcome)
            if not outcome.ok and not continue_on_error:
                stopped = True
                break
        return ScriptResult(name=plan.name, outcomes=tuple(outcomes), stopped_early=stopped)


def example_script() -> dict[str, Any]:
    """Return a fresh read-only script example."""
    return {
        "name": "local-overview",
        "allow_write": False,
        "steps": [
            {
                "label": "api info",
                "namespace": "system",
                "action": "info",
                "body": {},
                "write": False,
            },
            {
                "label": "installed extensions",
                "namespace": "extensions",
                "action": "list",
                "body": {"offset": 0, "size": 10},
                "write": False,
            },
            {
                "label": "schema",
                "namespace": "extensions",
                "action": "schema",
                "body": {},
                "write": False,
            },
        ],
    }
