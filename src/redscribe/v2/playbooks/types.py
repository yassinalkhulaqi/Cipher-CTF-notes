"""Typed domain objects for the playbooks V2 feature."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

Value = str | int | float | bool | tuple[Any, ...]
Values = dict[str, Value]


class PlaybookStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class StepKind(str, Enum):
    ACTION = "action"
    CHECKLIST = "checklist"
    COMMAND = "command"
    DECISION = "decision"
    NOTE = "note"
    VERIFICATION = "verification"


class RunStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    BLOCKED = "blocked"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class VariableKind(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    CHOICE = "choice"
    SECRET = "secret"
    LIST = "list"


class ConditionOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    MATCHES = "matches"
    IN = "in"
    NOT_IN = "not_in"


class ChecklistStateValue(str, Enum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


def enum_value(value: Enum | str) -> str:
    """Return the serialized form of an enum or string."""
    return value.value if isinstance(value, Enum) else value


@dataclass(frozen=True, slots=True)
class Issue:
    """One validation or rendering diagnostic."""

    code: str
    message: str
    severity: str = "error"
    path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "path": self.path,
        }

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


@dataclass(frozen=True, slots=True)
class Condition:
    """A structured predicate over the active variable context."""

    field: str
    operator: ConditionOperator = ConditionOperator.EXISTS
    value: Value = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "operator": enum_value(self.operator),
            "value": _json_value(self.value),
        }

    def matches(self, values: Values) -> bool:
        """Evaluate this predicate against resolved variable values."""
        from redscribe.v2.playbooks.expressions import evaluate_condition

        return evaluate_condition(self, values)

    def describe(self) -> str:
        """Return a human-readable summary for editors and previews."""
        operator = enum_value(self.operator)
        if operator in ("exists", "not_exists"):
            return f"{self.field} {operator.replace('_', ' ')}"
        return f"{self.field} {operator.replace('_', ' ')} {_display(self.value)}"


@dataclass(frozen=True, slots=True)
class VariableDefinition:
    """Metadata for one variable accepted by a playbook or template."""

    key: str
    label: str = ""
    kind: VariableKind = VariableKind.TEXT
    required: bool = False
    default: Value = ""
    choices: tuple[str, ...] = ()
    description: str = ""
    secret: bool = False
    pattern: str = ""
    minimum: float | None = None
    maximum: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label or self.key,
            "kind": enum_value(self.kind),
            "required": self.required,
            "default": _json_value(self.default),
            "choices": list(self.choices),
            "description": self.description,
            "secret": self.secret or self.kind == VariableKind.SECRET,
            "pattern": self.pattern,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }

    @property
    def is_secret(self) -> bool:
        return self.secret or self.kind == VariableKind.SECRET


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    """A single observable action in a run checklist."""

    id: str
    label: str
    detail: str = ""
    required: bool = True
    condition: Condition | None = None
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "detail": self.detail,
            "required": self.required,
            "condition": self.condition.as_dict() if self.condition else None,
            "tags": list(self.tags),
        }


@dataclass(frozen=True, slots=True)
class PlaybookStep:
    """One node in a playbook DAG."""

    id: str
    title: str
    kind: StepKind = StepKind.ACTION
    summary: str = ""
    command_template: str = ""
    snippet_key: str = ""
    checklist: tuple[ChecklistItem, ...] = ()
    depends_on: tuple[str, ...] = ()
    when: tuple[Condition, ...] = ()
    variables: tuple[str, ...] = ()
    optional: bool = False
    estimated_minutes: int = 0
    tags: tuple[str, ...] = ()
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": enum_value(self.kind),
            "summary": self.summary,
            "command_template": self.command_template,
            "snippet_key": self.snippet_key,
            "checklist": [item.as_dict() for item in self.checklist],
            "depends_on": list(self.depends_on),
            "when": [condition.as_dict() for condition in self.when],
            "variables": list(self.variables),
            "optional": self.optional,
            "estimated_minutes": self.estimated_minutes,
            "tags": list(self.tags),
            "note": self.note,
        }

    def with_changes(self, **changes: Any) -> PlaybookStep:
        """Return a copy with selected fields replaced."""
        return replace(self, **changes)

    @property
    def checklist_ids(self) -> tuple[str, ...]:
        return tuple(item.id for item in self.checklist)


@dataclass(frozen=True, slots=True)
class Playbook:
    """A reusable, versioned workflow made of dependent steps."""

    id: int
    key: str
    title: str
    description: str = ""
    status: PlaybookStatus = PlaybookStatus.DRAFT
    category: str = "general"
    tags: tuple[str, ...] = ()
    version: str = "0.1.0"
    steps: tuple[PlaybookStep, ...] = ()
    variables: tuple[VariableDefinition, ...] = ()
    owner: str = ""
    created_at: str = ""
    updated_at: str = ""
    references: tuple[str, ...] = ()

    def as_dict(self, *, include_steps: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "status": enum_value(self.status),
            "category": self.category,
            "tags": list(self.tags),
            "version": self.version,
            "owner": self.owner,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "references": list(self.references),
            "step_count": len(self.steps),
            "variable_count": len(self.variables),
        }
        if include_steps:
            data["steps"] = [step.as_dict() for step in self.steps]
            data["variables"] = [item.as_dict() for item in self.variables]
        return data

    def step_map(self) -> dict[str, PlaybookStep]:
        return {step.id: step for step in self.steps}

    def variable_map(self) -> dict[str, VariableDefinition]:
        return {item.key: item for item in self.variables}

    def all_tags(self) -> set[str]:
        tags = set(self.tags)
        tags.add(self.category)
        for step in self.steps:
            tags.update(step.tags)
        return {tag.casefold() for tag in tags if tag}

    def with_changes(self, **changes: Any) -> Playbook:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class PlannedStep:
    """A step resolved for one dry-run or live run."""

    step: PlaybookStep
    command: str = ""
    variables: Values = field(default_factory=dict)
    skipped: bool = False
    reason: str = ""
    checklist: tuple[ChecklistItem, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step.as_dict(),
            "command": self.command,
            "variables": _json_values(self.variables),
            "skipped": self.skipped,
            "reason": self.reason,
            "checklist": [item.as_dict() for item in self.checklist],
        }


@dataclass(frozen=True, slots=True)
class RunPlan:
    """The deterministic execution plan for one playbook."""

    playbook_key: str
    version: str
    order: tuple[str, ...]
    layers: tuple[tuple[str, ...], ...]
    steps: tuple[PlannedStep, ...]
    missing_variables: tuple[str, ...] = ()
    warnings: tuple[Issue, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "playbook_key": self.playbook_key,
            "version": self.version,
            "order": list(self.order),
            "layers": [list(layer) for layer in self.layers],
            "steps": [step.as_dict() for step in self.steps],
            "missing_variables": list(self.missing_variables),
            "warnings": [issue.as_dict() for issue in self.warnings],
        }

    def step(self, key: str) -> PlannedStep | None:
        for item in self.steps:
            if item.step.id == key:
                return item
        return None


@dataclass(frozen=True, slots=True)
class RunEvent:
    """An appended entry in a run's audit trail."""

    seq: int
    at: str
    kind: str
    message: str
    step_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "at": self.at,
            "kind": self.kind,
            "message": self.message,
            "step_id": self.step_id,
            "data": dict(self.data),
        }


@dataclass(frozen=True, slots=True)
class StepResult:
    """The outcome reported for one step of a run."""

    status: StepStatus = StepStatus.DONE
    message: str = ""
    output: str = ""
    variables: Values = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": enum_value(self.status),
            "message": self.message,
            "output": self.output,
            "variables": _json_values(self.variables),
        }


@dataclass(frozen=True, slots=True)
class RunState:
    """Mutable execution progress for one playbook run."""

    id: int
    playbook_key: str
    version: str
    status: RunStatus
    values: Values = field(default_factory=dict)
    step_status: dict[str, StepStatus] = field(default_factory=dict)
    checklist: dict[str, str] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    events: tuple[RunEvent, ...] = ()
    current_step: str = ""
    started_at: str = ""
    updated_at: str = ""
    finished_at: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, *, include_events: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "playbook_key": self.playbook_key,
            "version": self.version,
            "status": enum_value(self.status),
            "values": _json_values(self.values),
            "step_status": {key: enum_value(value) for key, value in self.step_status.items()},
            "checklist": dict(self.checklist),
            "notes": dict(self.notes),
            "current_step": self.current_step,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "finished_at": self.finished_at,
            "context": dict(self.context),
            "event_count": len(self.events),
        }
        if include_events:
            data["events"] = [event.as_dict() for event in self.events]
        return data

    def with_changes(self, **changes: Any) -> RunState:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class SnippetRecord:
    """A reusable command stored in a snippet library."""

    id: int
    key: str
    title: str
    command: str
    description: str = ""
    tags: tuple[str, ...] = ()
    library: str = "personal"
    variables: tuple[str, ...] = ()
    usage_count: int = 0
    version: str = "1.0.0"
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "title": self.title,
            "command": self.command,
            "description": self.description,
            "tags": list(self.tags),
            "library": self.library,
            "variables": list(self.variables),
            "usage_count": self.usage_count,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def with_changes(self, **changes: Any) -> SnippetRecord:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class TemplateRecord:
    """A versioned Markdown template with declared variables."""

    id: int
    key: str
    name: str
    content: str
    description: str = ""
    tags: tuple[str, ...] = ()
    category: str = "general"
    variables: tuple[VariableDefinition, ...] = ()
    version: str = "1.0.0"
    changelog: tuple[str, ...] = ()
    default_title: str = "Untitled"

    def as_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
            "category": self.category,
            "variables": [item.as_dict() for item in self.variables],
            "version": self.version,
            "changelog": list(self.changelog),
            "default_title": self.default_title,
        }
        if include_content:
            data["content"] = self.content
        return data

    def with_changes(self, **changes: Any) -> TemplateRecord:
        return replace(self, **changes)


@dataclass(frozen=True, slots=True)
class TemplateRender:
    """The result of rendering a template with a variable context."""

    key: str
    version: str
    content: str
    used: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    warnings: tuple[Issue, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "version": self.version,
            "content": self.content,
            "used": list(self.used),
            "unresolved": list(self.unresolved),
            "warnings": [issue.as_dict() for issue in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class Recommendation:
    """A scored suggestion for a playbook, snippet, or template."""

    kind: str
    key: str
    score: float
    reason: str
    title: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "score": round(self.score, 3),
            "reason": self.reason,
            "title": self.title,
            "meta": dict(self.meta),
        }


def _json_value(value: Value) -> Any:
    return list(value) if isinstance(value, tuple) else value


def _json_values(values: Values) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in values.items()}


def _display(value: Value) -> str:
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
