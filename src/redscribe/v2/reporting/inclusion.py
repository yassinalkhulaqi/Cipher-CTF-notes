"""Finding inclusion rules and candidate selection."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace

from redscribe.v2.reporting.models import (
    InclusionRule,
    ReportConfig,
    Severity,
    SourceNote,
)
from redscribe.v2.reporting.severity import at_least
from redscribe.v2.reporting.source import OPEN_STATUSES


def _matches_text(value: str, expected: Sequence[str]) -> bool:
    if not expected:
        return True
    needle = value.casefold()
    return any(item.casefold() in needle for item in expected)


def _matches_exact(value: str, expected: Sequence[str]) -> bool:
    if not expected:
        return True
    normalized = value.casefold()
    return normalized in {item.casefold() for item in expected}


def rule_matches(rule: InclusionRule, note: SourceNote) -> bool:
    """Return whether a rule's criteria match one source note."""
    if rule.identifier and rule.identifier != str(note.identifier):
        return False
    if not _matches_exact(note.severity, rule.severities):
        return False
    if not _matches_exact(note.status, rule.statuses):
        return False
    if not _matches_exact(note.category, rule.categories):
        return False
    if not _matches_text(" ".join(note.tags), rule.tags):
        return False
    prefix = rule.path_prefix.casefold()
    return not prefix or note.path.casefold().startswith(prefix)


def rule_matches_finding(rule: InclusionRule, note: SourceNote) -> bool:
    """Alias with a finding-oriented name for pipeline callers."""
    return rule_matches(rule, note)


def select_notes(
    notes: Iterable[SourceNote],
    rules: Sequence[InclusionRule],
    *,
    tags: Sequence[str] = (),
    statuses: Sequence[str] = (),
    minimum_severity: str = "info",
) -> tuple[SourceNote, ...]:
    """Filter source notes with declarative rules and explicit filters."""
    result: list[SourceNote] = []
    for note in notes:
        if not at_least(note.severity, minimum_severity):
            continue
        note_tags = {value.casefold() for value in note.tags}
        if tags and not any(tag.casefold() in note_tags for tag in tags):
            continue
        if statuses and note.status not in statuses:
            continue
        excluded = any(rule.is_exclusion and rule_matches(rule, note) for rule in rules)
        if excluded:
            continue
        has_include = any(not rule.is_exclusion for rule in rules)
        included = any(not rule.is_exclusion and rule_matches(rule, note) for rule in rules)
        if has_include and not included:
            continue
        result.append(note)
    return tuple(result)


def inclusion_decision(note: SourceNote, rules: Sequence[InclusionRule]) -> tuple[bool, str]:
    """Return a decision and the name of the deciding rule."""
    for rule in rules:
        if rule_matches(rule, note):
            return (not rule.is_exclusion, rule.name)
    return (True, "default")


def default_rules() -> tuple[InclusionRule, ...]:
    """Return conservative default inclusion rules."""
    return (
        InclusionRule("sensitive-notes", "exclude", tags=("secret", "sensitive", "credential")),
        InclusionRule("draft-notes", "exclude", statuses=("blocked",)),
        InclusionRule(
            "reportable",
            "include",
            severities=("info", "low", "medium", "high", "critical"),
        ),
    )


def rules_for_config(config: ReportConfig) -> tuple[InclusionRule, ...]:
    """Return configured rules, falling back to the defaults."""
    return tuple(config.rules) if config.rules else default_rules()


def filter_by_confidence(notes: Iterable[SourceNote], minimum: float) -> tuple[SourceNote, ...]:
    """Filter notes by an inferred confidence score."""
    if not 0.0 <= minimum <= 1.0:
        raise ValueError("minimum must be between zero and one")
    return tuple(note for note in notes if _note_confidence(note) >= minimum)


def _note_confidence(note: SourceNote) -> float:
    score = 0.45
    if note.content.strip():
        score += 0.2
    if note.path:
        score += 0.1
    if note.target:
        score += 0.1
    if note.flag:
        score += 0.15
    return min(1.0, score)


def confidence_for(note: SourceNote) -> float:
    """Return a stable confidence score for a source note."""
    return round(_note_confidence(note), 3)


def rule_summary(rules: Iterable[InclusionRule]) -> dict[str, object]:
    """Summarize the active inclusion rule set."""
    items = list(rules)
    return {
        "total": len(items),
        "includes": sum(1 for rule in items if not rule.is_exclusion),
        "excludes": sum(1 for rule in items if rule.is_exclusion),
        "names": [rule.name for rule in items],
        "tagged": sum(1 for rule in items if rule.tags),
        "severity_scoped": sum(1 for rule in items if rule.severities),
    }


def rule_digest(rules: Iterable[InclusionRule]) -> str:
    """Return a stable digest of an inclusion rule set."""
    from redscribe.v2.reporting.identifiers import digest

    return digest([rule.as_dict() for rule in rules])


def notes_to_finding_evidence(notes: Iterable[SourceNote]) -> tuple[object, ...]:
    """Prepare note snapshots for finding construction."""
    return tuple(
        replace(
            note,
            tags=tuple(dict.fromkeys(note.tags)),
        )
        for note in notes
    )


def apply_inclusion(notes: Iterable[SourceNote], config: ReportConfig) -> tuple[SourceNote, ...]:
    """Apply a configuration's inclusion policy to source notes."""
    selected = select_notes(
        notes,
        rules_for_config(config),
        tags=config.tags,
        statuses=config.statuses,
        minimum_severity=config.minimum_severity,
    )
    return filter_by_confidence(selected, 0.4)


def open_only(notes: Iterable[SourceNote]) -> tuple[SourceNote, ...]:
    """Return notes whose status indicates active work."""
    return tuple(note for note in notes if note.status in OPEN_STATUSES)


def severity_threshold(note: SourceNote, threshold: str) -> bool:
    """Return whether a note meets a severity threshold."""
    return Severity.parse(note.severity).rank >= Severity.parse(threshold).rank


def normalize_rules(rules: Iterable[InclusionRule]) -> tuple[InclusionRule, ...]:
    """Deduplicate rules by name, keeping the last definition."""
    result: dict[str, InclusionRule] = {}
    for rule in rules:
        result[rule.name] = rule
    return tuple(result.values())


def all_rule_tags(rules: Iterable[InclusionRule]) -> tuple[str, ...]:
    """Return sorted distinct tags mentioned by rules."""
    tags = {tag for rule in rules for tag in rule.tags}
    return tuple(sorted(tags, key=str.casefold))


def evidence_rules() -> tuple[InclusionRule, ...]:
    """Return rules that select notes suitable as evidence only."""
    return (
        InclusionRule("evidence-notes", "include", tags=("evidence", "artifact", "command")),
        InclusionRule("no-findings", "exclude", tags=("no-report",)),
    )


def sort_selected(notes: Iterable[SourceNote]) -> tuple[SourceNote, ...]:
    """Sort selected notes by severity and update time, then identifier."""
    return tuple(
        sorted(
            notes,
            key=lambda note: (
                -Severity.parse(note.severity).rank,
                note.updated_at,
                note.identifier,
            ),
        )
    )
