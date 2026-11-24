"""Tests for proof-block link integrity and CWE mapping metadata."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.service import EntityService
from redscribe.v3.entities.types import EntityId, EntityKind, EntityRef, LinkKind
from redscribe.v3.findings.mappings import (
    cwe_catalog,
    lookup_cwe,
    mapping_report,
    search_cwe,
    validate_mappings,
)
from redscribe.v3.findings.models import (
    Finding,
    FindingMappings,
    ProofRole,
    RetestRecord,
    RetestVerdict,
    finding_id,
    hash_excerpt,
)
from redscribe.v3.findings.proof import (
    ProofError,
    add_proof_block,
    make_proof,
    proof_blocks_for,
    proof_link,
    proof_ref_from_node,
    proof_summary,
    proof_targets,
    reconcile_links,
    validate_ref,
    verify_chain,
)
from redscribe.v3.findings.remediation import new_task

VECTOR = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"


def base_finding() -> Finding:
    """Build a finding for proof tests."""
    return Finding(
        entity_id=finding_id("proof-finding"),
        title="Evidence-backed finding",
        vector=VECTOR,
    )


def test_make_proof_hashes_excerpt_and_validates_kind() -> None:
    """Proof creation hashes content and limits link targets."""
    ref = EntityRef.of("evidence", "capture-01", "Capture 01")
    block = make_proof("b1", ref, excerpt="raw packet bytes", captured_at=12.0, label="pcap")
    assert block.content_hash == hash_excerpt("raw packet bytes")
    assert block.verified is True
    assert block.label == "pcap"
    assert block.captured_at == 12.0
    validate_ref(ref)
    with pytest.raises(ProofError):
        validate_ref(EntityRef.of("target", "host-1"))
    with pytest.raises(ProofError):
        make_proof("b2", EntityRef.of("run", "r1"), excerpt="x")


def test_proof_link_uses_evidences_edge() -> None:
    """A proof block maps to a typed EVIDENCES EntityLink."""
    finding = base_finding()
    block = make_proof(
        "b1",
        EntityRef.of("evidence", "e1"),
        excerpt="proof",
        role=ProofRole.CONTRADICTING,
    )
    link = proof_link(finding, block)
    assert link.kind is LinkKind.EVIDENCES
    assert str(link.source) == finding.ref_string
    assert str(link.target) == "evidence:e1"
    assert link.label == "contradicting"
    assert link.metadata["block_id"] == "b1"


def test_proof_chain_detects_tampering_and_duplicates() -> None:
    """Integrity checks catch hash mismatches and repeated block ids."""
    from dataclasses import replace

    good = make_proof("b1", EntityRef.of("evidence", "e1"), excerpt="good excerpt")
    tampered = replace(good, excerpt="modified excerpt")
    finding = base_finding().evolve(proof_blocks=(good, tampered, good))
    issues = verify_chain(finding)
    assert {issue.code for issue in issues} >= {"duplicate_id", "hash_mismatch"}
    assert all(issue.as_dict()["block_id"] == "b1" for issue in issues)
    assert proof_summary(finding)["integrity"] is False
    assert proof_summary(finding)["verified"] == 2


def test_proof_filtering_and_deduplication() -> None:
    """Proof views filter by role and collapse repeated references."""
    evidence = EntityRef.of("evidence", "e1")
    supporting = make_proof("b1", evidence, excerpt="first")
    context = make_proof("b2", EntityRef.of("note", "n1"), excerpt="second", role=ProofRole.CONTEXT)
    duplicate_ref = make_proof("b3", evidence, excerpt="third")
    finding = base_finding()
    for block in (supporting, context, duplicate_ref):
        finding = add_proof_block(finding, block, timestamp=1.0)
    assert finding.version == 4
    assert len(proof_blocks_for(finding, ProofRole.CONTEXT)) == 1
    assert len(proof_targets(finding)) == 2
    assert proof_summary(finding)["supporting"] == 2
    with pytest.raises(ProofError):
        add_proof_block(finding, supporting, timestamp=2.0)


def test_link_reconciliation_with_entity_service() -> None:
    """Expected proof links are counted against the universal link graph."""
    entities = EntityService()
    target = entities.create(EntityKind.EVIDENCE, title="Capture", value="e1")
    finding = base_finding()
    block = make_proof("b1", EntityRef(target.entity_id, "Capture"), excerpt="bytes")
    finding = add_proof_block(finding, block, timestamp=1.0)
    entities.create(EntityKind.FINDING, title=finding.title, value="proof-finding")
    assert reconcile_links(entities.graph(), (finding,)) == (0, 1)
    entities.link(
        finding.entity_id,
        target.entity_id,
        kind=LinkKind.EVIDENCES,
        label="supporting",
    )
    assert reconcile_links(entities.graph(), (finding,)) == (1, 1)


def test_proof_ref_from_node_and_actor() -> None:
    """Proof references can be built from parsed entity ids."""
    node = EntityId.parse("section:appendix-a")
    ref = proof_ref_from_node(node, "Appendix A")
    assert ref.kind is EntityKind.SECTION
    assert ref.label == "Appendix A"


def test_cwe_catalog_lookup_and_search() -> None:
    """The built-in CWE catalog is searchable and resolves known entries."""
    catalog = cwe_catalog()
    assert len(catalog) >= 10
    resolved = lookup_cwe("cwe-89")
    assert resolved.known is True
    assert resolved.entry is not None
    assert resolved.entry.owasp == ("A03:2021",)
    assert lookup_cwe("CWE-999999").known is False
    assert any(entry.cwe_id == "CWE-89" for entry in search_cwe("injection"))
    assert all(entry.category == "Authentication" for entry in search_cwe("", category="auth"))


def test_mapping_report_collects_mitigations_and_flags_unknown() -> None:
    """Mapping reports merge mitigations and report unresolved CWEs."""
    mappings = FindingMappings(
        cwes=("CWE-89", "CWE-999999"),
        cves=("CVE-2024-0001",),
        owasp=("A03:2021",),
        mitre_attack=("T1190",),
    )
    report = mapping_report(mappings)
    assert report["known_count"] == 1
    assert report["unknown"] == ["CWE-999999"]
    assert "Use parameterized queries" in report["mitigations"]
    assert "A03:2021" in report["owasp"]
    assert validate_mappings(mappings) == ("unknown CWE: CWE-999999",)


def test_retest_proof_references_are_preserved() -> None:
    """Retest records retain their evidence references in serialized form."""
    record = RetestRecord(
        retest_id="r1",
        verdict=RetestVerdict.PASS,
        tested_by="tester",
        timestamp=1.0,
        proof_refs=("evidence:e1",),
    )
    finding = base_finding().evolve(retests=(record,))
    task = new_task("t1", "Verify fix")
    finding = finding.evolve(remediation=(task,))
    payload = finding.as_dict()
    assert payload["retests"][0]["proof_refs"] == ["evidence:e1"]
    assert payload["remediation"][0]["status"] == "todo"
