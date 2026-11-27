"""Data-only contracts for the v4 playbook automation slice.

A playbook is a directed acyclic graph of declarative nodes. Nothing in this
package runs shell commands, evaluates user expressions, or opens sockets: a
run is a deterministic trace of simulated steps. The types here are immutable,
validated, and round-trip through plain dictionaries so they can cross the API
boundary without leaking behaviour.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum


class NodeKind(str, Enum):
    """Declarative operations a playbook node may represent."""

    SETUP = "setup"
    COLLECT = "collect"
    ANALYZE = "analyze"
    ENRICH = "enrich"
    REPORT = "report"
    NOTIFY = "notify"

    @classmethod
    def parse(cls, value: str) -> NodeKind:
        normalized = value.strip().casefold()
        for kind in cls:
            if kind.value == normalized:
                return kind
        raise ValueError(f"Unknown node kind: {value}")

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()

    @property
    def base_duration_ms(self) -> int:
        """A deterministic, data-only duration used by dry-run traces."""
        return {
            NodeKind.SETUP: 12,
            NodeKind.COLLECT: 48,
            NodeKind.ANALYZE: 76,
            NodeKind.ENRICH: 34,
            NodeKind.REPORT: 60,
            NodeKind.NOTIFY: 8,
        }[self]


class RunStatus(str, Enum):
    """Lifecycle states of an automation run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def parse(cls, value: str) -> RunStatus:
        normalized = value.strip().casefold()
        for status in cls:
            if status.value == normalized:
                return status
        raise ValueError(f"Unknown run status: {value}")

    @property
    def is_terminal(self) -> bool:
        return self in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }

    @property
    def label(self) -> str:
        return self.value.title()


class TraceStatus(str, Enum):
    """Per-node outcome inside a dry-run trace."""

    PLANNED = "planned"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"

    @classmethod
    def parse(cls, value: str) -> TraceStatus:
        normalized = value.strip().casefold()
        for status in cls:
            if status.value == normalized:
                return status
        raise ValueError(f"Unknown trace status: {value}")


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"

    @classmethod
    def parse(cls, value: str) -> IssueSeverity:
        normalized = value.strip().casefold()
        for severity in cls:
            if severity.value == normalized:
                return severity
        raise ValueError(f"Unknown issue severity: {value}")


class Frequency(str, Enum):
    """Supported recurrence shapes for a schedule."""

    INTERVAL = "interval"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    @classmethod
    def parse(cls, value: str) -> Frequency:
        normalized = value.strip().casefold()
        for frequency in cls:
            if frequency.value == normalized:
                return frequency
        raise ValueError(f"Unknown frequency: {value}")


def text(value: object, default: str = "") -> str:
    """Coerce an unknown decoded value to a string."""
    return value if isinstance(value, str) else default


def integer(value: object, default: int = 0) -> int:
    """Coerce an unknown decoded value to an int, rejecting bools."""
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def text_tuple(value: object) -> tuple[str, ...]:
    """Coerce an unknown decoded value to a tuple of strings."""
    if isinstance(value, list | tuple):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def integer_tuple(value: object) -> tuple[int, ...]:
    """Coerce an unknown decoded value to a tuple of ints, rejecting bools."""
    if isinstance(value, list | tuple):
        return tuple(item for item in value if not isinstance(item, bool) and isinstance(item, int))
    return ()


def string_map(value: object) -> dict[str, str]:
    """Coerce an unknown decoded value to a string-to-string mapping."""
    if isinstance(value, Mapping):
        return {str(key): text(item) for key, item in value.items()}
    return {}


def issue_dict(issue: ValidationIssue) -> dict[str, object]:
    """Serialize a validation issue (defined below) to plain data."""
    return {
        "code": issue.code,
        "message": issue.message,
        "path": issue.path,
        "severity": issue.severity.value,
    }


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A deterministic, structured validation finding."""

    code: str
    message: str
    path: str = ""
    severity: IssueSeverity = IssueSeverity.ERROR

    def __post_init__(self) -> None:
        if not self.code or not self.code.replace("_", "").isalnum():
            raise ValueError(f"Invalid issue code: {self.code}")
        if not self.message:
            raise ValueError("issue message must not be empty")

    def to_dict(self) -> dict[str, object]:
        return issue_dict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ValidationIssue:
        return cls(
            code=text(data.get("code")),
            message=text(data.get("message")),
            path=text(data.get("path")),
            severity=IssueSeverity.parse(text(data.get("severity"), "error")),
        )


@dataclass(frozen=True, slots=True)
class DagNode:
    """A declarative unit of work; parameters are inert strings only."""

    id: str
    label: str
    kind: NodeKind
    depends_on: tuple[str, ...] = ()
    params: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("node id must not be empty")
        if not self.label or not self.label.strip():
            raise ValueError(f"node label must not be empty: {self.id}")
        if self.id in self.depends_on:
            raise ValueError(f"node cannot depend on itself: {self.id}")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError(f"duplicate dependency on node: {self.id}")
        for key in self.params:
            if not key:
                raise ValueError(f"empty parameter key on node: {self.id}")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind.value,
            "depends_on": list(self.depends_on),
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DagNode:
        return cls(
            id=text(data.get("id")),
            label=text(data.get("label")),
            kind=NodeKind.parse(text(data.get("kind"), NodeKind.SETUP.value)),
            depends_on=text_tuple(data.get("depends_on")),
            params=string_map(data.get("params")),
        )

    @property
    def signature(self) -> str:
        """Stable fingerprint of the node's inert configuration."""
        params = ",".join(f"{key}={self.params[key]}" for key in sorted(self.params))
        deps = ",".join(sorted(self.depends_on))
        return f"{self.kind.value}|{deps}|{params}"


@dataclass(frozen=True, slots=True)
class DagEdge:
    """An explicit dependency edge between two node ids."""

    source: str
    target: str
    label: str = ""

    def __post_init__(self) -> None:
        if not self.source or not self.target:
            raise ValueError("edge endpoints must not be empty")
        if self.source == self.target:
            raise ValueError(f"self edge is not allowed: {self.source}")

    def to_dict(self) -> dict[str, object]:
        return {"source": self.source, "target": self.target, "label": self.label}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DagEdge:
        return cls(
            source=text(data.get("source")),
            target=text(data.get("target")),
            label=text(data.get("label")),
        )

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.target)


@dataclass(frozen=True, slots=True)
class PlaybookDag:
    """A named graph of nodes and optional explicit edges."""

    id: str
    name: str
    nodes: tuple[DagNode, ...] = ()
    edges: tuple[DagEdge, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("playbook id must not be empty")
        if not self.name or not self.name.strip():
            raise ValueError("playbook name must not be empty")
        ids = [node.id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate node ids in playbook")
        known = set(ids)
        for node in self.nodes:
            for dependency in node.depends_on:
                if dependency not in known:
                    raise ValueError(f"missing dependency {dependency} on node {node.id}")
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError(f"edge references unknown node: {edge.key}")
        if len({edge.key for edge in self.edges}) != len(self.edges):
            raise ValueError("duplicate edge in playbook")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PlaybookDag:
        raw_nodes = data.get("nodes", [])
        raw_edges = data.get("edges", [])
        node_items = raw_nodes if isinstance(raw_nodes, list | tuple) else ()
        edge_items = raw_edges if isinstance(raw_edges, list | tuple) else ()
        nodes = tuple(DagNode.from_dict(item) for item in node_items if isinstance(item, Mapping))
        edges = tuple(DagEdge.from_dict(item) for item in edge_items if isinstance(item, Mapping))
        return cls(
            id=text(data.get("id")),
            name=text(data.get("name")),
            description=text(data.get("description")),
            nodes=nodes,
            edges=edges,
        )

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(node.id for node in self.nodes)

    def node_map(self) -> dict[str, DagNode]:
        return {node.id: node for node in self.nodes}

    def with_node(self, node: DagNode) -> PlaybookDag:
        """Return a copy with ``node`` added or replaced by id."""
        nodes = (*tuple(item for item in self.nodes if item.id != node.id), node)
        return PlaybookDag(
            id=self.id,
            name=self.name,
            description=self.description,
            nodes=tuple(sorted(nodes, key=lambda item: item.id)),
            edges=self.edges,
        )

    def without_node(self, node_id: str) -> PlaybookDag:
        """Return a copy with ``node_id`` and every reference to it removed."""
        nodes = tuple(
            DagNode(
                id=item.id,
                label=item.label,
                kind=item.kind,
                depends_on=tuple(dep for dep in item.depends_on if dep != node_id),
                params=dict(item.params),
            )
            for item in self.nodes
            if item.id != node_id
        )
        edges = tuple(edge for edge in self.edges if node_id not in edge.key)
        return PlaybookDag(
            id=self.id,
            name=self.name,
            description=self.description,
            nodes=nodes,
            edges=edges,
        )


@dataclass(frozen=True, slots=True)
class TraceStep:
    """One simulated node outcome in a dry-run trace."""

    node_id: str
    status: TraceStatus
    detail: str
    duration_ms: int

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("trace node id must not be empty")
        if self.duration_ms < 0:
            raise ValueError("duration must be >= 0")

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "status": self.status.value,
            "detail": self.detail,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TraceStep:
        return cls(
            node_id=text(data.get("node_id")),
            status=TraceStatus.parse(text(data.get("status"), "planned")),
            detail=text(data.get("detail")),
            duration_ms=integer(data.get("duration_ms")),
        )


@dataclass(frozen=True, slots=True)
class RunRecord:
    """An immutable snapshot of a run at a point in its lifecycle."""

    id: str
    playbook_id: str
    status: RunStatus
    started_at: str
    finished_at: str = ""
    trace: tuple[TraceStep, ...] = ()
    trigger: str = "manual"

    def __post_init__(self) -> None:
        if not self.id or not self.playbook_id:
            raise ValueError("run id and playbook id must not be empty")
        if not self.started_at:
            raise ValueError("run start timestamp must not be empty")
        if self.status.is_terminal and not self.finished_at:
            raise ValueError("terminal run must have a finish timestamp")
        if len({step.node_id for step in self.trace}) != len(self.trace):
            raise ValueError("duplicate node in run trace")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "playbook_id": self.playbook_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "trace": [step.to_dict() for step in self.trace],
            "trigger": self.trigger,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RunRecord:
        raw_trace = data.get("trace", [])
        trace_items = raw_trace if isinstance(raw_trace, list | tuple) else ()
        trace = tuple(
            TraceStep.from_dict(item) for item in trace_items if isinstance(item, Mapping)
        )
        return cls(
            id=text(data.get("id")),
            playbook_id=text(data.get("playbook_id")),
            status=RunStatus.parse(text(data.get("status"), "pending")),
            started_at=text(data.get("started_at")),
            finished_at=text(data.get("finished_at")),
            trace=trace,
            trigger=text(data.get("trigger"), "manual"),
        )

    @property
    def duration_ms(self) -> int:
        return sum(step.duration_ms for step in self.trace)

    def with_status(
        self, status: RunStatus, finished_at: str, trace: tuple[TraceStep, ...] | None = None
    ) -> RunRecord:
        """Return a copy advanced to ``status``."""
        return RunRecord(
            id=self.id,
            playbook_id=self.playbook_id,
            status=status,
            started_at=self.started_at,
            finished_at=finished_at,
            trace=self.trace if trace is None else trace,
            trigger=self.trigger,
        )


@dataclass(frozen=True, slots=True)
class Schedule:
    """Cron-like recurrence metadata with a precomputed next run."""

    id: str
    playbook_id: str
    frequency: Frequency
    interval_minutes: int = 60
    minute: int = 0
    hour: int = 0
    day_of_week: tuple[int, ...] = ()
    day_of_month: int = 0
    next_run: str = ""
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.id or not self.playbook_id:
            raise ValueError("schedule id and playbook id must not be empty")
        if self.interval_minutes < 1:
            raise ValueError("interval_minutes must be >= 1")
        if not 0 <= self.minute <= 59:
            raise ValueError("minute must be between 0 and 59")
        if not 0 <= self.hour <= 23:
            raise ValueError("hour must be between 0 and 23")
        if any(day < 0 or day > 6 for day in self.day_of_week):
            raise ValueError("day_of_week values must be between 0 and 6")
        if self.day_of_month < 0 or self.day_of_month > 31:
            raise ValueError("day_of_month must be between 0 and 31")
        if self.frequency == Frequency.MONTHLY and self.day_of_month == 0:
            raise ValueError("monthly schedules require a day_of_month")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "playbook_id": self.playbook_id,
            "frequency": self.frequency.value,
            "interval_minutes": self.interval_minutes,
            "minute": self.minute,
            "hour": self.hour,
            "day_of_week": list(self.day_of_week),
            "day_of_month": self.day_of_month,
            "next_run": self.next_run,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Schedule:
        raw = data.get("enabled", True)
        return cls(
            id=text(data.get("id")),
            playbook_id=text(data.get("playbook_id")),
            frequency=Frequency.parse(text(data.get("frequency"), "interval")),
            interval_minutes=integer(data.get("interval_minutes"), 60),
            minute=integer(data.get("minute")),
            hour=integer(data.get("hour")),
            day_of_week=integer_tuple(data.get("day_of_week")),
            day_of_month=integer(data.get("day_of_month")),
            next_run=text(data.get("next_run")),
            enabled=raw if isinstance(raw, bool) else True,
        )

    def with_next_run(self, value: str) -> Schedule:
        """Return a copy with an advanced next-run timestamp."""
        return Schedule(
            id=self.id,
            playbook_id=self.playbook_id,
            frequency=self.frequency,
            interval_minutes=self.interval_minutes,
            minute=self.minute,
            hour=self.hour,
            day_of_week=self.day_of_week,
            day_of_month=self.day_of_month,
            next_run=value,
            enabled=self.enabled,
        )
