from __future__ import annotations

import pytest

from redscribe.v2.engagements.models import (
    CredentialStatus,
    EngagementStatus,
    FindingStatus,
    ScopeStatus,
    ServiceStatus,
    TargetStatus,
)
from redscribe.v2.engagements.state_machine import (
    CREDENTIAL_MACHINE,
    ENGAGEMENT_MACHINE,
    FINDING_MACHINE,
    SCOPE_MACHINE,
    SERVICE_MACHINE,
    TARGET_MACHINE,
    StateMachine,
    Transition,
    TransitionError,
    available_actions,
    describe_workflows,
    machine_for,
    require_field,
    require_flag,
    transition_context,
)


def test_transition_as_dict_derives_label() -> None:
    transition = Transition(action="mark_duplicate", source="draft", target="duplicate")
    payload = transition.as_dict()
    assert payload["label"] == "Mark Duplicate"
    assert payload["requires_note"] is False
    assert (
        Transition(
            action="archive", source="closed", target="archived", requires_note=True
        ).as_dict()["requires_note"]
        is True
    )


def test_transition_result_as_dict_is_json_ready() -> None:
    result = ENGAGEMENT_MACHINE.can_transition("planning", "activate")
    payload = result.as_dict()
    assert set(payload) == {"ok", "from", "to", "action", "reason", "note_required"}
    assert payload["from"] == "planning"
    assert payload["to"] == "active"


def test_state_machine_states_and_actions_are_sorted_and_unique() -> None:
    states = ENGAGEMENT_MACHINE.states()
    assert states == tuple(sorted(set(states)))
    actions = ENGAGEMENT_MACHINE.actions()
    assert actions == tuple(sorted(set(actions)))
    assert "report" in actions
    assert ENGAGEMENT_MACHINE.find("active", "report") is not None
    assert ENGAGEMENT_MACHINE.find("archived", "activate") is None


def test_allowed_actions_filters_guarded_transitions() -> None:
    assert ENGAGEMENT_MACHINE.allowed_actions("reporting") == ("close",)
    assert ENGAGEMENT_MACHINE.allowed_actions("reporting", {"report_signed_off": False}) == ()
    assert ENGAGEMENT_MACHINE.allowed_actions("reporting", {"report_signed_off": True}) == (
        "close",
    )
    assert ENGAGEMENT_MACHINE.allowed_actions("archived") == ()


def test_can_transition_rejects_unknown_action() -> None:
    result = ENGAGEMENT_MACHINE.can_transition("planning", "archive")
    assert result.ok is False
    assert result.source == "planning"
    assert result.target == "planning"
    assert "not allowed" in result.reason


def test_apply_returns_target_state() -> None:
    assert ENGAGEMENT_MACHINE.apply("planning", "activate") == "active"
    assert ENGAGEMENT_MACHINE.apply("active", "pause") == "paused"
    assert ENGAGEMENT_MACHINE.apply("paused", "resume") == "active"
    assert ENGAGEMENT_MACHINE.apply("active", "report") == "reporting"


def test_apply_raises_transition_error_with_context() -> None:
    with pytest.raises(TransitionError) as excinfo:
        ENGAGEMENT_MACHINE.apply("reporting", "close", {"report_signed_off": False})
    assert excinfo.value.action == "close"
    assert excinfo.value.source == "reporting"
    assert "sign-off" in str(excinfo.value)


def test_note_requiring_transition_reports_note_required() -> None:
    result = ENGAGEMENT_MACHINE.can_transition("closed", "archive", {"note": ""})
    assert result.ok is True
    assert result.note_required is True
    with pytest.raises(TransitionError, match="note is required"):
        ENGAGEMENT_MACHINE.apply("closed", "archive", {"note": ""})
    assert ENGAGEMENT_MACHINE.apply("closed", "archive", {"note": "retired"}) == "archived"


def test_require_field_guard_accepts_expected_shapes() -> None:
    guard = require_field("evidence", "evidence is required")
    assert guard({"evidence": "screenshot"}) == (True, "")
    assert guard({"evidence": "  "}) == (False, "evidence is required")
    assert guard({"evidence": ["a"]})[0] is True
    assert guard({"evidence": {"a": 1}})[0] is True
    assert guard({"evidence": 3})[0] is True
    assert guard({"evidence": True})[0] is False
    assert guard({})[0] is False


def test_require_flag_guard_requires_truthy_boolean() -> None:
    guard = require_flag("retested", "retest required")
    assert guard({"retested": True}) == (True, "")
    assert guard({"retested": "yes"}) == (True, "")
    assert guard({"retested": False}) == (False, "retest required")
    assert guard({})[0] is False


def test_custom_machine_evaluates_multiple_guards() -> None:
    machine = StateMachine(
        "custom",
        [
            Transition(
                action="finish",
                source="start",
                target="done",
                guards=(
                    require_field("actor", "actor required"),
                    require_flag("approved", "approval required"),
                ),
            )
        ],
    )
    assert machine.can_transition("start", "finish", {"actor": "a", "approved": True}).ok is True
    assert machine.can_transition("start", "finish", {"approved": True}).reason == "actor required"
    assert machine.can_transition("start", "finish", {"actor": "a"}).reason == "approval required"


def test_state_machine_as_dict_includes_edges() -> None:
    payload = TARGET_MACHINE.as_dict()
    assert payload["name"] == "target"
    assert "discovered" in payload["states"]
    assert any(edge["action"] == "exclude" for edge in payload["transitions"])


def test_machine_for_returns_known_machines() -> None:
    assert machine_for("engagement") is ENGAGEMENT_MACHINE
    assert machine_for("target") is TARGET_MACHINE
    assert machine_for("scope") is SCOPE_MACHINE
    assert machine_for("finding") is FINDING_MACHINE
    assert machine_for("service") is SERVICE_MACHINE
    assert machine_for("credential") is CREDENTIAL_MACHINE
    with pytest.raises(KeyError, match="Unknown state machine"):
        machine_for("unknown")


def test_available_actions_wraps_allowed_actions() -> None:
    assert available_actions("engagement", "planning") == ["activate"]
    assert available_actions("engagement", "reporting", {"report_signed_off": True}) == ["close"]
    assert available_actions("finding", "draft", {"duplicate_of": 3}) == [
        "submit",
        "mark_duplicate",
    ]


def test_transition_context_normalizes_guard_fields() -> None:
    context = transition_context(note="note", reason="reason", evidence="evidence", duplicate_of=7)
    assert context["note"] == "note"
    assert context["reason"] == "reason"
    assert context["evidence"] == "evidence"
    assert context["duplicate_of"] == 7
    assert context["report_signed_off"] is False
    assert context["retested"] is False


def test_transition_context_accepts_extra_fields() -> None:
    context = transition_context(custom="value", report_signed_off=True)
    assert context["custom"] == "value"
    assert context["report_signed_off"] is True


def test_describe_workflows_covers_all_machines() -> None:
    descriptions = describe_workflows()
    assert [item["name"] for item in descriptions] == [
        "engagement",
        "target",
        "scope",
        "finding",
        "service",
        "credential",
    ]
    assert all(item["states"] and item["actions"] and item["edges"] for item in descriptions)


@pytest.mark.parametrize(
    ("machine", "source", "action", "target"),
    [
        (ENGAGEMENT_MACHINE, "closed", "reopen", EngagementStatus.ACTIVE.value),
        (TARGET_MACHINE, "discovered", "confirm", TargetStatus.CONFIRMED.value),
        (TARGET_MACHINE, "tested", "retest", TargetStatus.CONFIRMED.value),
        (TARGET_MACHINE, "excluded", "restore", TargetStatus.DISCOVERED.value),
        (SCOPE_MACHINE, "unspecified", "propose", ScopeStatus.PENDING.value),
        (SCOPE_MACHINE, "pending", "reject", ScopeStatus.OUT_OF_SCOPE.value),
        (SCOPE_MACHINE, "waived", "revoke", ScopeStatus.OUT_OF_SCOPE.value),
        (FINDING_MACHINE, "draft", "submit", FindingStatus.OPEN.value),
        (FINDING_MACHINE, "duplicate", "unduplicate", FindingStatus.OPEN.value),
        (FINDING_MACHINE, "closed", "reopen", FindingStatus.OPEN.value),
        (SERVICE_MACHINE, "suspected", "discover", ServiceStatus.DISCOVERED.value),
        (SERVICE_MACHINE, "closed", "reopen", ServiceStatus.DISCOVERED.value),
        (CREDENTIAL_MACHINE, "candidate", "validate", CredentialStatus.VALID.value),
        (CREDENTIAL_MACHINE, "invalid", "retry", CredentialStatus.CANDIDATE.value),
    ],
)
def test_simple_transitions(machine: StateMachine, source: str, action: str, target: str) -> None:
    assert machine.apply(source, action) == target


@pytest.mark.parametrize(
    ("machine", "source", "action", "context", "reason"),
    [
        (TARGET_MACHINE, "discovered", "exclude", {}, "exclusion reason"),
        (FINDING_MACHINE, "open", "verify", {}, "Evidence is required"),
        (FINDING_MACHINE, "verified", "accept_risk", {}, "risk acceptance note"),
        (FINDING_MACHINE, "open", "mark_duplicate", {}, "canonical finding id"),
        (FINDING_MACHINE, "verified", "remediate", {}, "remediation note"),
        (FINDING_MACHINE, "remediated", "close", {}, "retest is required"),
    ],
)
def test_guarded_transitions_report_reason(
    machine: StateMachine, source: str, action: str, context: dict[str, object], reason: str
) -> None:
    result = machine.can_transition(source, action, transition_context(**context))
    assert result.ok is False
    assert reason in result.reason


def test_finding_full_lifecycle_with_guards() -> None:
    assert FINDING_MACHINE.apply("draft", "submit") == "open"
    assert FINDING_MACHINE.apply("open", "verify", {"evidence": "screenshot"}) == "verified"
    assert (
        FINDING_MACHINE.apply("verified", "accept_risk", {"note": "business owner accepted"})
        == "accepted_risk"
    )
    assert FINDING_MACHINE.apply("accepted_risk", "reopen") == "open"
    assert FINDING_MACHINE.apply("open", "remediate", {"note": "patched"}) == "remediated"
    assert FINDING_MACHINE.apply("remediated", "close", {"retested": True}) == "closed"


def test_engagement_full_lifecycle_with_guards() -> None:
    assert ENGAGEMENT_MACHINE.apply("planning", "activate") == "active"
    assert ENGAGEMENT_MACHINE.apply("active", "pause") == "paused"
    assert ENGAGEMENT_MACHINE.apply("paused", "report") == "reporting"
    assert ENGAGEMENT_MACHINE.apply("reporting", "close", {"report_signed_off": True}) == "closed"
    assert ENGAGEMENT_MACHINE.apply("closed", "archive", {"note": "complete"}) == "archived"
