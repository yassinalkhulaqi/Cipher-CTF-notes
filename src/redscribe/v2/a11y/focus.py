"""Focus-order analysis and keyboard navigation helpers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from redscribe.v2.a11y.models import (
    AuditIssue,
    ElementNode,
    FocusMode,
    FocusReport,
    FocusStep,
    Severity,
    severity_rank,
)

FOCUSABLE_TAGS: frozenset[str] = frozenset(
    {"a", "area", "button", "input", "select", "textarea", "summary", "audio", "video"}
)
SKIP_LINK_RE = re.compile(r"skip|jump to (main|content)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class FocusCandidate:
    """An element that can receive keyboard focus."""

    node: ElementNode
    tab_index: int
    natural_order: int
    hidden: bool
    label: str

    @property
    def target(self) -> str:
        return (
            self.node.path
            or self.node.element_id
            or self.node.attr("aria-label")
            or self.node.normalized_tag
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "tag": self.node.normalized_tag,
            "tab_index": self.tab_index,
            "order": self.natural_order,
            "hidden": self.hidden,
            "label": self.label,
        }


def is_focusable(node: ElementNode) -> bool:
    """Return whether an element can receive focus."""
    if not node.visible or node.attr("aria-hidden") == "true":
        return False
    tag = node.normalized_tag
    if tag in FOCUSABLE_TAGS:
        return not node.has_attr("disabled")
    if node.has_attr("tabindex"):
        return True
    return bool(
        node.role and node.role in {"button", "checkbox", "link", "textbox", "combobox", "option"}
    )


def parse_tab_index(node: ElementNode) -> int:
    """Parse tabindex, using zero for elements without an explicit value."""
    raw = node.attr("tabindex")
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def describe_focusable(node: ElementNode) -> str:
    """Return a short human-readable label for a focusable element."""
    for attribute in ("aria-label", "title", "placeholder", "alt"):
        value = node.attr(attribute).strip()
        if value:
            return value
    text = " ".join(part for part in (node.text.strip(),) if part)
    if text:
        return text[:80]
    return node.element_id or node.normalized_tag


def collect_focusables(nodes: Sequence[ElementNode]) -> list[FocusCandidate]:
    """Collect focusable elements in document order."""
    result: list[FocusCandidate] = []
    for node in nodes:
        for item in [node, *node.descendants()]:
            if not is_focusable(item):
                continue
            result.append(
                FocusCandidate(
                    node=item,
                    tab_index=parse_tab_index(item),
                    natural_order=len(result),
                    hidden=not item.visible or item.attr("aria-hidden") == "true",
                    label=describe_focusable(item),
                )
            )
    return result


def compute_tab_order(candidates: Sequence[FocusCandidate]) -> list[FocusCandidate]:
    """Sort focusable elements into effective keyboard tab order."""
    positives = [item for item in candidates if item.tab_index > 0]
    zeros = [item for item in candidates if item.tab_index == 0]
    positives.sort(key=lambda item: (item.tab_index, item.natural_order))
    zeros.sort(key=lambda item: item.natural_order)
    return [*positives, *zeros]


def is_skip_link(node: ElementNode) -> bool:
    """Return whether an element looks like a skip link."""
    if node.normalized_tag != "a":
        return False
    text = " ".join([node.text, node.attr("aria-label"), node.attr("href")])
    return bool(SKIP_LINK_RE.search(text))


def has_skip_link(nodes: Sequence[ElementNode]) -> bool:
    """Return whether any tree contains a skip link."""
    for node in nodes:
        for item in [node, *node.descendants()]:
            if is_skip_link(item):
                return True
    return False


def _issue(
    rule: str,
    message: str,
    target: str,
    severity: Severity,
    remediation: str,
) -> AuditIssue:
    return AuditIssue(
        rule=rule,
        severity=severity,
        message=message,
        target=target,
        wcag="2.4.3",
        remediation=remediation,
    )


def analyze_focus_order(
    nodes: Sequence[ElementNode],
    *,
    require_skip_link: bool = True,
    max_tab_index: int = 0,
) -> FocusReport:
    """Analyze focus order and report keyboard accessibility problems."""
    candidates = collect_focusables(nodes)
    ordered = compute_tab_order(candidates)
    issues: list[AuditIssue] = []
    positive = [item for item in candidates if item.tab_index > 0]
    negative = [item for item in candidates if item.tab_index < 0]

    for item in positive:
        issues.append(
            _issue(
                "focus-positive-tabindex",
                f"Positive tabindex {item.tab_index} breaks natural focus order",
                item.target,
                Severity.MODERATE,
                "Use tabindex='0' and reorder the DOM instead",
            )
        )
        if max_tab_index and item.tab_index > max_tab_index:
            issues.append(
                _issue(
                    "focus-tabindex-too-high",
                    f"tabindex {item.tab_index} exceeds the allowed maximum",
                    item.target,
                    Severity.SERIOUS,
                    f"Use a tabindex no greater than {max_tab_index}",
                )
            )

    for item in negative:
        if item.node.normalized_tag in FOCUSABLE_TAGS:
            issues.append(
                _issue(
                    "focus-removed-from-tab-order",
                    "Interactive element is removed from the tab order",
                    item.target,
                    Severity.SERIOUS,
                    "Remove tabindex='-1' unless focus is managed manually",
                )
            )

    for item in candidates:
        if item.hidden:
            issues.append(
                _issue(
                    "focus-hidden-element",
                    "Hidden element remains in the tab order",
                    item.target,
                    Severity.CRITICAL,
                    "Hide the element with display:none or remove it from the DOM",
                )
            )

    for item in ordered:
        if item.node.normalized_tag == "a" and not item.node.attr("href"):
            issues.append(
                _issue(
                    "focus-link-without-href",
                    "Link cannot be reached by keyboard without href",
                    item.target,
                    Severity.SERIOUS,
                    "Add an href or use a button element",
                )
            )
        if item.node.normalized_tag == "button" and not describe_focusable(item.node):
            issues.append(
                _issue(
                    "focus-unlabeled-control",
                    "Focusable control has no discernible label",
                    item.target,
                    Severity.SERIOUS,
                    "Add visible text or an aria-label",
                )
            )

    skip = has_skip_link(nodes)
    if require_skip_link and candidates and not skip:
        issues.append(
            _issue(
                "focus-no-skip-link",
                "No skip link was found before repeated navigation content",
                "document",
                Severity.MINOR,
                "Add a skip link as the first focusable element",
            )
        )
    elif skip:
        first = ordered[0] if ordered else None
        if first is not None and not is_skip_link(first.node):
            issues.append(
                _issue(
                    "focus-skip-link-not-first",
                    "Skip link is not the first element in the tab order",
                    first.target,
                    Severity.MINOR,
                    "Move the skip link to the start of the document",
                )
            )

    duplicates: dict[str, list[FocusCandidate]] = {}
    for item in ordered:
        label = item.label.strip().lower()
        if label:
            duplicates.setdefault(label, []).append(item)
    for label, items in duplicates.items():
        if len(items) > 3:
            issues.append(
                _issue(
                    "focus-ambiguous-label",
                    f"{len(items)} controls share the label '{label}'",
                    items[0].target,
                    Severity.MINOR,
                    "Give each control a unique accessible name",
                )
            )

    steps = tuple(
        FocusStep(
            order=index + 1,
            target=item.target,
            tag=item.node.normalized_tag,
            tab_index=item.tab_index,
            description=item.label,
            hidden=item.hidden,
        )
        for index, item in enumerate(ordered)
    )
    penalty = sum(max(1, int(severity_rank(item.severity))) for item in issues)
    score = max(0.0, 100.0 - penalty * 8.0)
    return FocusReport(
        steps=steps,
        issues=tuple(issues),
        focusable_count=len(candidates),
        positive_tabindex_count=len(positive),
        has_skip_link=skip,
        score=score,
    )


def simulate_tabs(
    nodes: Sequence[ElementNode],
    *,
    presses: int = 5,
    start: int = -1,
    wrap: bool = False,
) -> list[FocusStep]:
    """Simulate a number of Tab presses through a focus order."""
    report = analyze_focus_order(nodes, require_skip_link=False)
    steps = list(report.steps)
    if not steps:
        return []
    result: list[FocusStep] = []
    index = start
    for _ in range(max(0, presses)):
        index += 1
        if index >= len(steps):
            if not wrap:
                break
            index = 0
        result.append(steps[index])
    return result


def detect_traps(candidates: Sequence[FocusCandidate]) -> list[str]:
    """Return targets where focus cannot progress naturally."""
    ordered = compute_tab_order(candidates)
    traps: list[str] = []
    if not ordered:
        return traps
    seen: dict[str, int] = {}
    for item in ordered:
        seen[item.target] = seen.get(item.target, 0) + 1
    for target, count in seen.items():
        if count > 1:
            traps.append(target)
    if len(ordered) == 1 and ordered[0].node.role in {"dialog", "alertdialog"}:
        traps.append(ordered[0].target)
    return sorted(traps)


def focus_mode_for(node: ElementNode) -> FocusMode:
    """Infer the shortcut scope that applies to an element."""
    if node.role in {"dialog", "alertdialog"} or node.normalized_tag == "dialog":
        return FocusMode.DIALOG
    if node.normalized_tag in {"textarea", "input"} or node.role == "textbox":
        return FocusMode.EDITOR
    if node.role in {"navigation", "tree", "listbox"}:
        return FocusMode.SIDEBAR
    if node.normalized_tag == "article":
        return FocusMode.READING
    return FocusMode.GLOBAL


def focus_summary(report: FocusReport) -> dict[str, Any]:
    """Return a compact focus report summary."""
    return {
        "score": round(report.score, 1),
        "focusable": report.focusable_count,
        "steps": len(report.steps),
        "issues": len(report.issues),
        "skip_link": report.has_skip_link,
        "positive_tabindex": report.positive_tabindex_count,
    }
