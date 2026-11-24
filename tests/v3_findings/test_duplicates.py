"""Tests for V3 duplicate suggestions and false-positive controls."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.types import EntityRef
from redscribe.v3.findings.cvss_v4 import SeverityBand
from redscribe.v3.findings.duplicates import (
    DEFAULT_THRESHOLD,
    DuplicateSuggestion,
    duplicate_clusters,
    duplicate_summary,
    fingerprint_of,
    suggest_duplicates,
)
from redscribe.v3.findings.models import (
    Finding,
    FindingMappings,
    FindingState,
    ProofBlock,
    finding_id,
)

TARGET_A = EntityRef.of("target", "app-a", "App A")
TARGET_B = EntityRef.of("target", "app-b", "App B")


def make_finding(
    value: str,
    *,
    title: str = "SQL injection in login form",
    summary: str = "Login form passes unsanitized input to the database query",
    cwes: tuple[str, ...] = ("CWE-89",),
    target: EntityRef | None = TARGET_A,
    state: FindingState = FindingState.CONFIRMED,
    severity: SeverityBand = SeverityBand.CRITICAL,
    excerpts: tuple[str, ...] = (),
    proof_blocks: tuple[ProofBlock, ...] = (),
) -> Finding:
    """Build a finding with duplicate-relevant fields."""
    blocks = proof_blocks or tuple(
        ProofBlock(
            block_id=f"{value}-p{index}",
            ref=EntityRef.of("evidence", f"e{index}"),
            excerpt=text,
        )
        for index, text in enumerate(excerpts)
    )
    return Finding(
        entity_id=finding_id(value),
        title=title,
        summary=summary,
        state=state,
        mappings=FindingMappings(cwes=cwes),
        target_ref=target,
        metadata={"severity_override": severity.value} if severity is not SeverityBand.NONE else {},
        proof_blocks=blocks,
    )


def test_fingerprint_is_stable_and_ignores_cosmetic_title_order() -> None:
    """V2 fingerprints remain stable across word order changes."""
    first = make_finding("a")
    second = make_finding("b", title="Login form SQL injection in")
    assert fingerprint_of(first) == fingerprint_of(second)
    assert len(fingerprint_of(first)) > 8


def test_obvious_duplicate_is_suggested() -> None:
    """Near-identical findings produce a confident suggestion."""
    source = make_finding("source")
    candidate = make_finding("candidate")
    suggestions = suggest_duplicates(source, [candidate])
    assert len(suggestions) >= 1
    assert str(suggestions[0].candidate_ref) == "finding:candidate"
    assert suggestions[0].confirmed is True
    assert suggestions[0].score >= DEFAULT_THRESHOLD
    assert suggestions[0].reasons
    assert suggestions[0].as_dict()["score"] > 0


def test_different_target_without_mapping_is_filtered() -> None:
    """Cross-target matches need a stronger score or a shared mapping."""
    source = make_finding("source", cwes=())
    candidate = make_finding(
        "other-target",
        summary="Entirely unrelated condition with different observable behavior",
        cwes=(),
        target=TARGET_B,
    )
    assert suggest_duplicates(source, [candidate], threshold=0.4) == ()


def test_short_generic_titles_are_not_suggested() -> None:
    """Very short titles cannot form reliable duplicate evidence."""
    source = make_finding("source", title="SQLi", cwes=())
    candidate = make_finding("candidate", title="SQLi", cwes=())
    assert suggest_duplicates(source, [candidate], threshold=0.3) == ()


def test_closed_and_duplicate_candidates_are_excluded() -> None:
    """Closed findings and known duplicates never become suggestions."""
    source = make_finding("source")
    closed = make_finding("closed", state=FindingState.CLOSED)
    duplicate = make_finding("dupe")
    duplicate = duplicate.evolve(duplicate_of=finding_id("canonical"))
    assert suggest_duplicates(source, [closed, duplicate]) == ()


def test_divergent_cwe_is_filtered_until_score_is_high() -> None:
    """Different CWEs require stronger textual similarity."""
    source = make_finding("source")
    candidate = make_finding(
        "different-cwe",
        cwes=("CWE-79",),
        summary="An unrelated request handling defect with different impact",
    )
    assert suggest_duplicates(source, [candidate], threshold=0.4) == ()


def test_severity_gap_requires_stronger_similarity() -> None:
    """A two-band severity gap suppresses weak duplicate matches."""
    source = make_finding("source", severity=SeverityBand.CRITICAL)
    candidate = make_finding(
        "low-severity",
        severity=SeverityBand.LOW,
        summary="Different wording with a weaker observable consequence",
    )
    assert suggest_duplicates(source, [candidate], threshold=0.4) == ()


def test_duplicate_report_and_clusters() -> None:
    """Reports expose a best match; clusters group similar findings."""
    source = make_finding("source")
    candidate = make_finding("candidate")
    report = duplicate_summary(source, [candidate])
    assert report["count"] == 1
    assert report["best"] is not None
    assert report["best"]["candidate_ref"]["ref"] == "finding:candidate"
    assert report["fingerprint"] == fingerprint_of(source)

    clusters = duplicate_clusters(
        [source, candidate, make_finding("other", title="Unrelated topic")]
    )
    assert clusters
    assert any("finding:candidate" in cluster for cluster in clusters)


def test_threshold_validation() -> None:
    """Out-of-range thresholds are rejected."""
    source = make_finding("source")
    with pytest.raises(ValueError):
        suggest_duplicates(source, [], threshold=1.5)
    suggestion = DuplicateSuggestion(
        source_ref=source.ref_string,
        candidate_ref=EntityRef.of("finding", "c"),
        score=0.9,
        reasons=("same title",),
        fingerprint="abc",
        threshold=DEFAULT_THRESHOLD,
    )
    assert suggestion.confirmed is True
