"""Deterministic WCAG 2.2 audit rules for V3 surfaces.

The V2 ``AccessibilityAuditor`` covers structural markup concerns. This module
adds the success criteria introduced by WCAG 2.2 plus V3-specific keyboard and
localization checks. Rules are data: adding one never changes a dispatch table.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from redscribe.v2.a11y.models import Severity, WcagLevel, severity_rank
from redscribe.v3.a11y_refinement.models import (
    AuditRun,
    RuleFinding,
    RuleScope,
    SurfaceSpec,
    WcagRule,
)

MIN_TARGET_SIZE = 24
ENHANCED_TARGET_SIZE = 44
MIN_FOCUS_INDICATOR = 2
MIN_FOCUS_CONTRAST = 3.0

WCAG22_RULES: tuple[WcagRule, ...] = (
    WcagRule(
        rule_id="focus.not_obscured",
        criterion="2.4.11",
        title="Focus Not Obscured (Minimum)",
        level=WcagLevel.AA,
        scope=RuleScope.FOCUS,
        description="The focused component is not entirely hidden by authored content.",
        remediation="Ensure sticky headers and overlays never cover the focused control.",
    ),
    WcagRule(
        rule_id="focus.not_obscured.enhanced",
        criterion="2.4.12",
        title="Focus Not Obscured (Enhanced)",
        level=WcagLevel.AAA,
        scope=RuleScope.FOCUS,
        description="No part of the focused component is hidden by authored content.",
        remediation="Reserve space for focus rings near sticky or floating surfaces.",
    ),
    WcagRule(
        rule_id="focus.appearance",
        criterion="2.4.13",
        title="Focus Appearance",
        level=WcagLevel.AAA,
        scope=RuleScope.FOCUS,
        description="The focus indicator has sufficient area and contrast.",
        remediation="Use a two-pixel or thicker indicator with at least 3:1 contrast.",
    ),
    WcagRule(
        rule_id="pointer.dragging",
        criterion="2.5.7",
        title="Dragging Movements",
        level=WcagLevel.AA,
        scope=RuleScope.POINTER,
        description="Every drag interaction has a single-pointer alternative.",
        remediation="Add click, keyboard, or menu alternatives to drag-only actions.",
    ),
    WcagRule(
        rule_id="pointer.target_size",
        criterion="2.5.8",
        title="Target Size (Minimum)",
        level=WcagLevel.AA,
        scope=RuleScope.POINTER,
        description="Pointer targets are at least 24 by 24 CSS pixels.",
        remediation="Increase the hit area or add spacing around compact controls.",
    ),
    WcagRule(
        rule_id="help.consistent",
        criterion="3.2.6",
        title="Consistent Help",
        level=WcagLevel.A,
        scope=RuleScope.DOCUMENT,
        description="Help mechanisms appear in a consistent relative order.",
        remediation="Place help in the same location on every V3 surface.",
    ),
    WcagRule(
        rule_id="form.redundant_entry",
        criterion="3.3.7",
        title="Redundant Entry",
        level=WcagLevel.A,
        scope=RuleScope.FORM,
        description="Information already entered is prefilled or selectable.",
        remediation="Reuse previously supplied values in multi-step flows.",
    ),
    WcagRule(
        rule_id="auth.accessible",
        criterion="3.3.8",
        title="Accessible Authentication (Minimum)",
        level=WcagLevel.AA,
        scope=RuleScope.FORM,
        description="Authentication does not require a cognitive function test.",
        remediation="Offer a copy/paste friendly token or an alternative factor.",
    ),
    WcagRule(
        rule_id="auth.accessible.enhanced",
        criterion="3.3.9",
        title="Accessible Authentication (Enhanced)",
        level=WcagLevel.AAA,
        scope=RuleScope.FORM,
        description="No cognitive function test is required at any stage.",
        remediation="Remove object-recognition and puzzle steps entirely.",
    ),
    WcagRule(
        rule_id="contrast.non_text",
        criterion="1.4.11",
        title="Non-text Contrast",
        level=WcagLevel.AA,
        scope=RuleScope.CONTENT,
        description="Control boundaries and meaningful graphics reach 3:1.",
        remediation="Darken borders and status indicators to at least 3:1.",
    ),
    WcagRule(
        rule_id="content.hoverable",
        criterion="1.4.13",
        title="Content on Hover or Focus",
        level=WcagLevel.AA,
        scope=RuleScope.CONTENT,
        description="Hover content is dismissible, hoverable, and persistent.",
        remediation="Keep tooltips visible while hovering and allow Escape to dismiss.",
    ),
    WcagRule(
        rule_id="keyboard.reachable",
        criterion="2.1.1",
        title="Keyboard",
        level=WcagLevel.A,
        scope=RuleScope.FOCUS,
        description="Every interactive surface control is reachable by keyboard.",
        remediation="Use native focusable elements and a documented tab order.",
    ),
    WcagRule(
        rule_id="labels.screen_reader",
        criterion="4.1.2",
        title="Name, Role, Value",
        level=WcagLevel.A,
        scope=RuleScope.CONTENT,
        description="Interactive controls expose a name, role, and current value.",
        remediation="Add aria-label, aria-expanded, and value text where needed.",
    ),
    WcagRule(
        rule_id="locale.direction",
        criterion="3.1.1",
        title="Language of Page",
        level=WcagLevel.A,
        scope=RuleScope.LOCALIZATION,
        description="The active locale is valid and drives document direction.",
        remediation="Use a BCP 47 tag and propagate dir/lang to the surface root.",
    ),
)

_RULES_BY_ID = {rule.rule_id: rule for rule in WCAG22_RULES}


def rule_by_id(rule_id: str) -> WcagRule | None:
    """Look up a rule by its stable identifier."""
    return _RULES_BY_ID.get(rule_id)


def rules_for_level(level: str | WcagLevel) -> tuple[WcagRule, ...]:
    """Return rules at or below the requested conformance level."""
    target = level if isinstance(level, WcagLevel) else WcagLevel(level.upper())
    ranks = {WcagLevel.A: 1, WcagLevel.AA: 2, WcagLevel.AAA: 3}
    return tuple(rule for rule in WCAG22_RULES if ranks[rule.level] <= ranks[target])


def _finding(
    rule: WcagRule,
    surface: SurfaceSpec,
    severity: Severity,
    message: str,
    *,
    details: Mapping[str, object] | None = None,
) -> RuleFinding:
    return RuleFinding(
        rule_id=rule.rule_id,
        criterion=rule.criterion,
        severity=severity.value,
        target=surface.name,
        message=message,
        remediation=rule.remediation,
        details=dict(details or {}),
    )


def _check_focus(surface: SurfaceSpec, rules: dict[str, WcagRule]) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    obscured = surface.focus_obscured.strip().lower()
    if obscured in {"partial", "full", "fully"}:
        rule = rules["focus.not_obscured"]
        findings.append(
            _finding(
                rule,
                surface,
                Severity.SERIOUS,
                f"Focused control on '{surface.name}' is {obscured} obscured",
                details={"state": obscured},
            )
        )
    if obscured in {"full", "fully"}:
        findings.append(
            _finding(
                rules["focus.not_obscured.enhanced"],
                surface,
                Severity.MODERATE,
                "No part of the focused control is visible",
                details={"state": obscured},
            )
        )
    if surface.focus_indicator_width < MIN_FOCUS_INDICATOR:
        findings.append(
            _finding(
                rules["focus.appearance"],
                surface,
                Severity.SERIOUS,
                f"Focus indicator is {surface.focus_indicator_width}px wide on '{surface.name}'",
                details={"width": surface.focus_indicator_width},
            )
        )
    elif surface.focus_indicator_contrast < MIN_FOCUS_CONTRAST:
        findings.append(
            _finding(
                rules["focus.appearance"],
                surface,
                Severity.MODERATE,
                f"Focus indicator contrast is {surface.focus_indicator_contrast:.2f}:1",
                details={"contrast": surface.focus_indicator_contrast},
            )
        )
    if not surface.keyboard_reachable:
        findings.append(
            _finding(
                rules["keyboard.reachable"],
                surface,
                Severity.CRITICAL,
                f"'{surface.name}' has controls that cannot be reached by keyboard",
            )
        )
    return findings


def _check_pointer(surface: SurfaceSpec, rules: dict[str, WcagRule]) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    if surface.drag_only:
        findings.append(
            _finding(
                rules["pointer.dragging"],
                surface,
                Severity.SERIOUS,
                f"'{surface.name}' relies on dragging without a single-pointer alternative",
            )
        )
    if surface.target_size < MIN_TARGET_SIZE:
        findings.append(
            _finding(
                rules["pointer.target_size"],
                surface,
                Severity.SERIOUS if surface.target_size < 12 else Severity.MODERATE,
                f"Target size on '{surface.name}' is {surface.target_size}px",
                details={"size": surface.target_size, "minimum": MIN_TARGET_SIZE},
            )
        )
    elif surface.target_size < ENHANCED_TARGET_SIZE and surface.level == WcagLevel.AAA:
        findings.append(
            _finding(
                rules["pointer.target_size"],
                surface,
                Severity.MINOR,
                f"Target size {surface.target_size}px does not reach the enhanced 44px guidance",
                details={"size": surface.target_size, "enhanced": ENHANCED_TARGET_SIZE},
            )
        )
    return findings


def _check_content(surface: SurfaceSpec, rules: dict[str, WcagRule]) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    if surface.non_text_contrast < 3.0:
        findings.append(
            _finding(
                rules["contrast.non_text"],
                surface,
                Severity.SERIOUS if surface.non_text_contrast < 2.0 else Severity.MODERATE,
                f"Non-text contrast on '{surface.name}' is {surface.non_text_contrast:.2f}:1",
                details={"ratio": surface.non_text_contrast},
            )
        )
    if surface.hover_content:
        findings.append(
            _finding(
                rules["content.hoverable"],
                surface,
                Severity.MODERATE,
                f"'{surface.name}' shows hover content without a persistence guarantee",
            )
        )
    if not surface.screen_reader_labels:
        findings.append(
            _finding(
                rules["labels.screen_reader"],
                surface,
                Severity.SERIOUS,
                f"'{surface.name}' has controls without screen-reader labels",
            )
        )
    return findings


def _check_forms(surface: SurfaceSpec, rules: dict[str, WcagRule]) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    if not surface.has_help:
        findings.append(
            _finding(
                rules["help.consistent"],
                surface,
                Severity.MINOR,
                f"'{surface.name}' has no help mechanism in the expected location",
            )
        )
    if surface.repeated_entry:
        findings.append(
            _finding(
                rules["form.redundant_entry"],
                surface,
                Severity.MODERATE,
                f"'{surface.name}' asks users to re-enter information twice",
            )
        )
    auth = surface.auth_captcha.strip().lower()
    if auth in {"puzzle", "captcha", "cognitive"}:
        findings.append(
            _finding(
                rules["auth.accessible"],
                surface,
                Severity.SERIOUS,
                f"'{surface.name}' requires a {auth} authentication step",
                details={"mode": auth},
            )
        )
    if auth in {"puzzle", "cognitive", "object_recognition"}:
        findings.append(
            _finding(
                rules["auth.accessible.enhanced"],
                surface,
                Severity.MODERATE,
                f"'{surface.name}' requires a cognitive function test",
                details={"mode": auth},
            )
        )
    return findings


def _check_locale(surface: SurfaceSpec, rules: dict[str, WcagRule]) -> list[RuleFinding]:
    locale = surface.locale.strip()
    if locale and "-" not in locale and locale.isalpha() and len(locale) == 2:
        return []
    return [
        _finding(
            rules["locale.direction"],
            surface,
            Severity.MODERATE,
            f"'{surface.name}' declares an invalid language tag '{locale}'",
            details={"locale": locale},
        )
    ]


def audit_surface(spec: SurfaceSpec, *, level: str | WcagLevel | None = None) -> AuditRun:
    """Audit a single surface and return a deterministic report."""
    selected_level = level if level is not None else spec.level
    target = (
        selected_level
        if isinstance(selected_level, WcagLevel)
        else WcagLevel(str(selected_level).upper())
    )
    applicable = rules_for_level(target)
    rules = _RULES_BY_ID
    findings: list[RuleFinding] = []
    findings.extend(_check_focus(spec, rules))
    findings.extend(_check_pointer(spec, rules))
    findings.extend(_check_content(spec, rules))
    findings.extend(_check_forms(spec, rules))
    findings.extend(_check_locale(spec, rules))
    relevant = {item.rule_id for item in applicable}
    findings = [item for item in findings if item.rule_id in relevant]
    findings.sort(key=lambda item: (-severity_rank(item.severity), item.rule_id, item.target))
    fired = {item.rule_id for item in findings}
    passed = tuple(rule.rule_id for rule in applicable if rule.rule_id not in fired)
    penalty = sum(max(1, severity_rank(item.severity) * 2) for item in findings)
    score = max(0.0, 100.0 - penalty)
    return AuditRun(
        surface=spec.name,
        level=target,
        findings=tuple(findings),
        passed_rules=passed,
        checked=len(applicable),
        score=score,
    )


def audit_surfaces(
    specs: Sequence[SurfaceSpec],
    *,
    level: str | WcagLevel | None = None,
) -> tuple[AuditRun, ...]:
    """Audit a batch of surfaces in stable order."""
    return tuple(audit_surface(spec, level=level) for spec in specs)


def summarize_runs(runs: Sequence[AuditRun]) -> dict[str, object]:
    """Aggregate a batch of audit runs into dashboard metrics."""
    findings = [item for run in runs for item in run.findings]
    by_severity: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
    score = sum(run.score for run in runs) / len(runs) if runs else 100.0
    return {
        "surfaces": len(runs),
        "passed": sum(1 for run in runs if run.passed),
        "failed": sum(1 for run in runs if not run.passed),
        "findings": len(findings),
        "by_severity": by_severity,
        "checked_rules": sum(run.checked for run in runs),
        "score": round(score, 1),
        "criteria": sorted({item.criterion for item in findings}),
    }


__all__ = [
    "ENHANCED_TARGET_SIZE",
    "MIN_FOCUS_CONTRAST",
    "MIN_FOCUS_INDICATOR",
    "MIN_TARGET_SIZE",
    "WCAG22_RULES",
    "audit_surface",
    "audit_surfaces",
    "rule_by_id",
    "rules_for_level",
    "summarize_runs",
]
