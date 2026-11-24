"""Data-only vocabulary for V3 playbook automation.

Nothing in this package can start a process, open a socket, or read a command
line. A playbook is a declarative document that produces mutations of
*documents* and *workflow metadata* only. The enums and records here are the
shared vocabulary used by the compiler, executor, traces and API namespace.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

STEP_CREATE_NOTE = "create_note"
STEP_CREATE_FINDING = "create_finding"
STEP_ATTACH_EVIDENCE = "attach_evidence"
STEP_RENDER_SECTION = "render_section"
STEP_EMIT_EVENT = "emit_event"

STEP_KINDS: tuple[str, ...] = (
    STEP_CREATE_NOTE,
    STEP_CREATE_FINDING,
    STEP_ATTACH_EVIDENCE,
    STEP_RENDER_SECTION,
    STEP_EMIT_EVENT,
)


class StepKind(str, Enum):
    """The complete, closed set of operations an automation step may perform."""

    CREATE_NOTE = STEP_CREATE_NOTE
    CREATE_FINDING = STEP_CREATE_FINDING
    ATTACH_EVIDENCE = STEP_ATTACH_EVIDENCE
    RENDER_SECTION = STEP_RENDER_SECTION
    EMIT_EVENT = STEP_EMIT_EVENT

    @classmethod
    def parse(cls, value: str) -> StepKind:
        """Parse a step kind with a stable error message."""
        normalized = value.strip().casefold()
        for kind in cls:
            if kind.value == normalized:
                return kind
        raise ValueError(f"Unsupported automation step kind: {value}")

    @property
    def creates_entity(self) -> bool:
        """Whether this step creates a new entity record."""
        return self in (StepKind.CREATE_NOTE, StepKind.CREATE_FINDING, StepKind.RENDER_SECTION)


class VariableKind(str, Enum):
    """Types accepted by the typed variable resolver."""

    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    CHOICE = "choice"
    LIST = "list"
    ENTITY_REF = "entity_ref"

    @classmethod
    def parse(cls, value: str) -> VariableKind:
        """Parse a variable kind with a stable error message."""
        normalized = value.strip().casefold().replace("-", "_")
        for kind in cls:
            if kind.value == normalized:
                return kind
        raise ValueError(f"Unknown variable kind: {value}")


class ConditionOperator(str, Enum):
    """Operators supported by step guards."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    IN = "in"


_ORDER_COMPARATORS: dict[ConditionOperator, Callable[[Any, Any], bool]] = {
    ConditionOperator.GT: lambda left, right: left > right,
    ConditionOperator.GTE: lambda left, right: left >= right,
    ConditionOperator.LT: lambda left, right: left < right,
    ConditionOperator.LTE: lambda left, right: left <= right,
}


class RunMode(str, Enum):
    """Execution mode. Dry runs never call a mutating sink."""

    DRY_RUN = "dry_run"
    LIVE = "live"


class RunStatus(str, Enum):
    """Terminal state persisted for a run record."""

    PLANNED = "planned"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class StepStatus(str, Enum):
    """Outcome of one step in a run trace."""

    EXECUTED = "executed"
    PLANNED = "planned"
    SKIPPED = "skipped"
    FAILED = "failed"


class Frequency(str, Enum):
    """Recurrence frequencies supported by the rule expander."""

    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    @classmethod
    def parse(cls, value: str) -> Frequency:
        """Parse a frequency value."""
        normalized = value.strip().casefold()
        for frequency in cls:
            if frequency.value == normalized:
                return frequency
        raise ValueError(f"Unknown recurrence frequency: {value}")


Value = str | int | float | bool | None | list[Any] | dict[str, Any]


def as_text(value: Any) -> str:
    """Render a JSON value in a compact, deterministic form."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


@dataclass(frozen=True, slots=True)
class VariableDefinition:
    """Validation metadata for one typed playbook variable."""

    key: str
    kind: VariableKind = VariableKind.TEXT
    label: str = ""
    required: bool = False
    default: Value = ""
    choices: tuple[str, ...] = ()
    description: str = ""
    secret: bool = False
    pattern: str = ""
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        if not self.key or len(self.key) > 64:
            raise ValueError("Variable key must be 1-64 characters")
        if not self.key.replace("_", "").isalnum():
            raise ValueError(f"Invalid variable key: {self.key}")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError(f"Invalid range for variable: {self.key}")

    @property
    def is_secret(self) -> bool:
        """Whether the value must be masked in traces and records."""
        return self.secret

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "label": self.label or self.key,
            "kind": self.kind.value,
            "required": self.required,
            "default": self.default,
            "choices": list(self.choices),
            "description": self.description,
            "secret": self.is_secret,
            "pattern": self.pattern,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass(frozen=True, slots=True)
class StepCondition:
    """A structured predicate evaluated against resolved variables."""

    field: str
    operator: ConditionOperator = ConditionOperator.EXISTS
    value: Value = None

    def __post_init__(self) -> None:
        if not self.field or len(self.field) > 128:
            raise ValueError("Condition field must be 1-128 characters")

    def matches(self, values: dict[str, Any]) -> bool:
        """Evaluate this condition against a resolution context."""
        current: Any = values
        for part in self.field.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                current = None
                break
        operator = self.operator
        if operator is ConditionOperator.EXISTS:
            return current is not None
        if operator is ConditionOperator.NOT_EXISTS:
            return current is None
        if operator is ConditionOperator.EQ:
            return bool(current == self.value)
        if operator is ConditionOperator.NE:
            return bool(current != self.value)
        if operator is ConditionOperator.IN:
            return isinstance(self.value, list) and current in self.value
        if operator is ConditionOperator.CONTAINS:
            return isinstance(current, (str, list, dict)) and self.value in current
        if current is None or self.value is None:
            return False
        comparator = _ORDER_COMPARATORS.get(operator)
        if comparator is None:
            return False
        try:
            return bool(comparator(current, self.value))
        except TypeError:
            return False

    def describe(self) -> str:
        """Return a human-readable condition summary for editors."""
        if self.operator in (ConditionOperator.EXISTS, ConditionOperator.NOT_EXISTS):
            return f"{self.field} {self.operator.value.replace('_', ' ')}"
        return f"{self.field} {self.operator.value} {as_text(self.value)}"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "field": self.field,
            "operator": self.operator.value,
            "value": self.value,
            "description": self.describe(),
        }


@dataclass(frozen=True, slots=True)
class StepDefinition:
    """One node in a playbook DAG."""

    id: str
    title: str
    kind: StepKind = StepKind.CREATE_NOTE
    depends_on: tuple[str, ...] = ()
    inputs: dict[str, Any] = field(default_factory=dict)
    condition: StepCondition | None = None
    output: str = ""
    optional: bool = False
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or len(self.id) > 64:
            raise ValueError("Step id must be 1-64 characters")
        if any(char.isspace() for char in self.id):
            raise ValueError(f"Step id cannot contain whitespace: {self.id}")
        if not self.title.strip():
            raise ValueError(f"Step title cannot be blank: {self.id}")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind.value,
            "depends_on": list(self.depends_on),
            "inputs": dict(self.inputs),
            "condition": self.condition.as_dict() if self.condition else None,
            "output": self.output,
            "optional": self.optional,
            "tags": list(self.tags),
        }


@dataclass(frozen=True, slots=True)
class RecurrenceRule:
    """Deterministic, UTC-based recurrence specification for a playbook."""

    frequency: Frequency = Frequency.DAILY
    interval: int = 1
    by_weekday: tuple[int, ...] = ()
    by_month_day: int | None = None
    hour: int = 9
    minute: int = 0
    start_at: float = 0.0
    end_at: float = 0.0
    count: int = 0

    def __post_init__(self) -> None:
        if self.interval < 1:
            raise ValueError("Recurrence interval must be at least 1")
        if not 0 <= self.hour <= 23 or not 0 <= self.minute <= 59:
            raise ValueError("Recurrence time must be a valid UTC hour and minute")
        if any(day < 0 or day > 6 for day in self.by_weekday):
            raise ValueError("Weekdays must be in 0 (Monday) .. 6 (Sunday)")
        if self.by_month_day is not None and not 1 <= self.by_month_day <= 31:
            raise ValueError("Month day must be 1-31")
        if self.end_at and self.end_at < self.start_at:
            raise ValueError("Recurrence end must follow its start")
        if self.count < 0:
            raise ValueError("Recurrence count cannot be negative")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "frequency": self.frequency.value,
            "interval": self.interval,
            "by_weekday": list(self.by_weekday),
            "by_month_day": self.by_month_day,
            "hour": self.hour,
            "minute": self.minute,
            "start_at": self.start_at,
            "end_at": self.end_at,
            "count": self.count,
        }


@dataclass(frozen=True, slots=True)
class PlaybookDefinition:
    """A validated, immutable playbook document."""

    id: str
    title: str
    steps: tuple[StepDefinition, ...]
    variables: tuple[VariableDefinition, ...] = ()
    description: str = ""
    version: int = 1
    tags: tuple[str, ...] = ()
    recurrence: RecurrenceRule | None = None

    def __post_init__(self) -> None:
        if not self.id or len(self.id) > 128:
            raise ValueError("Playbook id must be 1-128 characters")
        if not self.title.strip():
            raise ValueError("Playbook title cannot be blank")
        if self.version < 1:
            raise ValueError("Playbook version must be at least 1")

    @property
    def ref(self) -> str:
        """Canonical entity reference for this playbook."""
        return f"playbook:{self.id}"

    def step(self, step_id: str) -> StepDefinition:
        """Return a step by id or raise ``KeyError``."""
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(f"Unknown step: {step_id}")

    def variable(self, key: str) -> VariableDefinition | None:
        """Return a variable definition by key."""
        for definition in self.variables:
            if definition.key == key:
                return definition
        return None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "ref": self.ref,
            "title": self.title,
            "description": self.description,
            "version": self.version,
            "tags": list(self.tags),
            "steps": [step.as_dict() for step in self.steps],
            "variables": [definition.as_dict() for definition in self.variables],
            "recurrence": self.recurrence.as_dict() if self.recurrence else None,
        }


@dataclass(frozen=True, slots=True)
class MutationIntent:
    """A fully resolved, inspectable data mutation requested by one step."""

    step_id: str
    kind: StepKind
    target: str
    payload: dict[str, Any]
    key: str
    inverse: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "step_id": self.step_id,
            "kind": self.kind.value,
            "target": self.target,
            "payload": dict(self.payload),
            "key": self.key,
            "inverse": dict(self.inverse),
        }


@dataclass(frozen=True, slots=True)
class MutationResult:
    """The predicted or applied outcome of a :class:`MutationIntent`."""

    intent: MutationIntent
    ref: str
    applied: bool
    before: Value = None
    after: Value = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "intent": self.intent.as_dict(),
            "ref": self.ref,
            "applied": self.applied,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True, slots=True)
class TraceEntry:
    """One immutable entry of a dry-run or execution trace."""

    index: int
    step_id: str
    status: StepStatus
    kind: StepKind
    message: str
    variables: dict[str, Any] = field(default_factory=dict)
    result: MutationResult | None = None
    chain: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "index": self.index,
            "step_id": self.step_id,
            "status": self.status.value,
            "kind": self.kind.value,
            "message": self.message,
            "variables": dict(self.variables),
            "result": self.result.as_dict() if self.result else None,
            "chain": self.chain,
        }


@dataclass(frozen=True, slots=True)
class DryRunTrace:
    """A complete, ordered, hash-chained record of would-be mutations."""

    playbook_ref: str
    mode: RunMode
    entries: tuple[TraceEntry, ...]
    variables: dict[str, Any] = field(default_factory=dict)
    digest: str = ""
    writes: int = 0
    input_fingerprint: str = ""
    state_digest: str = ""

    @property
    def mutations(self) -> tuple[MutationIntent, ...]:
        """Return every mutation recorded by this trace."""
        return tuple(entry.result.intent for entry in self.entries if entry.result is not None)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "playbook_ref": self.playbook_ref,
            "mode": self.mode.value,
            "entries": [entry.as_dict() for entry in self.entries],
            "variables": dict(self.variables),
            "digest": self.digest,
            "writes": self.writes,
            "input_fingerprint": self.input_fingerprint,
            "state_digest": self.state_digest,
        }


@dataclass(frozen=True, slots=True)
class RunRecord:
    """A persisted run in the ``v3_run_records`` table."""

    id: str
    playbook_ref: str
    status: RunStatus
    mode: RunMode
    started_at: float
    finished_at: float = 0.0
    trace: tuple[TraceEntry, ...] = ()
    variables: dict[str, Any] = field(default_factory=dict)
    input_fingerprint: str = ""
    trace_digest: str = ""
    state_digest: str = ""
    rollback_of: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "playbook_ref": self.playbook_ref,
            "status": self.status.value,
            "mode": self.mode.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "trace": [entry.as_dict() for entry in self.trace],
            "variables": dict(self.variables),
            "input_fingerprint": self.input_fingerprint,
            "trace_digest": self.trace_digest,
            "state_digest": self.state_digest,
            "rollback_of": self.rollback_of,
        }


@dataclass(frozen=True, slots=True)
class DiffEntry:
    """One field-level difference between two traces or run records."""

    path: str
    before: Value
    after: Value

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"path": self.path, "before": self.before, "after": self.after}


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A validation diagnostic with a stable code and JSON path."""

    code: str
    message: str
    path: str = ""
    severity: str = "error"

    @property
    def is_error(self) -> bool:
        """Whether this issue blocks execution."""
        return self.severity == "error"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "severity": self.severity,
        }
