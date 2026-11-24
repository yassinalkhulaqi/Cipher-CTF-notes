"""Live redaction preview and enforcement for report designs.

Redaction runs on the immutable design tree before pagination and rendering,
so no renderer can accidentally emit an unredacted value. The preview API
returns the exact spans that would be replaced, including surrounding context,
which the React designer uses for its inline redaction controls.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from redscribe.v3.report_designer.identifiers import digest
from redscribe.v3.report_designer.model import (
    EvidenceItem,
    FindingItem,
    LayoutDocument,
    LayoutSection,
    RedactionRule,
)

FLAG_PATTERN = r"\b(?:flag|ctf)\{[^}\s]{4,}\}|(?i:\b[a-z0-9_]+\{[^}\s]{4,}\})"
EMAIL_PATTERN = r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"
IPV4_PATTERN = r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
SECRET_PATTERN = r"(?i)\b(?:api[_-]?key|secret|token|password|passwd)\b\s*[:=]\s*['\"]?[^\s'\"]{6,}"
PRIVATE_KEY_PATTERN = r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"
HOST_PATTERN = r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|local|internal|test)\b"
PHONE_PATTERN = r"\b(?:\+?\d{1,2}[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b"


@dataclass(frozen=True, slots=True)
class RedactionSpan:
    """One matched-and-replaced region of text."""

    rule: str
    start: int
    end: int
    matched: str
    replacement: str
    before: str = ""
    after: str = ""
    section_key: str = ""
    field_name: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "rule": self.rule,
            "start": self.start,
            "end": self.end,
            "matched": self.matched,
            "replacement": self.replacement,
            "before": self.before,
            "after": self.after,
            "section_key": self.section_key,
            "field": self.field_name,
        }


@dataclass(frozen=True, slots=True)
class RedactionPreview:
    """Result of applying rules, with an audit of every match."""

    text: str
    spans: tuple[RedactionSpan, ...] = ()
    applied: tuple[str, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total_matches(self) -> int:
        """Total number of replacements made."""
        return sum(self.counts.values())

    @property
    def leaked(self) -> tuple[str, ...]:
        """Matched secrets that still appear in the redacted text."""
        return tuple(
            span.matched
            for span in self.spans
            if span.matched and span.matched != span.replacement and span.matched in self.text
        )

    @property
    def is_complete(self) -> bool:
        """Whether every match was fully replaced."""
        return not self.leaked

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "text": self.text,
            "spans": [span.as_dict() for span in self.spans],
            "applied": list(self.applied),
            "counts": dict(self.counts),
            "total_matches": self.total_matches,
            "is_complete": self.is_complete,
        }


def builtin_redactions(
    *, include_hosts: bool = False, include_phones: bool = False
) -> tuple[RedactionRule, ...]:
    """Return built-in rules in deterministic priority order."""
    rules = [
        RedactionRule("private-key", PRIVATE_KEY_PATTERN, "[PRIVATE KEY]", priority=10),
        RedactionRule("api-secret", SECRET_PATTERN, "[SECRET]", priority=20),
        RedactionRule("email", EMAIL_PATTERN, "[EMAIL]", priority=30),
        RedactionRule("flag", FLAG_PATTERN, "[FLAG]", priority=40),
        RedactionRule("ipv4", IPV4_PATTERN, "[IP]", priority=50),
    ]
    if include_hosts:
        rules.append(RedactionRule("host", HOST_PATTERN, "[HOST]", priority=60))
    if include_phones:
        rules.append(RedactionRule("phone", PHONE_PATTERN, "[PHONE]", priority=70))
    return tuple(rules)


def compile_rule(rule: RedactionRule) -> re.Pattern[str]:
    """Compile a rule's pattern to a regular expression."""
    return re.compile(rule.pattern, re.IGNORECASE)


def sorted_rules(rules: Iterable[RedactionRule]) -> tuple[RedactionRule, ...]:
    """Return enabled rules ordered by priority and name."""
    return tuple(
        sorted(
            (rule for rule in rules if rule.enabled),
            key=lambda rule: (rule.priority, rule.name.casefold()),
        )
    )


def rules_for_scope(rules: Sequence[RedactionRule], scope: str) -> tuple[RedactionRule, ...]:
    """Return enabled rules that apply to a given field scope."""
    return tuple(rule for rule in sorted_rules(rules) if rule.scope in ("all", scope))


def redact_text(
    text: str,
    rules: Sequence[RedactionRule],
    *,
    section_key: str = "",
    field_name: str = "",
    context: int = 0,
) -> RedactionPreview:
    """Apply rules to text and return both output and match audit."""
    if context < 0:
        raise ValueError("context cannot be negative")
    spans: list[RedactionSpan] = []
    counts: dict[str, int] = {}
    applied: list[str] = []
    result = text
    for rule in sorted_rules(rules):
        pattern = compile_rule(rule)
        matches = list(pattern.finditer(result))
        if not matches:
            continue
        result = pattern.sub(rule.replacement, result)
        applied.append(rule.name)
        counts[rule.name] = counts.get(rule.name, 0) + len(matches)
        for match in matches:
            start = max(0, match.start() - context)
            end = min(len(text), match.end() + context)
            spans.append(
                RedactionSpan(
                    rule=rule.name,
                    start=match.start(),
                    end=match.end(),
                    matched=match.group(0),
                    replacement=rule.replacement,
                    before=text[start : match.start()],
                    after=text[match.end() : end],
                    section_key=section_key,
                    field_name=field_name,
                )
            )
    return RedactionPreview(result, tuple(spans), tuple(applied), counts)


def preview_document(
    document: LayoutDocument,
    rules: Sequence[RedactionRule],
    *,
    context: int = 18,
    max_spans: int = 200,
) -> RedactionPreview:
    """Preview every redaction that would fire across a whole design."""
    if max_spans < 1:
        raise ValueError("max_spans must be positive")
    texts: list[tuple[str, str, str]] = [
        ("document", "title", document.title),
        ("document", "subtitle", document.subtitle),
        ("document", "client", document.client),
    ]
    for section in document.visible_sections:
        texts.append((section.key, "title", section.title))
        texts.append((section.key, "body", section.body))
        texts.append((section.key, "summary", section.summary))
        for finding in section.findings:
            texts.append((finding.key, "finding.title", finding.title))
            texts.append((finding.key, "finding.summary", finding.summary))
            texts.append((finding.key, "finding.impact", finding.impact))
            for evidence in finding.evidence:
                texts.append((str(evidence.ref), "evidence.content", evidence.content))
    spans: list[RedactionSpan] = []
    applied: set[str] = set()
    counts: dict[str, int] = {}
    for section_key, field_name, text in texts:
        preview = redact_text(text, rules, section_key=section_key, field_name=field_name)
        applied.update(preview.applied)
        for name, count in preview.counts.items():
            counts[name] = counts.get(name, 0) + count
        spans.extend(preview.spans)
        if len(spans) >= max_spans:
            spans = spans[:max_spans]
            break
    return RedactionPreview("", tuple(spans), tuple(sorted(applied)), counts)


def redact_evidence(evidence: EvidenceItem, rules: Sequence[RedactionRule]) -> EvidenceItem:
    """Redact all visible fields of one evidence item."""
    evidence_rules = rules_for_scope(rules, "evidence")
    title_rules = rules_for_scope(rules, "title")
    return replace(
        evidence,
        title=redact_text(evidence.title, title_rules).text,
        content=redact_text(evidence.content, evidence_rules).text,
        excerpt=redact_text(evidence.excerpt, evidence_rules).text,
        locator=redact_text(evidence.locator, evidence_rules).text,
    )


def redact_finding(finding: FindingItem, rules: Sequence[RedactionRule]) -> FindingItem:
    """Redact all visible fields of one finding."""
    body_rules = rules_for_scope(rules, "body")
    title_rules = rules_for_scope(rules, "title")
    return replace(
        finding,
        title=redact_text(finding.title, title_rules).text,
        summary=redact_text(finding.summary, body_rules).text,
        impact=redact_text(finding.impact, body_rules).text,
        recommendation=redact_text(finding.recommendation, body_rules).text,
        evidence=tuple(redact_evidence(item, rules) for item in finding.evidence),
    )


def redact_section(section: LayoutSection, rules: Sequence[RedactionRule]) -> LayoutSection:
    """Recursively redact a section tree."""
    body_rules = rules_for_scope(rules, "body")
    title_rules = rules_for_scope(rules, "title")
    return replace(
        section,
        title=redact_text(section.title, title_rules).text,
        body=redact_text(section.body, body_rules).text,
        summary=redact_text(section.summary, body_rules).text,
        findings=tuple(redact_finding(item, rules) for item in section.findings),
        children=tuple(redact_section(child, rules) for child in section.children),
    )


def apply_redactions(document: LayoutDocument, rules: Sequence[RedactionRule]) -> LayoutDocument:
    """Return a design tree with every visible field redacted."""
    body_rules = rules_for_scope(rules, "body")
    title_rules = rules_for_scope(rules, "title")
    return replace(
        document,
        title=redact_text(document.title, title_rules).text,
        subtitle=redact_text(document.subtitle, body_rules).text,
        client=redact_text(document.client, body_rules).text,
        author=redact_text(document.author, body_rules).text,
        sections=tuple(redact_section(section, rules) for section in document.sections),
        findings=tuple(redact_finding(item, rules) for item in document.findings),
    )


def verify_redactions(document: LayoutDocument, rules: Sequence[RedactionRule]) -> bool:
    """Return whether a design contains no text matched by any enabled rule."""
    preview = preview_document(document, rules, max_spans=10000)
    return preview.total_matches == 0


def rule_digest(rules: Iterable[RedactionRule]) -> str:
    """Return a digest of the enabled rule set."""
    return digest([rule.as_dict() for rule in sorted_rules(rules)])
