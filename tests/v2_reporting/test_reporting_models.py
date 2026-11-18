from __future__ import annotations

import pytest

from redscribe.v2.reporting.identifiers import (
    canonical_json,
    citation_label,
    digest,
    digest_text,
    is_identifier,
    short_hash,
    slugify,
    unique_identifier,
)
from redscribe.v2.reporting.models import (
    EVIDENCE_KINDS,
    FINDING_STATUSES,
    REPORT_FORMATS,
    SEVERITY_ORDER,
    EvidenceRef,
    Finding,
    InclusionRule,
    RedactionRule,
    ReportConfig,
    ReportSection,
    Severity,
    SeverityCounts,
    ValidationIssue,
)


def make_evidence(identifier: str = "ev-1", **changes: object) -> EvidenceRef:
    values: dict[str, object] = {
        "identifier": identifier,
        "title": "Console output",
        "content": "$ whoami\nroot",
        "kind": "command",
        "source_path": "labs / target",
        "locator": "line 4",
    }
    values.update(changes)
    return EvidenceRef(**values)


def make_finding(identifier: str = "finding-1", **changes: object) -> Finding:
    values: dict[str, object] = {
        "identifier": identifier,
        "title": "Weak credentials",
        "severity": "high",
        "status": "open",
        "summary": "Default credentials were accepted.",
        "evidence": (make_evidence(),),
        "confidence": 0.8,
    }
    values.update(changes)
    return Finding(**values)


def make_section(identifier: str = "section-1", **changes: object) -> ReportSection:
    values: dict[str, object] = {
        "identifier": identifier,
        "title": "Findings",
        "kind": "findings",
    }
    values.update(changes)
    return ReportSection(**values)


def test_canonical_json_is_stable_across_key_order() -> None:
    left = {"b": 2, "a": [1, {"z": True, "y": None}]}
    right = {"a": [1, {"y": None, "z": True}], "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert canonical_json(left) == '{"a":[1,{"y":null,"z":true}],"b":2}'


def test_digest_helpers_are_deterministic() -> None:
    assert digest({"a": 1}) == digest({"a": 1})
    assert digest({"a": 1}) != digest({"a": 2})
    assert digest_text("report") == digest_text("report")
    assert len(digest_text("report")) == 64
    assert short_hash("report", length=10) == digest_text("report")[:10]


def test_short_hash_rejects_invalid_lengths() -> None:
    with pytest.raises(ValueError):
        short_hash("report", length=3)
    with pytest.raises(ValueError):
        short_hash("report", length=65)


def test_slugify_normalizes_unicode_and_punctuation() -> None:
    assert slugify("  Critical Findings / Résumé  ") == "critical-findings-resume"
    assert slugify("!!!", fallback="fallback") == "fallback"
    assert slugify("a" * 100, max_length=10) == "aaaaaaaaaa"


def test_identifier_helpers() -> None:
    assert is_identifier("finding-01.detail")
    assert not is_identifier("Finding 01")
    assert not is_identifier("-finding")
    assert unique_identifier(" finding ", {"finding"}) == "finding-2"
    assert unique_identifier(" finding ", {"finding", "finding-2"}) == "finding-3"
    assert citation_label("ev", "§ 4", "note-2") == "ev-4-note-2"


def test_severity_parse_and_aliases() -> None:
    assert Severity.parse("HIGH") is Severity.HIGH
    assert Severity.parse(Severity.LOW) is Severity.LOW
    assert Severity.parse("severe") is Severity.CRITICAL
    assert Severity.parse("informational") is Severity.INFO
    assert Severity.parse("minor").value == "low"
    assert Severity.parse("major").rank == 3
    assert Severity.CRITICAL.label == "Critical"
    assert Severity.INFO.as_dict() == {"value": "info", "rank": 0, "label": "Informational"}


def test_severity_parse_rejects_unknown_values() -> None:
    with pytest.raises(ValueError):
        Severity.parse("catastrophic")
    with pytest.raises(ValueError):
        Severity.parse("")


def test_evidence_citation_prefers_locator_then_path() -> None:
    item = make_evidence()
    assert item.citation == "Console output (line 4)"
    assert make_evidence(locator="").citation == "Console output — labs / target"
    assert make_evidence(locator="", source_path="").citation == "Console output"


def test_evidence_validates_identifier_and_kind() -> None:
    with pytest.raises(ValueError):
        make_evidence("   ")
    with pytest.raises(ValueError):
        make_evidence("ev", kind="unknown")
    assert EVIDENCE_KINDS == ("note", "command", "artifact", "observation", "reference")


def test_evidence_as_dict_is_json_ready() -> None:
    payload = make_evidence().as_dict()
    assert payload["identifier"] == "ev-1"
    assert payload["kind"] == "command"
    assert payload["source_id"] is None
    assert canonical_json(payload) == canonical_json(make_evidence().as_dict())


def test_finding_validation() -> None:
    finding = make_finding()
    assert finding.evidence_count == 1
    assert finding.severity_level is Severity.HIGH
    assert finding.is_open is True
    assert finding.with_evidence(()).evidence_count == 0
    with pytest.raises(ValueError):
        make_finding("   ")
    with pytest.raises(ValueError):
        make_finding("f", title="")
    with pytest.raises(ValueError):
        make_finding("f", severity="unknown")
    with pytest.raises(ValueError):
        make_finding("f", status="later")
    with pytest.raises(ValueError):
        make_finding("f", confidence=1.4)


def test_finding_as_dict_contains_all_visible_fields() -> None:
    payload = make_finding().as_dict()
    expected = {
        "identifier": "finding-1",
        "severity": "high",
        "status": "open",
        "confidence": 0.8,
    }
    for key, value in expected.items():
        assert payload[key] == value
    assert payload["evidence"][0]["identifier"] == "ev-1"
    assert payload["references"] == []


def test_report_section_walk_and_finding_collection() -> None:
    child = make_section("child", title="Child", findings=(make_finding("f-2"),))
    root = make_section("root", findings=(make_finding("f-1"),), children=(child,))
    assert root.finding_count == 1
    assert root.is_container is True
    assert tuple(item.identifier for item in root.walk()) == ("root", "child")
    assert tuple(item.identifier for item in root.all_findings()) == ("f-1", "f-2")
    assert root.with_children(()).children == ()


def test_report_section_validation() -> None:
    with pytest.raises(ValueError):
        make_section("")
    with pytest.raises(ValueError):
        make_section("s", title="")
    with pytest.raises(ValueError):
        make_section("s", title="S", level=0)
    with pytest.raises(ValueError):
        make_section("s", title="S", level=7)


def test_severity_counts_operations() -> None:
    counts = SeverityCounts()
    counts = counts.increment("critical").increment("severe").increment("low")
    assert counts.as_dict() == {"info": 0, "low": 1, "medium": 0, "high": 0, "critical": 2}
    assert counts.total() == 3
    assert counts.weighted() == 9
    assert counts.highest() == "critical"
    assert SeverityCounts().highest() == "info"


def test_inclusion_rule_accepts_finding_and_note_statuses() -> None:
    finding_rule = InclusionRule("f", "include", statuses=("open", "closed"))
    note_rule = InclusionRule("n", "exclude", statuses=("blocked",))
    assert finding_rule.is_exclusion is False
    assert note_rule.is_exclusion is True
    assert note_rule.statuses == ("blocked",)
    with pytest.raises(ValueError):
        InclusionRule("bad", "include", statuses=("later",))
    with pytest.raises(ValueError):
        InclusionRule("bad", "other")


def test_redaction_rule_validation() -> None:
    rule = RedactionRule("email", r"a@b", "[REDACTED]", priority=5)
    assert rule.disabled() is False
    assert rule.as_dict()["replacement"] == "[REDACTED]"
    with pytest.raises(ValueError):
        RedactionRule("", "pattern")
    with pytest.raises(ValueError):
        RedactionRule("bad", "")
    with pytest.raises(ValueError):
        RedactionRule("bad", "pattern", scope="unknown")


def test_report_config_fingerprint_and_dict() -> None:
    config = ReportConfig(title="Engagement", print_profile="compact")
    assert config.fingerprint() == config.fingerprint()
    assert config.as_dict()["print_profile"] == "compact"
    assert config.as_dict()["statuses"] == []
    assert ReportConfig(title="A").fingerprint() != ReportConfig(title="B").fingerprint()


def test_report_config_finding_helpers() -> None:
    child = make_section("child", findings=(make_finding("f-2"),))
    root = make_section("root", findings=(make_finding("f-1"),), children=(child,))
    config = ReportConfig(
        title="Report",
        findings=(make_finding("f-3"),),
        sections=(root,),
    )
    assert config.finding_count() == 2
    assert len(config.all_findings()) == 3
    assert config.confidence_invalid() is False


def test_constants_are_stable() -> None:
    assert SEVERITY_ORDER == ("info", "low", "medium", "high", "critical")
    assert REPORT_FORMATS == ("markdown", "html", "json", "print")
    assert FINDING_STATUSES == ("open", "confirmed", "mitigated", "accepted", "closed")


def test_validation_issue_as_dict() -> None:
    issue = ValidationIssue(code="bad", message="Bad", path="title", severity="error")
    payload = issue.as_dict()
    assert payload["code"] == "bad"
    assert payload["path"] == "title"
    assert payload["severity"] == "error"
