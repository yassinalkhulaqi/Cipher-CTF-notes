"""Tests for stable finding and evidence selection rules."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.types import EntityRef
from redscribe.v3.report_designer.model import EvidenceItem, FindingItem, SelectionRule
from redscribe.v3.report_designer.selection import (
    SelectionPolicy,
    collect_evidence,
    default_policy,
    rule_matches,
    rule_summary,
    select_evidence,
    stable_sort_findings,
)


def make_finding(key: str, severity: str = "medium", status: str = "open", **kwargs) -> FindingItem:
    return FindingItem(
        ref=EntityRef.of("finding", key),
        title=key.replace("-", " ").title(),
        severity=severity,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        **kwargs,
    )


def test_rule_matches() -> None:
    finding = make_finding("sql", "high", tags=("web", "owasp"), confidence=0.8)
    assert rule_matches(SelectionRule("all", "include"), finding) is True
    assert rule_matches(SelectionRule("high", "include", severities=("high",)), finding) is True
    assert rule_matches(SelectionRule("low", "include", severities=("low",)), finding) is False
    assert rule_matches(SelectionRule("tag", "include", tags=("WEB",)), finding) is True
    assert rule_matches(SelectionRule("tag", "include", tags=("mobile",)), finding) is False
    assert rule_matches(SelectionRule("conf", "include", minimum_confidence=0.9), finding) is False
    assert rule_matches(SelectionRule("id", "include", identifier="finding:sql"), finding) is True
    assert rule_matches(SelectionRule("id", "include", identifier="wrong"), finding) is False
    assert (
        rule_matches(SelectionRule("cat", "include", categories=("injection",)), finding) is False
    )


def test_policy_decide() -> None:
    policy = SelectionPolicy(
        rules=(
            SelectionRule("drop-sensitive", "exclude", tags=("secret",)),
            SelectionRule("only-high", "include", severities=("high", "critical")),
        ),
        minimum_severity="low",
        statuses=("open", "confirmed"),
    )
    assert policy.decide(make_finding("a", "high")) == (True, "only-high", "included by rule")
    assert policy.decide(make_finding("b", "low"))[:1] == (False,)
    assert policy.decide(make_finding("c", "high", tags=("secret",)))[1] == "drop-sensitive"
    assert policy.decide(make_finding("d", "high", status="closed"))[1] == "status-filter"
    assert policy.decide(make_finding("e", "info"))[1] == "severity-threshold"


def test_policy_filters_tags_and_evidence() -> None:
    finding = make_finding("a", tags=("web",))
    policy = SelectionPolicy(tags=("mobile",))
    assert policy.decide(finding)[1] == "tag-filter"
    assert SelectionPolicy(require_evidence=True).decide(finding)[1] == "evidence-filter"
    with_evidence = finding.with_evidence(
        (
            EvidenceItem(
                ref=EntityRef.of("evidence", "e1"),
                title="Evidence",
            ),
        )
    )
    assert SelectionPolicy(require_evidence=True).decide(with_evidence)[0] is True


def test_select_records_every_decision() -> None:
    findings = (
        make_finding("low", "low"),
        make_finding("high", "high"),
        make_finding("secret", "critical", tags=("secret",)),
    )
    policy = SelectionPolicy(
        rules=(
            SelectionRule("drop-sensitive", "exclude", tags=("secret",)),
            SelectionRule("all", "include"),
        )
    )
    result = policy.select(findings)
    assert result.total == 3
    assert [item.key for item in result.included] == ["high", "low"]
    assert [item.key for item in result.excluded] == ["secret"]
    assert len(result.decisions) == 3
    assert {item.key for item in result.decisions if item.included} == {"high", "low"}
    assert all(decision.rule for decision in result.decisions)
    assert result.inclusion_rate == 0.6667
    assert result.digest() == result.digest()
    assert "included" in result.as_dict()


def test_stable_sort_findings() -> None:
    findings = (
        make_finding("z-low", "low"),
        make_finding("b-high", "high"),
        make_finding("a-high", "high"),
    )
    assert [item.key for item in stable_sort_findings(findings)] == [
        "a-high",
        "b-high",
        "z-low",
    ]


def test_select_evidence() -> None:
    sensitive = EvidenceItem(ref=EntityRef.of("evidence", "s1"), title="sensitive", sensitive=True)
    plain = EvidenceItem(ref=EntityRef.of("evidence", "p1"), title="plain")
    other = EvidenceItem(ref=EntityRef.of("evidence", "p2"), title="another")
    evidence = (sensitive, other, plain)
    assert [item.title for item in select_evidence(evidence)] == ["another", "plain"]
    assert [item.title for item in select_evidence(evidence, include_sensitive=True)] == [
        "another",
        "plain",
        "sensitive",
    ]
    assert len(select_evidence(evidence, limit=1)) == 1
    with pytest.raises(ValueError):
        select_evidence(evidence, limit=-1)


def test_collect_evidence_deduplicates() -> None:
    evidence = EvidenceItem(ref=EntityRef.of("evidence", "e1"), title="E")
    first = make_finding("a").with_evidence((evidence,))
    second = make_finding("b").with_evidence((evidence,))
    assert collect_evidence((first, second)) == (evidence,)


def test_default_policy_and_summaries() -> None:
    policy = default_policy()
    assert policy.decide(make_finding("secret", tags=("secret",)))[1] == "drop-sensitive"
    assert policy.decide(make_finding("ok"))[0] is True
    summary = rule_summary(policy)
    assert summary["includes"] == 1
    assert summary["excludes"] == 2
    assert policy.digest() == policy.digest()
    assert SelectionPolicy().decide(make_finding("x")) == (True, "default", "no rule matched")
