"""Severity calculations and reporting summaries."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence

from redscribe.v2.reporting.models import (
    SEVERITY_ORDER,
    Finding,
    Severity,
    SeverityCounts,
    SeverityName,
)


def count_severities(findings: Iterable[Finding]) -> SeverityCounts:
    """Count findings by normalized severity name."""
    counts = SeverityCounts()
    for finding in findings:
        counts = counts.increment(finding.severity)
    return counts


def severity_totals(findings: Iterable[Finding]) -> dict[str, int]:
    """Return severity counts in display order."""
    return count_severities(findings).as_dict()


def severity_index(severity: str) -> int:
    """Return the ordinal rank of a severity label."""
    return Severity.parse(severity).rank


def at_least(severity: str, minimum: str) -> bool:
    """Return whether ``severity`` meets or exceeds ``minimum``."""
    return severity_index(severity) >= severity_index(minimum)


def sort_findings(
    findings: Iterable[Finding],
    *,
    descending: bool = True,
    stable: bool = True,
) -> tuple[Finding, ...]:
    """Order findings by severity, confidence, status, and identifier."""
    items = list(findings)
    if stable:
        items.sort(key=lambda finding: finding.identifier.casefold())
        items.sort(key=lambda finding: finding.confidence, reverse=True)
    items.sort(
        key=lambda finding: (
            finding.severity_level.rank,
            finding.status != "open",
            finding.identifier.casefold(),
        ),
        reverse=descending,
    )
    if descending and stable:
        items.sort(key=lambda finding: finding.severity_level.rank, reverse=True)
    return tuple(items)


def filter_minimum_severity(findings: Iterable[Finding], minimum: str) -> tuple[Finding, ...]:
    """Keep findings at or above a severity threshold."""
    return tuple(finding for finding in findings if at_least(finding.severity, minimum))


def severity_summary(counts: SeverityCounts) -> dict[str, object]:
    """Return a presentation-ready severity summary."""
    values = counts.as_dict()
    total = counts.total()
    return {
        "counts": dict(values),
        "total": total,
        "highest": counts.highest(),
        "weighted": counts.weighted(),
        "risk_level": risk_level(counts),
        "bar": severity_bar(counts),
        "percentages": {
            name: (round(count * 100 / total, 1) if total else 0.0)
            for name, count in values.items()
        },
    }


def risk_level(counts: SeverityCounts) -> str:
    """Translate severity counts into a single risk band."""
    if counts.critical:
        return "critical"
    if counts.high:
        return "high"
    if counts.medium:
        return "medium"
    if counts.low:
        return "low"
    return "informational"


def severity_bar(counts: SeverityCounts, *, width: int = 20) -> str:
    """Render a small ASCII severity distribution bar."""
    if width < 4:
        raise ValueError("width must be at least 4")
    values = counts.as_dict()
    total = counts.total()
    if not total:
        return "." * width
    blocks = "▁▃▅▇█"
    segments: list[str] = []
    for name in reversed(SEVERITY_ORDER):
        count = int(values[name])
        size = max(1, round(count * width / total)) if count else 0
        level = SEVERITY_ORDER.index(name)
        segments.append(blocks[min(level, len(blocks) - 1)] * size)
    bar = "".join(segments)
    return bar[:width].ljust(width, ".")


def merge_counts(left: SeverityCounts, right: SeverityCounts) -> SeverityCounts:
    """Add two severity count objects."""
    a = left.as_dict()
    b = right.as_dict()
    return SeverityCounts(**{name: a[name] + b[name] for name in SEVERITY_ORDER})


def counts_from_values(values: dict[str, int]) -> SeverityCounts:
    """Build counts from a partially populated mapping."""
    normalized: dict[str, int] = {}
    for name in SEVERITY_ORDER:
        raw = values.get(name, 0)
        normalized[name] = max(0, int(raw))
    return SeverityCounts(**normalized)


def severity_counts_from_pairs(pairs: Sequence[tuple[str, int]]) -> SeverityCounts:
    """Build counts from ``(severity, count)`` pairs, last value winning."""
    return counts_from_values(dict(pairs))


def severity_distribution(findings: Iterable[Finding]) -> Counter[str]:
    """Return a counter keyed by normalized severity."""
    return Counter(finding.severity_level.value for finding in findings)


def format_count_line(label: str, count: int) -> str:
    """Format one label/count line for a report summary table."""
    return f"| {label} | {count} |"


def severity_table(counts: SeverityCounts) -> str:
    """Render a Markdown table of severity totals."""
    rows = [
        "| Severity | Count |",
        "| --- | ---: |",
        *[
            format_count_line(Severity.parse(name).label, int(count))
            for name, count in counts.as_dict().items()
        ],
        f"| **Total** | {counts.total()} |",
    ]
    return "\n".join(rows)


def severity_label(severity: SeverityName | str) -> str:
    """Return a human label for a severity value."""
    return Severity.parse(severity).label
