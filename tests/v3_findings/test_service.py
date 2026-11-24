"""Tests for the finding application service and its domain events."""

from __future__ import annotations

import pytest

from redscribe.v3.capabilities import CAP_FINDINGS, Capabilities
from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityRef
from redscribe.v3.events.bus import EventBus
from redscribe.v3.findings.lifecycle import TransitionError
from redscribe.v3.findings.mappings import MappingError
from redscribe.v3.findings.remediation import RemediationError
from redscribe.v3.findings.service import (
    FINDING_CREATED,
    FINDING_DUPLICATE,
    FINDING_PROOF,
    FINDING_REMEDIATION,
    FINDING_RETEST,
    FINDING_SCORED,
    FINDING_TRANSITION,
    FindingConflictError,
    FindingService,
    FindingServiceError,
)

VECTOR = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"
LOW_VECTOR = "CVSS:4.0/AV:L/AC:H/AT:N/PR:H/UI:A/VC:N/VI:L/VA:N/SC:N/SI:N/SA:N"


def service() -> FindingService:
    """Build an isolated service with deterministic time and events."""
    return FindingService(clock=FixedClock(100.0, step=1.0), bus=EventBus())


def make(service_instance: FindingService, title: str = "SQL injection") -> str:
    """Create a finding and return its reference."""
    return service_instance.create(
        title=title,
        summary="Untrusted input reaches the query",
        vector=VECTOR,
        owner="analyst",
        target_ref=EntityRef.of("target", "app-1"),
        cwes=("CWE-89",),
        tags=("web", "sqli"),
    ).ref_string


def test_create_registers_entity_and_emits_event() -> None:
    """Creation writes both the finding and its universal entity record."""
    svc = service()
    finding = svc.create(title="Broken auth", vector=LOW_VECTOR)
    assert finding.state.value == "draft"
    assert finding.ref_string.startswith("finding:")
    assert svc.entities.find(finding.ref_string) is not None
    assert svc.bus.of_kind(FINDING_CREATED)[0].subject_ref == finding.ref_string
    assert svc.get(finding.ref_string) is finding
    with pytest.raises(FindingServiceError):
        svc.get("finding:missing")


def test_update_is_versioned_and_validated() -> None:
    """Updates bump versions, reject unknown fields, and emit events."""
    svc = service()
    ref = make(svc)
    updated = svc.update(ref, title="Renamed", summary="New details", tags=("web",))
    assert updated.version == 2
    assert updated.title == "Renamed"
    assert svc.get(ref).title == "Renamed"
    with pytest.raises(FindingConflictError):
        svc.update(ref, nonexistent="x")
    with pytest.raises(FindingConflictError):
        svc.update(ref, title="   ")


def test_score_and_severity_override() -> None:
    """Scoring stores a canonical vector and emits a scored event."""
    svc = service()
    ref = make(svc)
    scored = svc.set_score(ref, LOW_VECTOR)
    assert scored.vector == LOW_VECTOR
    assert scored.score < 5.0
    assert scored.severity.value == "low"
    assert svc.bus.of_kind(FINDING_SCORED)
    overridden = svc.set_severity_override(ref, "high")
    assert overridden.severity.value == "high"
    assert overridden.score == scored.score
    cleared = svc.set_severity_override(ref, "")
    assert "severity_override" not in cleared.metadata
    with pytest.raises(FindingConflictError):
        svc.set_severity_override(ref, "catastrophic")


def test_mappings_are_validated_and_stored() -> None:
    """Mapping updates reject unknown CWEs before mutating state."""
    svc = service()
    ref = make(svc)
    updated = svc.set_mappings(ref, cwes=("CWE-79",), cves=("CVE-2024-9999",), notes="XSS")
    assert updated.mappings.primary_cwe == "CWE-79"
    assert updated.mappings.notes == "XSS"
    with pytest.raises(MappingError):
        svc.set_mappings(ref, cwes=("CWE-999999",))


def test_remediation_and_retest_flow() -> None:
    """Checklist updates and retests are recorded with events."""
    svc = service()
    ref = make(svc)
    finding = svc.add_remediation(ref, lines="1. Patch input handling\n2. Add regression test")
    assert len(finding.remediation) == 2
    assert svc.bus.of_kind(FINDING_REMEDIATION)
    first = finding.remediation[0].task_id
    finding = svc.update_remediation_task(ref, first, "done")
    assert svc.remediation(ref)["done"] == 1
    with pytest.raises(RemediationError):
        svc.update_remediation_task(ref, "missing", "done")
    record = svc.record_retest(
        ref, verdict="pass", tested_by="tester", notes="Retested", proof_refs=("evidence:e1",)
    )
    assert record.passed is True
    assert svc.bus.of_kind(FINDING_RETEST)[0].event.payload["verdict"] == "pass"


def test_full_lifecycle_through_service() -> None:
    """The service drives confirm, remediate, retest, and close with events."""
    svc = service()
    ref = make(svc)
    svc.add_remediation(ref, lines="Patch the vulnerable endpoint")
    svc.update_remediation_task(ref, "task-1", "done")
    finding, _ = svc.transition(ref, "confirm", actor="analyst")
    assert finding.state.value == "confirmed"
    finding, _ = svc.transition(ref, "remediate", actor="dev")
    assert finding.state.value == "remediated"
    svc.record_retest(ref, verdict="pass", tested_by="tester")
    finding, _ = svc.transition(ref, "retest", actor="tester")
    assert finding.state.value == "retested"
    finding, record = svc.transition(ref, "pass", actor="lead")
    assert finding.state is not None
    assert record.target.value == "closed"
    assert len(svc.bus.of_kind(FINDING_TRANSITION)) == 4
    with pytest.raises(TransitionError):
        svc.transition(ref, "remediate", actor="dev")


def test_proof_and_duplicate_links_use_entity_graph() -> None:
    """Proof and duplicate mutations create typed universal links."""
    svc = service()
    source = make(svc, "SQL injection source")
    canonical = make(svc, "SQL injection canonical")
    block = svc.add_proof(
        source,
        block_id="p1",
        target=EntityRef.of("evidence", "e1", "Log"),
        excerpt="ERROR: invalid query",
        role="supporting",
    )
    assert block.verified is True
    assert svc.proof_report(source)["verified"] == 1
    assert svc.bus.of_kind(FINDING_PROOF)
    links = list(svc.entities.graph().links())
    assert any(link.kind.value == "evidences" for link in links)

    updated = svc.mark_duplicate(source, canonical, note="Same root cause")
    assert updated.duplicate_of is not None
    assert str(updated.duplicate_of) == canonical
    assert any(link.kind.value == "duplicates" for link in svc.entities.graph().links())
    assert svc.bus.of_kind(FINDING_DUPLICATE)
    with pytest.raises(FindingConflictError):
        svc.mark_duplicate(source, source)


def test_list_filters_and_summary() -> None:
    """List facets and dashboard summary reflect current state."""
    svc = service()
    first = make(svc, "SQL injection login")
    second = svc.create(title="Reflected XSS", vector=LOW_VECTOR, tags=("web",)).ref_string
    svc.transition(first, "confirm")
    assert len(svc.list(query="sql")) == 1
    assert len(svc.list(state="draft")) == 1
    assert len(svc.list(severity="low")) == 1
    assert len(svc.list(tag="web")) == 2
    assert len(svc.list(vector_has_threat=True)) == 0
    summary = svc.summary()
    assert summary["total"] == 2
    assert summary["open"] == 2
    assert summary["by_state"]["confirmed"] == 1
    assert summary["events"] > 2
    assert second in [item.ref_string for item in svc.all()]


def test_capability_gate_blocks_mutations() -> None:
    """Disabling the findings capability rejects writes."""
    svc = service()
    disabled = Capabilities().remove(CAP_FINDINGS)
    gated = FindingService(bus=EventBus(), capabilities=disabled)
    with pytest.raises(FindingConflictError, match="Capability"):
        gated.create(title="Blocked")
    with pytest.raises(FindingConflictError, match="Capability"):
        gated.create(title="Blocked")
    assert svc.summary()["total"] == 0


def test_remove_only_drafts() -> None:
    """Non-draft findings cannot be removed from the index."""
    svc = service()
    ref = make(svc)
    svc.transition(ref, "confirm")
    with pytest.raises(FindingConflictError):
        svc.remove(ref)
    draft = svc.create(title="Temporary").ref_string
    svc.remove(draft)
    assert svc.find(draft) is None
