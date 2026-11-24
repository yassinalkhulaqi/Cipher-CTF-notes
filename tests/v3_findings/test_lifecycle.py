"""Tests for finding lifecycle legality, guards, and reopen behavior."""

from __future__ import annotations

import pytest

from redscribe.v3.findings.lifecycle import (
    ACTIONS,
    TransitionError,
    apply_transition,
    available_actions,
    can_transition,
    checklist_complete,
    transition_graph,
)
from redscribe.v3.findings.models import (
    Finding,
    FindingState,
    RetestRecord,
    RetestVerdict,
    TaskStatus,
    finding_id,
)
from redscribe.v3.findings.remediation import new_task

VECTOR = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"


def draft() -> Finding:
    """Build a draft finding without remediation tasks."""
    return Finding(entity_id=finding_id("f1"), title="Finding", vector=VECTOR)


def with_checklist(finding: Finding) -> Finding:
    """Attach a settled remediation checklist."""
    task = new_task("fix-1", "Apply patch").with_status(TaskStatus.DONE, 5.0)
    return finding.evolve(remediation=(task,))


def retest(verdict: RetestVerdict) -> RetestRecord:
    """Build a retest result."""
    return RetestRecord(
        retest_id="retest-1",
        verdict=verdict,
        tested_by="tester",
        timestamp=6.0,
        notes="Verified in staging",
    )


def test_full_happy_path_lifecycle() -> None:
    """A finding can travel from draft all the way to closed."""
    finding = draft()
    assert available_actions(finding) == ("confirm",)

    finding, record = apply_transition(finding, "confirm", actor="analyst", timestamp=1.0)
    assert finding.state is FindingState.CONFIRMED
    assert record.source is FindingState.DRAFT
    assert record.target is FindingState.CONFIRMED
    assert len(finding.history) == 1

    finding = with_checklist(finding)
    finding, _ = apply_transition(finding, "remediate", actor="dev", timestamp=2.0)
    assert finding.state is FindingState.REMEDIATED

    finding, _ = apply_transition(
        finding,
        "retest",
        actor="tester",
        timestamp=3.0,
        retest=retest(RetestVerdict.PASS),
    )
    assert finding.state is FindingState.RETESTED
    assert finding.latest_retest is not None
    assert finding.latest_retest.passed is True

    finding, _ = apply_transition(finding, "pass", actor="lead", timestamp=4.0)
    assert finding.state is FindingState.CLOSED
    assert finding.is_open is False
    assert len(finding.history) == 4


def test_reopen_moves_closed_finding_back_to_confirmed() -> None:
    """Reopening a closed finding restores it to confirmed and records why."""
    finding = create_closed()
    updated, record = apply_transition(
        finding, "reopen", actor="lead", timestamp=9.0, note="Regression in 2.4.1"
    )
    assert updated.state is FindingState.CONFIRMED
    assert record.note == "Regression in 2.4.1"
    assert updated.metadata["reopen_count"] == 1
    assert updated.is_open is True


def test_failed_retest_returns_to_confirmed() -> None:
    """A failing retest sends a remediated finding back to confirmed."""
    finding = with_checklist(draft())
    finding, _ = apply_transition(finding, "confirm", actor="a", timestamp=1.0)
    finding, _ = apply_transition(finding, "remediate", actor="a", timestamp=2.0)
    finding, _ = apply_transition(
        finding, "retest", actor="t", timestamp=3.0, retest=retest(RetestVerdict.FAIL)
    )
    updated, _ = apply_transition(finding, "fail", actor="t", timestamp=4.0)
    assert updated.state is FindingState.CONFIRMED
    assert len(updated.retests) == 1


def test_illegal_transitions_are_rejected() -> None:
    """State edges are enforced even when the target action exists."""
    finding = draft()
    with pytest.raises(TransitionError):
        apply_transition(finding, "close", actor="a", timestamp=1.0)
    with pytest.raises(TransitionError):
        apply_transition(finding, "unknown", actor="a", timestamp=1.0)
    assert can_transition(finding, "remediate") is False
    assert "reopen" in ACTIONS


def test_remediation_guard_blocks_premature_remediation() -> None:
    """An incomplete or missing checklist blocks the remediate action."""
    finding = draft()
    finding, _ = apply_transition(finding, "confirm", actor="a", timestamp=1.0)
    assert checklist_complete(finding) is False
    assert can_transition(finding, "remediate") is False
    with pytest.raises(TransitionError, match="checklist"):
        apply_transition(finding, "remediate", actor="a", timestamp=2.0)

    partial = finding.evolve(remediation=(new_task("a", "Step one"),))
    assert can_transition(partial, "remediate") is False
    assert checklist_complete(with_checklist(finding)) is True


def test_retest_and_close_guards() -> None:
    """Closing requires a passing retest and retest rejects partial verdicts."""
    finding = with_checklist(draft())
    finding, _ = apply_transition(finding, "confirm", actor="a", timestamp=1.0)
    finding, _ = apply_transition(finding, "remediate", actor="a", timestamp=2.0)
    with pytest.raises(TransitionError, match="retest record"):
        apply_transition(finding, "retest", actor="a", timestamp=3.0)
    with pytest.raises(TransitionError, match="partial"):
        apply_transition(
            finding, "retest", actor="a", timestamp=3.0, retest=retest(RetestVerdict.PARTIAL)
        )
    finding, _ = apply_transition(
        finding, "retest", actor="a", timestamp=3.0, retest=retest(RetestVerdict.FAIL)
    )
    with pytest.raises(TransitionError, match="passing"):
        apply_transition(finding, "pass", actor="a", timestamp=4.0)


def test_dismiss_and_regress_actions() -> None:
    """Dismiss requires a note; regress returns work to confirmed."""
    finding = draft()
    finding, _ = apply_transition(finding, "confirm", actor="a", timestamp=1.0)
    with pytest.raises(TransitionError, match="note"):
        apply_transition(finding, "dismiss", actor="a", timestamp=2.0)
    dismissed, _ = apply_transition(
        finding, "dismiss", actor="a", timestamp=2.0, note="False positive"
    )
    assert dismissed.state is FindingState.CLOSED

    finding = with_checklist(finding)
    remediated, _ = apply_transition(finding, "remediate", actor="a", timestamp=2.0)
    with pytest.raises(TransitionError, match="note"):
        apply_transition(remediated, "regress", actor="a", timestamp=3.0)
    regressed, _ = apply_transition(
        remediated, "regress", actor="a", timestamp=3.0, note="Fix reverted"
    )
    assert regressed.state is FindingState.CONFIRMED


def test_transition_graph_is_complete() -> None:
    """Every state exposes at least one outgoing edge."""
    graph = transition_graph()
    assert set(graph) == {state.value for state in FindingState}
    assert graph["draft"][0]["target"] == "confirmed"
    assert any(edge["action"] == "reopen" for edge in graph["closed"])
    assert any(edge["action"] == "fail" for edge in graph["retested"])


def create_closed() -> Finding:
    """Build a closed finding by walking the full happy path."""
    finding = with_checklist(draft())
    finding, _ = apply_transition(finding, "confirm", actor="a", timestamp=1.0)
    finding, _ = apply_transition(finding, "remediate", actor="a", timestamp=2.0)
    finding, _ = apply_transition(
        finding, "retest", actor="a", timestamp=3.0, retest=retest(RetestVerdict.PASS)
    )
    finding, _ = apply_transition(finding, "pass", actor="a", timestamp=4.0)
    return finding
