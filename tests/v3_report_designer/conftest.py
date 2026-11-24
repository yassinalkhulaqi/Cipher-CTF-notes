"""Shared fixtures for the report designer test suite."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.types import EntityRef
from redscribe.v3.report_designer.engine import DesignSpec, ReportDesignerEngine, default_engine
from redscribe.v3.report_designer.model import (
    EvidenceItem,
    FindingItem,
    LayoutSection,
    RedactionRule,
    SelectionRule,
)
from redscribe.v3.report_designer.redaction import builtin_redactions


@pytest.fixture
def evidence() -> EvidenceItem:
    return EvidenceItem(
        ref=EntityRef.of("evidence", "ev-1", "Auth log"),
        title="Auth log excerpt",
        content="admin@example.com from 10.0.0.5 flag{secret1234}",
        excerpt="Failed login for admin@example.com",
        kind="command",
        locator="line 42",
    )


@pytest.fixture
def finding(evidence: EvidenceItem) -> FindingItem:
    return FindingItem(
        ref=EntityRef.of("finding", "f-1", "SQL injection"),
        title="SQL injection in login",
        summary="Unsanitized input reaches the query at admin@example.com.",
        severity="high",
        status="confirmed",
        category="injection",
        tags=("web", "owasp"),
        confidence=0.9,
        impact="Complete database compromise",
        recommendation="Use parameterized queries.",
        evidence=(evidence,),
    )


@pytest.fixture
def low_finding() -> FindingItem:
    return FindingItem(
        ref=EntityRef.of("finding", "f-2", "Verbose headers"),
        title="Verbose server headers",
        severity="low",
        status="open",
        tags=("info",),
    )


@pytest.fixture
def sensitive_finding() -> FindingItem:
    return FindingItem(
        ref=EntityRef.of("finding", "f-3", "Leaked credential"),
        title="Leaked credential",
        severity="critical",
        status="open",
        tags=("secret", "credential"),
        summary="password: hunter2secret from 192.168.1.10",
    )


@pytest.fixture
def section(finding: FindingItem) -> LayoutSection:
    return LayoutSection(
        key="overview",
        title="Overview",
        kind="text",
        order=0,
        body="Assessed acme.internal. Contact security@acme.com.",
        summary="Engagement summary",
        children=(
            LayoutSection(
                key="scope",
                title="Scope",
                order=1,
                level=2,
                body="External web application only.",
            ),
        ),
    )


@pytest.fixture
def rules() -> tuple[SelectionRule, ...]:
    return (
        SelectionRule("drop-sensitive", "exclude", tags=("secret",)),
        SelectionRule("reportable", "include"),
    )


@pytest.fixture
def redactions() -> tuple[RedactionRule, ...]:
    return builtin_redactions()


@pytest.fixture
def spec(
    section: LayoutSection,
    finding: FindingItem,
    low_finding: FindingItem,
    sensitive_finding: FindingItem,
    rules: tuple[SelectionRule, ...],
    redactions: tuple[RedactionRule, ...],
) -> DesignSpec:
    return DesignSpec(
        key="demo-report",
        title="Acme Security Assessment",
        subtitle="External Assessment",
        client="Acme Corp",
        author="RedScribe",
        classification="confidential",
        generated_at="2026-01-01T00:00:00Z",
        theme="client",
        sections=(section,),
        findings=(finding, low_finding, sensitive_finding),
        rules=rules,
        redactions=redactions,
    )


@pytest.fixture
def engine() -> ReportDesignerEngine:
    return default_engine()
