"""Redaction rules and preview helpers for exported reports."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import replace

from redscribe.v2.reporting.models import (
    EvidenceRef,
    Finding,
    RedactionResult,
    RedactionRule,
    ReportSection,
)

FLAG_PATTERN = r"\b(?:flag|ctf)\{[^}\s]{4,}\}|(?i:\b[a-z0-9_]+\{[^}\s]{4,}\})"
EMAIL_PATTERN = r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"
IPV4_PATTERN = r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
API_KEY_PATTERN = (
    r"(?i)\b(?:api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['\"]?[^\s'\"]{6,}"
)
PRIVATE_KEY_PATTERN = r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"
HOST_PATTERN = r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|local|internal|test)\b"


def builtin_redactions(*, include_hosts: bool = False) -> tuple[RedactionRule, ...]:
    """Return the default redaction rule set in priority order."""
    rules = [
        RedactionRule("private-key", PRIVATE_KEY_PATTERN, "[PRIVATE KEY]", priority=10),
        RedactionRule("api-secret", API_KEY_PATTERN, "[SECRET]", priority=20),
        RedactionRule("email", EMAIL_PATTERN, "[EMAIL]", priority=30),
        RedactionRule("flag", FLAG_PATTERN, "[FLAG]", priority=40),
        RedactionRule("ipv4", IPV4_PATTERN, "[IP]", priority=50),
    ]
    if include_hosts:
        rules.append(RedactionRule("host", HOST_PATTERN, "[HOST]", priority=60))
    return tuple(rules)


def compile_rule(rule: RedactionRule) -> re.Pattern[str]:
    """Compile a redaction rule with its declared flags."""
    flags = 0
    if "ignorecase" in rule.flags:
        flags |= re.IGNORECASE
    if "multiline" in rule.flags:
        flags |= re.MULTILINE
    if "dotall" in rule.flags:
        flags |= re.DOTALL
    if "verbose" in rule.flags:
        flags |= re.VERBOSE
    return re.compile(rule.pattern, flags)


def sorted_rules(rules: Iterable[RedactionRule]) -> list[RedactionRule]:
    """Sort enabled rules by priority and stable name."""
    enabled = [rule for rule in rules if rule.enabled]
    return sorted(enabled, key=lambda rule: (rule.priority, rule.name.casefold()))


def redact_text(text: str, rules: Sequence[RedactionRule]) -> RedactionResult:
    """Apply redaction rules to text and report what matched."""
    applied: list[str] = []
    counts: dict[str, int] = {}
    result = text
    for rule in sorted_rules(rules):
        pattern = compile_rule(rule)
        result, count = pattern.subn(rule.replacement, result)
        if count:
            applied.append(rule.name)
            counts[rule.name] = counts.get(rule.name, 0) + count
    return RedactionResult(result, tuple(applied), counts)


def preview_redaction(
    text: str,
    rules: Sequence[RedactionRule],
    *,
    context: int = 24,
    max_spans: int = 12,
) -> list[dict[str, object]]:
    """Return comment-free preview spans for the redaction preview UI."""
    if context < 0:
        raise ValueError("context must not be negative")
    if max_spans < 1:
        raise ValueError("max_spans must be at least one")
    spans: list[dict[str, object]] = []
    for rule in sorted_rules(rules):
        pattern = compile_rule(rule)
        for match in pattern.finditer(text):
            start = max(0, match.start() - context)
            end = min(len(text), match.end() + context)
            spans.append(
                {
                    "rule": rule.name,
                    "replacement": rule.replacement,
                    "before": text[start : match.start()],
                    "matched": text[match.start() : match.end()],
                    "after": text[match.end() : end],
                }
            )
            if len(spans) >= max_spans:
                return spans
    return spans


def redact_evidence(evidence: EvidenceRef, rules: Sequence[RedactionRule]) -> EvidenceRef:
    """Redact all user-visible fields of one evidence reference."""
    body_rules = [rule for rule in rules if rule.scope in ("all", "evidence")]
    title_rules = [rule for rule in rules if rule.scope in ("all", "title")]
    return replace(
        evidence,
        title=redact_text(evidence.title, title_rules).text,
        content=redact_text(evidence.content, body_rules).text,
        excerpt=redact_text(evidence.excerpt, body_rules).text,
        source_path=redact_text(evidence.source_path, body_rules).text,
        locator=redact_text(evidence.locator, body_rules).text,
    )


def redact_finding(finding: Finding, rules: Sequence[RedactionRule]) -> Finding:
    """Redact every visible part of a finding."""
    body_rules = [rule for rule in rules if rule.scope in ("all", "body")]
    title_rules = [rule for rule in rules if rule.scope in ("all", "title")]
    return replace(
        finding,
        title=redact_text(finding.title, title_rules).text,
        summary=redact_text(finding.summary, body_rules).text,
        impact=redact_text(finding.impact, body_rules).text,
        recommendation=redact_text(finding.recommendation, body_rules).text,
        affected=redact_text(finding.affected, body_rules).text,
        evidence=tuple(redact_evidence(item, rules) for item in finding.evidence),
    )


def redact_section(section: ReportSection, rules: Sequence[RedactionRule]) -> ReportSection:
    """Recursively redact a section tree."""
    body_rules = [rule for rule in rules if rule.scope in ("all", "body")]
    title_rules = [rule for rule in rules if rule.scope in ("all", "title")]
    return replace(
        section,
        title=redact_text(section.title, title_rules).text,
        body=redact_text(section.body, body_rules).text,
        summary=redact_text(section.summary, body_rules).text,
        findings=tuple(redact_finding(item, rules) for item in section.findings),
        children=tuple(redact_section(child, rules) for child in section.children),
    )


def redaction_summary(rules: Sequence[RedactionRule], text: str) -> dict[str, object]:
    """Summarize which rules would fire for a text sample."""
    result = redact_text(text, rules)
    return {
        "rule_count": len(sorted_rules(rules)),
        "applied": list(result.applied),
        "counts": dict(result.counts),
        "matches": sum(result.counts.values()),
        "redacted_length": len(result.text),
        "original_length": len(text),
    }


def rule_digest(rules: Iterable[RedactionRule]) -> str:
    """Return a stable digest of an ordered rule set."""
    from redscribe.v2.reporting.identifiers import digest

    return digest([rule.as_dict() for rule in sorted_rules(rules)])


def merge_rules(
    left: Iterable[RedactionRule], right: Iterable[RedactionRule]
) -> tuple[RedactionRule, ...]:
    """Merge rule sets, letting later rules override earlier names."""
    merged: dict[str, RedactionRule] = {}
    for rule in [*left, *right]:
        merged[rule.name] = rule
    return tuple(sorted(merged.values(), key=lambda rule: (rule.priority, rule.name)))


def rule_names(rules: Iterable[RedactionRule]) -> tuple[str, ...]:
    """Return sorted rule names for display."""
    return tuple(sorted(rule.name for rule in rules))
