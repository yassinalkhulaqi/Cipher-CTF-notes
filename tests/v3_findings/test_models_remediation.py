"""Tests for immutable finding models and remediation checklists."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.types import EntityKind, EntityRef
from redscribe.v3.findings.models import (
    CweMapping,
    Finding,
    FindingMappings,
    FindingState,
    ProofRole,
    RetestVerdict,
    TaskStatus,
    finding_id,
    hash_excerpt,
    parse_finding_ref,
)
from redscribe.v3.findings.proof import make_proof
from redscribe.v3.findings.remediation import (
    RemediationError,
    add_task,
    checklist_issues,
    new_task,
    plan_for,
    task_from_lines,
    update_task,
)

VECTOR = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"
TARGET = EntityRef.of("target", "app-01", "Application 01")


def make_finding(**overrides: object) -> Finding:
    """Build a minimal valid finding for model tests."""
    values: dict[str, object] = {
        "entity_id": finding_id("finding-1"),
        "title": "SQL injection in login form",
        "vector": VECTOR,
        "target_ref": TARGET,
        "mappings": FindingMappings(cwes=("CWE-89",), cves=("CVE-2024-0001",)),
        "created_at": 100.0,
        "updated_at": 100.0,
    }
    values.update(overrides)
    return Finding(**values)  # type: ignore[arg-type]


def test_finding_identity_and_derived_fields() -> None:
    """A finding derives its reference, score, severity, and open state."""
    finding = make_finding()
    assert finding.ref_string == "finding:finding-1"
    assert finding.ref.label == finding.title
    assert finding.score == 9.3
    assert finding.severity.value == "critical"
    assert finding.is_open is True
    assert finding.version == 1
    assert finding.remediation_progress == 0.0
    assert finding.verified_proof_count == 0
    assert finding.latest_retest is None
    assert finding.as_dict()["mappings"]["cwes"] == ["CWE-89"]


def test_finding_validation_rejects_bad_inputs() -> None:
    """Construction validates entity kind, title, version, and vector."""
    with pytest.raises(ValueError):
        Finding(entity_id=EntityRef.of("note", "n1").entity_id, title="Bad")
    with pytest.raises(ValueError):
        make_finding(title="  ")
    with pytest.raises(ValueError):
        make_finding(version=0)
    with pytest.raises(ValueError):
        make_finding(vector="CVSS:4.0/AV:N")


def test_parse_finding_ref_and_id_helpers() -> None:
    """Finding identifiers are parsed strictly."""
    assert finding_id("abc").kind is EntityKind.FINDING
    assert str(parse_finding_ref("finding:abc")) == "finding:abc"
    with pytest.raises(ValueError):
        parse_finding_ref("evidence:abc")
    with pytest.raises(ValueError):
        parse_finding_ref("no-colon")


def test_finding_evolve_is_immutable_and_versioned() -> None:
    """Each evolve call produces a new snapshot with an incremented version."""
    original = make_finding()
    changed = original.evolve(title="Renamed finding", updated_at=200.0)
    assert changed is not original
    assert original.title == "SQL injection in login form"
    assert changed.title == "Renamed finding"
    assert changed.version == 2
    assert changed.updated_at == 200.0
    with pytest.raises(ValueError):
        original.evolve(unknown_field=1)


def test_severity_override_changes_band_without_touching_vector() -> None:
    """A manual override changes the displayed severity only."""
    finding = make_finding(metadata={"severity_override": "medium"})
    assert finding.severity.value == "medium"
    assert finding.score == 9.3
    assert finding.vector == VECTOR


def test_mappings_validation_and_merge() -> None:
    """Mappings validate CWE/CVE syntax and union without duplicates."""
    first = FindingMappings(cwes=("cwe-89",), cves=("cve-2024-0001",), owasp=("A03:2021",))
    second = FindingMappings(cwes=("CWE-89", "CWE-79"), cves=("CVE-2024-0002",))
    merged = first.merge(second)
    assert merged.cwes == ("CWE-89", "CWE-79")
    assert len(merged.cves) == 2
    assert merged.primary_cwe == "CWE-89"
    with pytest.raises(ValueError):
        FindingMappings(cwes=("CWE-abc",))
    with pytest.raises(ValueError):
        FindingMappings(cves=("CVE-1",))


def test_cwe_mapping_requires_identifier_and_name() -> None:
    """Catalog entries validate their required fields."""
    entry = CweMapping(cwe_id="cwe-89", name="SQL Injection", category="Injection")
    assert entry.cwe_id == "CWE-89"
    assert entry.as_dict()["category"] == "Injection"
    with pytest.raises(ValueError):
        CweMapping(cwe_id="invalid", name="SQL Injection", category="Injection")
    with pytest.raises(ValueError):
        CweMapping(cwe_id="CWE-89", name=" ", category="Injection")


def test_proof_block_hash_verification() -> None:
    """Proof blocks detect excerpt tampering and reject invalid references."""
    ref = EntityRef.of("evidence", "log-1", "Server log")
    block = make_proof("p1", ref, excerpt="ERROR: unauthorized", captured_at=5.0)
    assert block.verified is True
    assert block.content_hash == hash_excerpt("ERROR: unauthorized")
    assert block.target == "evidence:log-1"
    from dataclasses import replace

    changed = replace(block, excerpt="ERROR: authorized")
    assert changed.verified is False
    with pytest.raises(ValueError):
        make_proof("p2", EntityRef.of("finding", "f2"), excerpt="bad")
    with pytest.raises(ValueError):
        ProofRole.parse("attacker")


def test_task_creation_and_status_transitions() -> None:
    """Remediation tasks validate ids and record completion metadata."""
    task = new_task("fix-1", "Parameterize query", detail="Use bound parameters", owner="dev")
    assert task.status is TaskStatus.TODO
    assert task.status.is_settled is False
    done = task.with_status(TaskStatus.DONE, timestamp=42.0, proof_ref="evidence:pr-1")
    assert done.status.is_settled is True
    assert done.completed_at == 42.0
    assert done.proof_refs == ("evidence:pr-1",)
    assert TaskStatus.parse("in_progress") is TaskStatus.IN_PROGRESS
    with pytest.raises(ValueError):
        new_task("bad id!", "Invalid")
    with pytest.raises(ValueError):
        TaskStatus.parse("unknown")


def test_remediation_plan_progress_and_ordering() -> None:
    """Plan reports progress and surfaces the next unfinished task."""
    first = new_task("a", "Patch dependency")
    second = new_task("b", "Add regression test")
    tasks = add_task((first,), second)
    plan = plan_for(tasks, owner="team", target_date="2026-12-01")
    assert plan.total == 2
    assert plan.done == 0
    assert plan.percent == 0
    assert plan.complete is False
    assert plan.next_task() is not None
    assert plan.next_task().task_id == "a"
    tasks = update_task(tasks, "a", status=TaskStatus.DONE, timestamp=7.0)
    plan = plan_for(tasks)
    assert plan.percent == 50
    assert plan.next_task() is not None
    assert plan.next_task().task_id == "b"
    tasks = update_task(tasks, "b", status=TaskStatus.SKIPPED, timestamp=8.0)
    plan = plan_for(tasks)
    assert plan.complete is True
    assert plan.next_task() is None
    assert plan.skipped == 1
    assert plan.as_dict()["complete"] is True


def test_remediation_error_paths() -> None:
    """Checklist helpers reject duplicate ids and unknown tasks."""
    task = new_task("a", "Do the thing")
    with pytest.raises(RemediationError):
        add_task((task,), task)
    with pytest.raises(RemediationError):
        update_task((task,), "missing", status=TaskStatus.DONE, timestamp=1.0)
    assert checklist_issues(()) == ("checklist is empty",)
    assert checklist_issues((task,)) == ()


def test_task_from_lines_parses_pasted_checklists() -> None:
    """Pasted remediation guidance becomes an ordered checklist."""
    tasks = task_from_lines(
        "1. Rotate the exposed token\n- Add WAF rule\n\n* Log the attempt\n",
        owner="analyst",
    )
    assert len(tasks) == 3
    assert tasks[0].title == "Rotate the exposed token"
    assert tasks[1].title == "Add WAF rule"
    assert all(task.owner == "analyst" for task in tasks)
    assert task_from_lines("") == ()


def test_retest_verdict_parsing_and_proof_roles() -> None:
    """Enum parsers are case-insensitive and stable."""
    assert RetestVerdict.parse(" PASS ") is RetestVerdict.PASS
    assert ProofRole.parse("Contradicting") is ProofRole.CONTRADICTING
    assert FindingState.parse("confirmed") is FindingState.CONFIRMED
    with pytest.raises(ValueError):
        RetestVerdict.parse("maybe")
