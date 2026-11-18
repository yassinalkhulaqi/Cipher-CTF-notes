from __future__ import annotations

from typing import Any

import pytest

from redscribe.v2.engagements.duplicates import (
    FIELD_WEIGHTS,
    STOP_TOKENS,
    DuplicateMatch,
    best_duplicate,
    canonical_candidate,
    cluster_duplicates,
    containment,
    duplicate_reasons,
    duplicate_score,
    duplicate_summary,
    find_duplicates,
    finding_tokens,
    fingerprint,
    from_dicts,
    jaccard,
    normalize_title,
    reassign_duplicates,
)
from redscribe.v2.engagements.models import Finding, FindingStatus, Severity


def _copy(finding: Any, **overrides: Any) -> Any:
    payload = finding.as_dict()
    payload.update(overrides)
    return Finding.from_dict(payload)


def test_field_weights_cover_all_weighted_fields() -> None:
    assert set(FIELD_WEIGHTS) == {"title", "target", "summary", "evidence"}
    assert sum(FIELD_WEIGHTS.values()) == pytest.approx(1.0)
    assert "admin" in STOP_TOKENS


def test_normalize_title_sorts_meaningful_tokens(finding_factory: Any) -> None:
    first = normalize_title("There is SQL injection in the login form")
    second = normalize_title("login form injection SQL there")
    assert first == second
    assert "sql" in first.split()
    assert "the" not in first.split()


def test_finding_tokens_extracts_weighted_sections(finding_factory: Any) -> None:
    finding = finding_factory(
        title="SQL injection in login",
        summary="Unauthenticated SQL injection in login",
        reproduction_steps="Submit a quoted payload",
        impact="Data can be read",
    )
    tokens = finding_tokens(finding)
    assert set(tokens) == set(FIELD_WEIGHTS)
    assert "sql" in tokens["title"]
    assert "submit" in tokens["target"]
    assert "data" in tokens["evidence"]


def test_fingerprint_is_stable_for_cosmetic_edits(finding_factory: Any) -> None:
    first = finding_factory(title="SQL injection in login form")
    second = _copy(
        first,
        title="Login form SQL injection",
        summary="cosmetic wording change",
        id=2,
    )
    assert fingerprint(first) == fingerprint(second)
    assert len(fingerprint(first)) == 16


def test_fingerprint_changes_with_target_or_cwe(finding_factory: Any) -> None:
    first = finding_factory()
    assert fingerprint(first) != fingerprint(_copy(first, id=2, cwe="CWE-20"))
    assert fingerprint(first) != fingerprint(
        _copy(first, id=2, reproduction_steps="different steps")
    )


def test_jaccard_and_containment_edge_cases() -> None:
    assert jaccard([], []) == 1.0
    assert jaccard(["a"], []) == 0.0
    assert jaccard(["a", "b"], ["b", "c"]) == pytest.approx(1 / 3)
    assert containment(["a"], []) == 0.0
    assert containment(["a", "b"], ["a", "b", "c"]) == 1.0
    assert containment(["a", "b", "c"], ["a", "b"]) == 1.0
    assert containment(["a", "b"], ["c", "d"]) == 0.0


def test_duplicate_score_is_high_for_identical_findings(finding_factory: Any) -> None:
    first = finding_factory()
    second = _copy(first, id=2)
    assert duplicate_score(first, second) > 0.9


def test_duplicate_score_drops_when_fields_differ(finding_factory: Any) -> None:
    first = finding_factory()
    similar = duplicate_score(first, _copy(first, id=2))
    different = duplicate_score(
        first,
        _copy(
            first,
            id=3,
            title="Broken access control in billing",
            summary="Users can read other accounts",
            cwe="CWE-639",
            target_id=9,
            severity=Severity.LOW,
            reproduction_steps="Open another account identifier",
        ),
    )
    assert different < similar
    assert 0.0 <= different <= 1.0


def test_duplicate_score_bonuses_and_penalties(finding_factory: Any) -> None:
    first = finding_factory(
        cwe="CWE-89",
        cves=["CVE-2024-0001"],
        target_id=1,
        title="Alpha beta",
        summary="Gamma delta",
        reproduction_steps="epsilon zeta",
        impact="eta theta",
    )
    overrides = {
        "id": 2,
        "title": "Alpha beta different",
        "summary": "Other content",
        "reproduction_steps": "new steps",
        "impact": "fresh impact",
        "cwe": "",
        "cves": [],
        "target_id": 2,
    }
    base = duplicate_score(first, _copy(first, **overrides))
    with_cwe = duplicate_score(first, _copy(first, **{**overrides, "cwe": "CWE-89"}))
    with_cve = duplicate_score(first, _copy(first, **{**overrides, "cves": ["CVE-2024-0001"]}))
    with_target = duplicate_score(first, _copy(first, **{**overrides, "target_id": 1}))
    with_severity_change = duplicate_score(
        first, _copy(first, **{**overrides, "severity": Severity.LOW})
    )
    assert 0.0 < base < 1.0
    assert with_cwe > base
    assert with_cve > base
    assert with_target > base
    assert with_severity_change < base


def test_duplicate_reasons_are_explanatory(finding_factory: Any) -> None:
    first = finding_factory()
    reasons = duplicate_reasons(first, _copy(first, id=2))
    assert "same normalized title" in reasons
    assert "same CWE" in reasons
    assert "shared CVE" in reasons
    assert "same target" in reasons
    assert "similar summary" in reasons


def test_duplicate_reasons_fall_back_to_token_similarity(finding_factory: Any) -> None:
    first = finding_factory()
    second = _copy(
        first,
        id=2,
        title="Entirely different subject",
        summary="Nothing overlaps here",
        cwe="",
        cves=[],
        target_id=0,
    )
    assert duplicate_reasons(first, second) == ("token similarity",)


def test_duplicate_match_as_dict(finding_factory: Any) -> None:
    first = finding_factory()
    match = DuplicateMatch(
        source_id=first.id,
        candidate_id=2,
        score=0.87654,
        reasons=("same title",),
        fingerprint="abcdef",
    )
    assert match.as_dict() == {
        "source_id": 1,
        "candidate_id": 2,
        "score": 0.8765,
        "reasons": ["same title"],
        "fingerprint": "abcdef",
    }


def test_find_duplicates_ranks_by_score_then_id(finding_factory: Any) -> None:
    source = finding_factory()
    exact = _copy(source, id=2)
    near = _copy(source, id=3, severity=Severity.HIGH)
    matches = find_duplicates(source, [near, exact])
    assert [match.candidate_id for match in matches] == [2, 3]
    assert matches[0].score >= matches[1].score
    assert matches[0].fingerprint == fingerprint(source)


def test_find_duplicates_filters_source_other_engagements_and_statuses(
    finding_factory: Any,
) -> None:
    source = finding_factory(id=10)
    candidates = [
        source,
        _copy(source, id=11),
        _copy(source, id=12, engagement_id=2),
        _copy(source, id=13, status=FindingStatus.DUPLICATE),
        _copy(source, id=14, status=FindingStatus.CLOSED),
    ]
    matches = find_duplicates(source, candidates)
    assert [match.candidate_id for match in matches] == [11]


def test_find_duplicates_respects_threshold(finding_factory: Any) -> None:
    source = finding_factory()
    candidate = _copy(
        source,
        id=2,
        title="Different finding title",
        summary="Different finding summary",
        cwe="",
        cves=[],
        target_id=0,
        severity=Severity.LOW,
    )
    assert find_duplicates(source, [candidate], threshold=0.01)
    assert find_duplicates(source, [candidate], threshold=0.99) == []


def test_best_duplicate_returns_strongest_match(finding_factory: Any) -> None:
    source = finding_factory()
    match = best_duplicate(source, [_copy(source, id=2)])
    assert match is not None
    assert match.candidate_id == 2
    assert best_duplicate(source, [], threshold=0.99) is None


def test_cluster_duplicates_groups_similar_findings(finding_factory: Any) -> None:
    first = finding_factory(id=1)
    second = _copy(first, id=2)
    third = _copy(first, id=3)
    unrelated = _copy(
        first,
        id=4,
        title="Password stored in plain text",
        summary="Database column stores cleartext passwords",
        cwe="CWE-312",
        cves=[],
        target_id=77,
        reproduction_steps="Inspect database schema",
    )
    clusters = cluster_duplicates([third, unrelated, second, first])
    assert [[item.id for item in cluster] for cluster in clusters] == [[1, 2, 3], [4]]


def test_cluster_duplicates_respects_engagement_boundaries(finding_factory: Any) -> None:
    first = finding_factory(id=1)
    second = _copy(first, id=2, engagement_id=2)
    clusters = cluster_duplicates([first, second])
    assert [[item.id for item in cluster] for cluster in clusters] == [[1], [2]]


def test_duplicate_summary_reports_groups(finding_factory: Any) -> None:
    first = finding_factory(id=1)
    duplicate = _copy(first, id=2)
    unique = _copy(
        first,
        id=3,
        title="Password stored in plain text",
        summary="Database column stores cleartext passwords",
        cwe="CWE-312",
        cves=[],
        target_id=99,
        reproduction_steps="Inspect database schema",
        impact="Passwords are exposed",
        severity=Severity.LOW,
    )
    summary = duplicate_summary([first, duplicate, unique])
    assert summary["total"] == 3
    assert summary["clusters"] == 2
    assert summary["duplicate_groups"] == 1
    assert summary["duplicate_findings"] == 1
    assert summary["groups"][0]["ids"] == [1, 2]
    assert summary["groups"][0]["severity"] == "high"


def test_canonical_candidate_prefers_complete_finding(finding_factory: Any) -> None:
    draft = finding_factory(
        id=1,
        status=FindingStatus.DRAFT,
        reproduction_steps="",
        impact="",
        references=[],
    )
    verified = _copy(
        draft,
        id=2,
        status=FindingStatus.VERIFIED,
        reproduction_steps="detailed steps",
        impact="detailed impact",
        references=["https://example.test"],
    )
    assert canonical_candidate([draft, verified]).id == 2


def test_reassign_duplicates_guards_against_self_links() -> None:
    assert reassign_duplicates([1, 2, 3], canonical_id=2, duplicate_ids=[1, 2, 3]) == {1: 2, 3: 2}
    assert reassign_duplicates([1], canonical_id=1, duplicate_ids=[1]) == {}


def test_from_dicts_converts_payloads(finding_factory: Any) -> None:
    first = finding_factory()
    second = _copy(first, id=2)
    restored = from_dicts([first.as_dict(), second.as_dict()])
    assert [item.id for item in restored] == [1, 2]
    assert all(item.title == first.title for item in restored)
