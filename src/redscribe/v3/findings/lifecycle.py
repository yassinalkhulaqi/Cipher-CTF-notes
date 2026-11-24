"""Finding lifecycle state machine with legal transitions and guards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v3.events.types import EventSeverity
from redscribe.v3.findings.models import (
    Finding,
    FindingState,
    RetestRecord,
    RetestVerdict,
    TransitionRecord,
)


class TransitionError(ValueError):
    """Raised when a lifecycle transition is illegal or missing a prerequisite."""


@dataclass(frozen=True, slots=True)
class TransitionRule:
    """One edge in the finding lifecycle graph."""

    action: str
    sources: tuple[FindingState, ...]
    target: FindingState
    requires_checklist: bool = False
    requires_retest: bool = False
    requires_note: bool = False
    requires_failed_retest: bool = False
    severity: EventSeverity = EventSeverity.INFO

    def allows(self, state: FindingState) -> bool:
        """Whether the rule applies to a source state."""
        return state in self.sources

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "action": self.action,
            "sources": [state.value for state in self.sources],
            "target": self.target.value,
            "requires_checklist": self.requires_checklist,
            "requires_retest": self.requires_retest,
            "requires_note": self.requires_note,
            "requires_failed_retest": self.requires_failed_retest,
        }


RULES: tuple[TransitionRule, ...] = (
    TransitionRule(
        action="confirm",
        sources=(FindingState.DRAFT,),
        target=FindingState.CONFIRMED,
        severity=EventSeverity.NOTICE,
    ),
    TransitionRule(
        action="remediate",
        sources=(FindingState.CONFIRMED,),
        target=FindingState.REMEDIATED,
        requires_checklist=True,
        severity=EventSeverity.NOTICE,
    ),
    TransitionRule(
        action="retest",
        sources=(FindingState.REMEDIATED,),
        target=FindingState.RETESTED,
        requires_retest=True,
        severity=EventSeverity.NOTICE,
    ),
    TransitionRule(
        action="pass",
        sources=(FindingState.RETESTED,),
        target=FindingState.CLOSED,
        requires_retest=True,
        severity=EventSeverity.NOTICE,
    ),
    TransitionRule(
        action="fail",
        sources=(FindingState.RETESTED,),
        target=FindingState.CONFIRMED,
        requires_failed_retest=True,
        severity=EventSeverity.WARNING,
    ),
    TransitionRule(
        action="dismiss",
        sources=(FindingState.CONFIRMED,),
        target=FindingState.CLOSED,
        requires_note=True,
        severity=EventSeverity.WARNING,
    ),
    TransitionRule(
        action="reopen",
        sources=(FindingState.CLOSED,),
        target=FindingState.CONFIRMED,
        requires_note=True,
        severity=EventSeverity.WARNING,
    ),
    TransitionRule(
        action="regress",
        sources=(FindingState.REMEDIATED, FindingState.RETESTED),
        target=FindingState.CONFIRMED,
        requires_note=True,
        severity=EventSeverity.WARNING,
    ),
)

RULES_BY_ACTION = {rule.action: rule for rule in RULES}
ACTIONS = tuple(rule.action for rule in RULES)


def rules_for(state: FindingState) -> tuple[TransitionRule, ...]:
    """Return all rules that can fire from a state before guard checks."""
    return tuple(rule for rule in RULES if rule.allows(state))


def checklist_complete(finding: Finding) -> bool:
    """Whether the remediation checklist is present and fully settled."""
    return bool(finding.remediation) and all(task.status.is_settled for task in finding.remediation)


def rule_for(action: str, state: FindingState) -> TransitionRule:
    """Look up a rule by action and source state."""
    rule = RULES_BY_ACTION.get(action)
    if rule is None:
        raise TransitionError(f"Unknown lifecycle action: {action}")
    if not rule.allows(state):
        raise TransitionError(
            f"Cannot {action} a finding in state {state.value}; allowed from "
            + ", ".join(item.value for item in rule.sources)
        )
    return rule


def check_guards(
    finding: Finding,
    rule: TransitionRule,
    *,
    note: str = "",
    retest: RetestRecord | None = None,
) -> None:
    """Validate all prerequisites for a transition."""
    if rule.requires_checklist and not checklist_complete(finding):
        raise TransitionError("Remediation checklist must be complete before this transition")
    if rule.requires_note and not note.strip():
        raise TransitionError(f"A note is required when using '{rule.action}'")
    if rule.requires_retest:
        effective = retest or finding.latest_retest
        if effective is None:
            raise TransitionError("A retest record is required for this transition")
        if rule.action == "pass" and effective.verdict is not RetestVerdict.PASS:
            raise TransitionError("Closing requires a passing retest verdict")
        if rule.action == "retest" and effective.verdict is RetestVerdict.PARTIAL:
            raise TransitionError("A partial retest cannot complete the retest stage")
    if rule.requires_failed_retest:
        latest = retest or finding.latest_retest
        if latest is None or latest.verdict is not RetestVerdict.FAIL:
            raise TransitionError("A failing retest is required to return to confirmed")


def can_transition(
    finding: Finding,
    action: str,
    *,
    note: str = "",
    retest: RetestRecord | None = None,
) -> bool:
    """Return whether a transition is legal and all its guards pass."""
    rule = RULES_BY_ACTION.get(action)
    if rule is None or not rule.allows(finding.state):
        return False
    try:
        check_guards(finding, rule, note=note, retest=retest)
    except TransitionError:
        return False
    return True


def available_actions(
    finding: Finding,
    *,
    note: str = "",
    retest: RetestRecord | None = None,
) -> tuple[str, ...]:
    """List actions currently available on a finding."""
    return tuple(
        rule.action
        for rule in rules_for(finding.state)
        if can_transition(finding, rule.action, note=note, retest=retest)
    )


def apply_transition(
    finding: Finding,
    action: str,
    *,
    actor: str,
    timestamp: float,
    note: str = "",
    retest: RetestRecord | None = None,
) -> tuple[Finding, TransitionRecord]:
    """Apply a legal transition and return the new finding plus its history event."""
    rule = rule_for(action, finding.state)
    check_guards(finding, rule, note=note, retest=retest)
    record = TransitionRecord(
        action=action,
        source=finding.state,
        target=rule.target,
        actor=actor,
        timestamp=timestamp,
        note=note,
        retest_id=retest.retest_id if retest else "",
    )
    metadata = dict(finding.metadata)
    reopen_count = int(metadata.get("reopen_count", 0))
    if action == "reopen":
        metadata["reopen_count"] = reopen_count + 1
    updated = finding.evolve(
        state=rule.target,
        history=(*finding.history, record),
        retests=(*finding.retests, retest) if retest else finding.retests,
        metadata=metadata,
        updated_at=timestamp,
    )
    return updated, record


def transition_graph() -> dict[str, list[dict[str, str]]]:
    """Return the full state graph for documentation and UI rendering."""
    graph: dict[str, list[dict[str, str]]] = {state.value: [] for state in FindingState}
    for rule in RULES:
        for source in rule.sources:
            graph[source.value].append(
                {
                    "action": rule.action,
                    "target": rule.target.value,
                    "label": rule.action.replace("_", " ").title(),
                }
            )
    return graph


def state_summary(finding: Finding) -> dict[str, Any]:
    """Return a UI-ready lifecycle summary."""
    return {
        "state": finding.state.value,
        "actions": list(available_actions(finding)),
        "transitions": len(finding.history),
        "reopens": int(finding.metadata.get("reopen_count", 0)),
        "last_transition": finding.history[-1].as_dict() if finding.history else None,
        "checklist_complete": checklist_complete(finding),
    }
