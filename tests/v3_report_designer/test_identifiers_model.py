"""Tests for deterministic helpers and the layout document model."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.types import EntityRef
from redscribe.v3.report_designer.identifiers import (
    anchor_for,
    canonical_json,
    digest,
    digest_text,
    is_identifier,
    page_anchor,
    page_label,
    short_hash,
    slugify,
    stable_id,
    unique_slug,
)
from redscribe.v3.report_designer.model import (
    EvidenceItem,
    FindingItem,
    LayoutDocument,
    LayoutSection,
    RedactionRule,
    SectionKind,
    SelectionRule,
    Severity,
    SeverityCounts,
    count_severities,
    empty_counts,
)


def test_canonical_json_is_stable_and_sorted() -> None:
    assert canonical_json({"b": 1, "a": [2, 3]}) == '{"a":[2,3],"b":1}'
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})
    assert digest({"a": 1}) == digest({"a": 1})
    assert digest({"a": 1}) != digest({"a": 2})
    assert digest_text("hello") == digest_text("hello")
    assert len(short_hash("hello", length=8)) == 8
    with pytest.raises(ValueError):
        short_hash("hello", length=2)


def test_slugify_and_identifiers() -> None:
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("###", fallback="x") == "x"
    assert slugify("A" * 100, max_length=10) == "a" * 10
    assert is_identifier("abc-1")
    assert not is_identifier("Bad Name")
    assert unique_slug("overview", {"overview"}) == "overview-2"
    assert unique_slug("overview", {"overview", "overview-2"}) == "overview-3"
    assert anchor_for("Overview Section") == "sec-overview-section"
    assert page_anchor(3) == "page-3"
    assert page_label(2, 5) == "Page 2 of 5"
    with pytest.raises(ValueError):
        page_anchor(0)
    with pytest.raises(ValueError):
        page_label(0, 5)
    assert stable_id("finding", "Login", 2) == stable_id("finding", "Login", 2)
    assert stable_id("finding", "Login", 2) != stable_id("finding", "Login", 3)


def test_severity_parse_and_ordering() -> None:
    assert Severity.parse("HIGH") is Severity.HIGH
    assert Severity.parse("informational") is Severity.INFO
    assert Severity.parse("major") is Severity.HIGH
    assert Severity.parse(Severity.LOW) is Severity.LOW
    assert Severity.CRITICAL.rank > Severity.HIGH.rank
    assert Severity.INFO.label == "Informational"
    assert Severity.parse("high").as_dict()["rank"] == 3
    with pytest.raises(ValueError):
        Severity.parse("catastrophic")


def test_evidence_and_finding_validation(evidence: EvidenceItem, finding: FindingItem) -> None:
    assert evidence.citation == "Auth log excerpt (line 42)"
    assert evidence.as_dict()["kind"] == "command"
    assert finding.evidence_count == 1
    assert finding.is_open is True
    assert finding.severity_level is Severity.HIGH
    assert finding.key == "sql-injection-in-login"
    with pytest.raises(ValueError):
        EvidenceItem(ref=EntityRef.of("finding", "x"), title="Bad ref")
    with pytest.raises(ValueError):
        FindingItem(ref=EntityRef.of("finding", "x"), title="Bad", confidence=2.0)


def test_severity_counts() -> None:
    counts = empty_counts()
    for name in ("info", "high", "high", "critical"):
        counts = counts.increment(name)
    assert counts.total() == 4
    assert counts.high == 2
    assert counts.highest() == "critical"
    assert counts.weighted() > 0
    assert count_severities(()) == SeverityCounts()
    assert empty_counts().highest() == "info"


def test_section_tree_and_aggregation(finding: FindingItem) -> None:
    child = LayoutSection(key="child", title="Child", level=2, findings=(finding,))
    root = LayoutSection(key="root", title="Root", children=(child,))
    assert len(root.walk()) == 2
    assert root.all_findings() == (finding,)
    assert root.is_container is True
    assert root.anchor == "sec-root"
    hidden = LayoutSection(key="hidden", title="Hidden", visible=False)
    document = LayoutDocument(key="doc", title="Doc", sections=(root, hidden))
    assert len(document.all_sections) == 3
    assert len(document.visible_sections) == 2
    assert document.find_section("child") is child
    assert document.find_section("missing") is None
    assert document.finding_count == 1
    assert document.severity.high == 1
    assert document.fingerprint() == document.fingerprint()


def test_model_validation() -> None:
    with pytest.raises(ValueError):
        LayoutSection(key="", title="Bad")
    with pytest.raises(ValueError):
        LayoutSection(key="x", title="Bad", level=9)
    with pytest.raises(ValueError):
        LayoutDocument(key="", title="Bad")
    with pytest.raises(ValueError):
        SelectionRule(name="bad", action="maybe")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RedactionRule(name="bad", pattern="", scope="all")
    with pytest.raises(ValueError):
        RedactionRule(name="bad", pattern="x", scope="invalid")  # type: ignore[arg-type]


def test_special_kinds_and_section_helpers(section: LayoutSection, finding: FindingItem) -> None:
    assert SectionKind.parse("cover") is SectionKind.COVER
    assert SectionKind.COVER.is_special is True
    assert SectionKind.TEXT.is_special is False
    with pytest.raises(ValueError):
        SectionKind.parse("nope")
    assert section.with_children(()).children == ()
    assert section.with_findings((finding,)).finding_count == 1
    assert section.as_dict()["anchor"] == "sec-overview"
