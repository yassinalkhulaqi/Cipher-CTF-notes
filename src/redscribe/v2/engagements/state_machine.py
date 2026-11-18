"""Explicit state machines for engagement workflow entities."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v2.engagements.models import (
    CredentialStatus,
    EngagementStatus,
    FindingStatus,
    ScopeStatus,
    ServiceStatus,
    TargetStatus,
)

Guard = Callable[[Mapping[str, Any]], tuple[bool, str]]


class TransitionError(ValueError):
    """Raised when a workflow transition is not permitted."""

    def __init__(self, message: str, *, action: str, source: str) -> None:
        super().__init__(message)
        self.action = action
        self.source = source


@dataclass(frozen=True, slots=True)
class Transition:
    """One directed state change with optional guards."""

    action: str
    source: str
    target: str
    label: str = ""
    guards: tuple[Guard, ...] = ()
    requires_note: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "from": self.source,
            "to": self.target,
            "label": self.label or self.action.replace("_", " ").title(),
            "requires_note": self.requires_note,
        }


@dataclass(frozen=True, slots=True)
class TransitionResult:
    """Outcome of a transition attempt."""

    ok: bool
    source: str
    target: str
    action: str
    reason: str = ""
    note_required: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "from": self.source,
            "to": self.target,
            "action": self.action,
            "reason": self.reason,
            "note_required": self.note_required,
        }


class StateMachine:
    """A small deterministic finite-state machine."""

    def __init__(self, name: str, transitions: Iterable[Transition]) -> None:
        self.name = name
        self.transitions = tuple(transitions)

    def states(self) -> tuple[str, ...]:
        states = {transition.source for transition in self.transitions}
        states.update(transition.target for transition in self.transitions)
        return tuple(sorted(states))

    def actions(self) -> tuple[str, ...]:
        return tuple(sorted({transition.action for transition in self.transitions}))

    def find(self, source: str, action: str) -> Transition | None:
        for transition in self.transitions:
            if transition.source == source and transition.action == action:
                return transition
        return None

    def allowed_actions(
        self, source: str, context: Mapping[str, Any] | None = None
    ) -> tuple[str, ...]:
        result: list[str] = []
        for transition in self.transitions:
            if transition.source != source:
                continue
            if context is not None and not self._guards_pass(transition, context)[0]:
                continue
            result.append(transition.action)
        return tuple(dict.fromkeys(result))

    def can_transition(
        self,
        source: str,
        action: str,
        context: Mapping[str, Any] | None = None,
    ) -> TransitionResult:
        transition = self.find(source, action)
        if transition is None:
            return TransitionResult(
                False,
                source,
                source,
                action,
                reason=f"'{action}' is not allowed from '{source}'",
            )
        if context is None:
            return TransitionResult(True, source, transition.target, action)
        passed, reason = self._guards_pass(transition, context)
        if not passed:
            return TransitionResult(False, source, source, action, reason=reason)
        return TransitionResult(
            True,
            source,
            transition.target,
            action,
            note_required=transition.requires_note and not bool(context.get("note")),
        )

    def apply(
        self,
        source: str,
        action: str,
        context: Mapping[str, Any] | None = None,
    ) -> str:
        """Apply a transition, raising when it is not permitted."""
        result = self.can_transition(source, action, context)
        if not result.ok:
            raise TransitionError(result.reason, action=action, source=source)
        if result.note_required:
            raise TransitionError(
                "A note is required for this transition", action=action, source=source
            )
        return result.target

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "states": list(self.states()),
            "actions": list(self.actions()),
            "transitions": [transition.as_dict() for transition in self.transitions],
        }

    @staticmethod
    def _guards_pass(
        transition: Transition,
        context: Mapping[str, Any],
    ) -> tuple[bool, str]:
        for guard in transition.guards:
            passed, reason = guard(context)
            if not passed:
                return False, reason
        return True, ""


def _value(enum_value: Enum | str) -> str:
    return enum_value.value if isinstance(enum_value, Enum) else enum_value


def require_field(name: str, message: str) -> Guard:
    """Build a guard that requires a non-empty context field."""

    def guard(context: Mapping[str, Any]) -> tuple[bool, str]:
        value = context.get(name)
        if isinstance(value, str) and value.strip():
            return True, ""
        if isinstance(value, (list, tuple, dict)) and value:
            return True, ""
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return True, ""
        return False, message

    return guard


def require_flag(name: str, message: str) -> Guard:
    """Build a guard that requires a boolean context flag."""

    def guard(context: Mapping[str, Any]) -> tuple[bool, str]:
        return (True, "") if bool(context.get(name)) else (False, message)

    return guard


def _transition(action: str, source: Enum | str, target: Enum | str, **kwargs: Any) -> Transition:
    return Transition(action=action, source=_value(source), target=_value(target), **kwargs)


ENGAGEMENT_MACHINE = StateMachine(
    "engagement",
    [
        _transition("activate", EngagementStatus.PLANNING, EngagementStatus.ACTIVE),
        _transition("pause", EngagementStatus.ACTIVE, EngagementStatus.PAUSED),
        _transition("resume", EngagementStatus.PAUSED, EngagementStatus.ACTIVE),
        _transition("report", EngagementStatus.ACTIVE, EngagementStatus.REPORTING),
        _transition("report", EngagementStatus.PAUSED, EngagementStatus.REPORTING),
        _transition(
            "close",
            EngagementStatus.REPORTING,
            EngagementStatus.CLOSED,
            guards=(require_flag("report_signed_off", "Report sign-off is required"),),
        ),
        _transition("reopen", EngagementStatus.CLOSED, EngagementStatus.ACTIVE),
        _transition(
            "archive",
            EngagementStatus.CLOSED,
            EngagementStatus.ARCHIVED,
            requires_note=True,
        ),
    ],
)

TARGET_MACHINE = StateMachine(
    "target",
    [
        _transition("confirm", TargetStatus.DISCOVERED, TargetStatus.CONFIRMED),
        _transition("test", TargetStatus.CONFIRMED, TargetStatus.TESTED),
        _transition("retest", TargetStatus.TESTED, TargetStatus.CONFIRMED),
        _transition(
            "exclude",
            TargetStatus.DISCOVERED,
            TargetStatus.EXCLUDED,
            guards=(require_field("reason", "An exclusion reason is required"),),
        ),
        _transition(
            "exclude",
            TargetStatus.CONFIRMED,
            TargetStatus.EXCLUDED,
            guards=(require_field("reason", "An exclusion reason is required"),),
        ),
        _transition("restore", TargetStatus.EXCLUDED, TargetStatus.DISCOVERED),
        _transition(
            "out_of_service",
            TargetStatus.CONFIRMED,
            TargetStatus.OUT_OF_SERVICE,
        ),
        _transition("restore", TargetStatus.OUT_OF_SERVICE, TargetStatus.DISCOVERED),
    ],
)

SCOPE_MACHINE = StateMachine(
    "scope",
    [
        _transition("propose", ScopeStatus.UNSPECIFIED, ScopeStatus.PENDING),
        _transition("accept", ScopeStatus.PENDING, ScopeStatus.IN_SCOPE),
        _transition("reject", ScopeStatus.PENDING, ScopeStatus.OUT_OF_SCOPE),
        _transition("waive", ScopeStatus.OUT_OF_SCOPE, ScopeStatus.WAIVED),
        _transition("revoke", ScopeStatus.WAIVED, ScopeStatus.OUT_OF_SCOPE),
        _transition("exclude", ScopeStatus.IN_SCOPE, ScopeStatus.OUT_OF_SCOPE),
        _transition("include", ScopeStatus.OUT_OF_SCOPE, ScopeStatus.IN_SCOPE),
        _transition("reset", ScopeStatus.PENDING, ScopeStatus.UNSPECIFIED),
        _transition("reset", ScopeStatus.IN_SCOPE, ScopeStatus.UNSPECIFIED),
    ],
)

FINDING_MACHINE = StateMachine(
    "finding",
    [
        _transition("submit", FindingStatus.DRAFT, FindingStatus.OPEN),
        _transition(
            "verify",
            FindingStatus.OPEN,
            FindingStatus.VERIFIED,
            guards=(require_field("evidence", "Evidence is required to verify a finding"),),
        ),
        _transition(
            "accept_risk",
            FindingStatus.VERIFIED,
            FindingStatus.ACCEPTED_RISK,
            guards=(require_field("note", "A risk acceptance note is required"),),
        ),
        _transition("reopen", FindingStatus.ACCEPTED_RISK, FindingStatus.OPEN),
        _transition("reopen", FindingStatus.CLOSED, FindingStatus.OPEN),
        _transition(
            "mark_duplicate",
            FindingStatus.DRAFT,
            FindingStatus.DUPLICATE,
            guards=(require_field("duplicate_of", "A canonical finding id is required"),),
        ),
        _transition(
            "mark_duplicate",
            FindingStatus.OPEN,
            FindingStatus.DUPLICATE,
            guards=(require_field("duplicate_of", "A canonical finding id is required"),),
        ),
        _transition("unduplicate", FindingStatus.DUPLICATE, FindingStatus.OPEN),
        _transition(
            "remediate",
            FindingStatus.VERIFIED,
            FindingStatus.REMEDIATED,
            guards=(require_field("note", "A remediation note is required"),),
        ),
        _transition(
            "remediate",
            FindingStatus.OPEN,
            FindingStatus.REMEDIATED,
            guards=(require_field("note", "A remediation note is required"),),
        ),
        _transition(
            "close",
            FindingStatus.REMEDIATED,
            FindingStatus.CLOSED,
            guards=(require_flag("retested", "A retest is required before closing"),),
        ),
    ],
)

SERVICE_MACHINE = StateMachine(
    "service",
    [
        _transition("discover", ServiceStatus.SUSPECTED, ServiceStatus.DISCOVERED),
        _transition("verify", ServiceStatus.DISCOVERED, ServiceStatus.VERIFIED),
        _transition("test", ServiceStatus.VERIFIED, ServiceStatus.TESTED),
        _transition("close", ServiceStatus.TESTED, ServiceStatus.CLOSED),
        _transition("reopen", ServiceStatus.CLOSED, ServiceStatus.DISCOVERED),
    ],
)

CREDENTIAL_MACHINE = StateMachine(
    "credential",
    [
        _transition("validate", CredentialStatus.CANDIDATE, CredentialStatus.VALID),
        _transition("invalidate", CredentialStatus.CANDIDATE, CredentialStatus.INVALID),
        _transition("invalidate", CredentialStatus.VALID, CredentialStatus.INVALID),
        _transition("revoke", CredentialStatus.VALID, CredentialStatus.REVOKED),
        _transition("rotate", CredentialStatus.VALID, CredentialStatus.ROTATED),
        _transition("rotate", CredentialStatus.REVOKED, CredentialStatus.ROTATED),
        _transition("retry", CredentialStatus.INVALID, CredentialStatus.CANDIDATE),
    ],
)

MACHINES: dict[str, StateMachine] = {
    machine.name: machine
    for machine in (
        ENGAGEMENT_MACHINE,
        TARGET_MACHINE,
        SCOPE_MACHINE,
        FINDING_MACHINE,
        SERVICE_MACHINE,
        CREDENTIAL_MACHINE,
    )
}


def machine_for(entity: str) -> StateMachine:
    """Return a named state machine or raise a clear error."""
    try:
        return MACHINES[entity]
    except KeyError as exc:
        raise KeyError(f"Unknown state machine: {entity}") from exc


def available_actions(
    entity: str, state: str, context: Mapping[str, Any] | None = None
) -> list[str]:
    """List actions available from a state for UI controls."""
    return list(machine_for(entity).allowed_actions(state, context))


def transition_context(
    *,
    note: str = "",
    reason: str = "",
    evidence: str = "",
    duplicate_of: int = 0,
    report_signed_off: bool = False,
    retested: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """Build a normalized context for guard evaluation."""
    context: dict[str, Any] = {
        "note": note,
        "reason": reason,
        "evidence": evidence,
        "duplicate_of": duplicate_of,
        "report_signed_off": report_signed_off,
        "retested": retested,
    }
    context.update(extra)
    return context


@dataclass(slots=True)
class WorkflowDescriptor:
    """Machine metadata used by API schema and frontend capability checks."""

    name: str
    states: tuple[str, ...]
    actions: tuple[str, ...]
    edges: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "states": list(self.states),
            "actions": list(self.actions),
            "edges": self.edges,
        }


def describe_workflows() -> list[dict[str, Any]]:
    """Return all workflow definitions as JSON-ready data."""
    result: list[dict[str, Any]] = []
    for machine in MACHINES.values():
        descriptor = WorkflowDescriptor(
            name=machine.name,
            states=machine.states(),
            actions=machine.actions(),
            edges=[transition.as_dict() for transition in machine.transitions],
        )
        result.append(descriptor.as_dict())
    return result
