"""Static accessibility auditing for element trees and theme palettes."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v2.a11y.aria import compute_accessible_name, validate_tree
from redscribe.v2.a11y.contrast import build_report, palette_pairs
from redscribe.v2.a11y.focus import analyze_focus_order, has_skip_link, is_focusable
from redscribe.v2.a11y.i18n.locales import is_valid_locale, normalize_locale
from redscribe.v2.a11y.models import (
    AuditIssue,
    AuditReport,
    ElementNode,
    Severity,
    ThemeDefinition,
    WcagLevel,
    severity_rank,
)
from redscribe.v2.a11y.themes import missing_tokens

HEADING_RE = re.compile(r"^h([1-6])$")
GENERIC_LINK_TEXT: frozenset[str] = frozenset(
    {"click here", "here", "read more", "more", "link", "learn more", "this"}
)
LANDMARK_TAGS: frozenset[str] = frozenset({"header", "nav", "main", "aside", "footer", "form"})
LANDMARK_ROLES: frozenset[str] = frozenset(
    {"banner", "navigation", "main", "complementary", "contentinfo", "search", "form", "region"}
)
INTERACTIVE_TAGS: frozenset[str] = frozenset(
    {"button", "a", "input", "select", "textarea", "summary"}
)


def node_from_payload(payload: Mapping[str, Any], *, path: str = "") -> ElementNode:
    """Build an ElementNode from an API payload."""
    tag = str(payload.get("tag") or payload.get("element") or "div")
    attrs = {
        str(key): str(value)
        for key, value in (payload.get("attrs") or payload.get("attributes") or {}).items()
        if isinstance(value, (str, int, float, bool))
    }
    children_payload = payload.get("children") or []
    children = tuple(
        node_from_payload(child, path=f"{path}/{index}")
        for index, child in enumerate(children_payload)
        if isinstance(child, Mapping)
    )
    return ElementNode(
        tag=tag,
        attrs=attrs,
        text=str(payload.get("text") or ""),
        children=children,
        visible=bool(payload.get("visible", True)),
        path=path or str(payload.get("path") or tag),
    )


def nodes_from_payload(payload: Sequence[Any]) -> tuple[ElementNode, ...]:
    """Build a list of ElementNodes from a payload sequence."""
    return tuple(
        node_from_payload(item, path=f"/{index}")
        for index, item in enumerate(payload)
        if isinstance(item, Mapping)
    )


def flatten(nodes: Sequence[ElementNode]) -> list[ElementNode]:
    """Return all nodes in a tree sequence."""
    result: list[ElementNode] = []
    for node in nodes:
        result.append(node)
        result.extend(node.descendants())
    return result


def _issue(
    rule: str,
    message: str,
    *,
    target: str = "",
    severity: Severity = Severity.MODERATE,
    wcag: str = "",
    remediation: str = "",
    details: Mapping[str, Any] | None = None,
) -> AuditIssue:
    return AuditIssue(
        rule=rule,
        severity=severity,
        message=message,
        target=target,
        wcag=wcag,
        remediation=remediation,
        details=dict(details or {}),
    )


@dataclass(slots=True)
class AccessibilityAuditor:
    """Run deterministic static accessibility checks."""

    locale: str = "en"
    level: WcagLevel = WcagLevel.AA
    require_skip_link: bool = True
    require_landmarks: bool = True
    checked_rules: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.locale = normalize_locale(self.locale)
        if isinstance(self.level, str):
            self.level = WcagLevel(self.level.upper())
        base_rules = (
            "document.lang",
            "document.landmarks",
            "heading.order",
            "image.alt",
            "link.text",
            "control.label",
            "focus.order",
            "aria.valid",
        )
        self.checked_rules = base_rules

    def audit(
        self,
        nodes: Sequence[ElementNode],
        *,
        theme: ThemeDefinition | None = None,
        palette: Mapping[str, str] | None = None,
    ) -> AuditReport:
        """Audit an element tree and optional color palette."""
        issues: list[AuditIssue] = []
        all_nodes = flatten(nodes)
        issues.extend(self._check_document(nodes, all_nodes))
        issues.extend(self._check_headings(all_nodes))
        issues.extend(self._check_images(all_nodes))
        issues.extend(self._check_links(all_nodes))
        issues.extend(self._check_controls(all_nodes))
        issues.extend(self._check_tables(all_nodes))
        issues.extend(self._check_motion(all_nodes))
        aria = validate_tree(nodes)
        issues.extend(
            _issue(
                f"aria.{item.rule}",
                item.message,
                target=item.target,
                severity=item.severity,
                wcag="4.1.2",
                remediation=item.remediation,
            )
            for item in aria.issues
        )
        focus = analyze_focus_order(nodes, require_skip_link=self.require_skip_link)
        for item in focus.issues:
            issues.append(
                _issue(
                    f"focus.{item.rule}",
                    item.message,
                    target=item.target,
                    severity=item.severity,
                    wcag=item.wcag,
                    remediation=item.remediation,
                )
            )
        if theme is not None:
            issues.extend(self._check_theme(theme))
        if palette is not None:
            issues.extend(self._check_palette(palette))

        unique: dict[tuple[str, str, str], AuditIssue] = {}
        for item in issues:
            key = (item.rule, item.target, item.message)
            if key not in unique:
                unique[key] = item
        findings = sorted(
            unique.values(),
            key=lambda item: (-severity_rank(item.severity), item.rule, item.target),
        )
        summary: dict[str, int] = {}
        for item in findings:
            summary[item.severity.value] = summary.get(item.severity.value, 0) + 1
        penalty = sum(max(1, severity_rank(item.severity) * 2) for item in findings)
        score = max(0.0, 100.0 - penalty)
        passed_rules = tuple(
            rule
            for rule in self.checked_rules
            if not any(item.rule.startswith(rule) for item in findings)
        )
        return AuditReport(
            issues=tuple(findings),
            checked_elements=len(all_nodes),
            passed_rules=passed_rules,
            score=score,
            level=self.level,
            summary=summary,
        )

    def _check_document(
        self,
        nodes: Sequence[ElementNode],
        all_nodes: Sequence[ElementNode],
    ) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        root = nodes[0] if nodes else None
        lang = root.attr("lang") if root is not None else ""
        if not lang:
            issues.append(
                _issue(
                    "document.lang.missing",
                    "Document has no lang attribute",
                    target="document",
                    severity=Severity.SERIOUS,
                    wcag="3.1.1",
                    remediation="Set lang on the root element",
                )
            )
        elif not is_valid_locale(lang):
            issues.append(
                _issue(
                    "document.lang.invalid",
                    f"Document lang '{lang}' is not a valid language tag",
                    target="document",
                    severity=Severity.MODERATE,
                    wcag="3.1.1",
                    remediation="Use a BCP 47 language tag",
                )
            )
        if (
            self.locale != "en"
            and lang
            and normalize_locale(lang).split("-", 1)[0] != self.locale.split("-", 1)[0]
        ):
            issues.append(
                _issue(
                    "document.lang.mismatch",
                    "Document language does not match the active locale",
                    target="document",
                    severity=Severity.MINOR,
                    wcag="3.1.1",
                    remediation="Synchronize document lang with the selected locale",
                )
            )
        if self.require_landmarks:
            roles = {item.role for item in all_nodes}
            tags = {item.normalized_tag for item in all_nodes}
            if "main" not in tags and "main" not in roles:
                issues.append(
                    _issue(
                        "document.landmarks.main",
                        "No main landmark was found",
                        target="document",
                        severity=Severity.MODERATE,
                        wcag="1.3.1",
                        remediation="Wrap primary content in a main element",
                    )
                )
            if not tags & LANDMARK_TAGS and not roles & LANDMARK_ROLES:
                issues.append(
                    _issue(
                        "document.landmarks.none",
                        "No landmarks were found",
                        target="document",
                        severity=Severity.MINOR,
                        wcag="1.3.1",
                        remediation="Add header, nav, main, and footer landmarks",
                    )
                )
        if all_nodes and not has_skip_link(nodes):
            issues.append(
                _issue(
                    "navigation.skip_link",
                    "No skip navigation link was found",
                    target="document",
                    severity=Severity.MINOR,
                    wcag="2.4.1",
                    remediation="Add a skip link before repeated navigation",
                )
            )
        return issues

    def _check_headings(self, nodes: Sequence[ElementNode]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        previous = 0
        seen_first = False
        for node in nodes:
            match = HEADING_RE.match(node.normalized_tag)
            explicit = node.role == "heading"
            level = int(match.group(1)) if match else 0
            if explicit and not level:
                try:
                    level = int(node.attr("aria-level"))
                except ValueError:
                    level = 0
            if not level:
                continue
            if not seen_first and level != 1:
                issues.append(
                    _issue(
                        "heading.order.first",
                        f"First heading is h{level} instead of h1",
                        target=node.path,
                        severity=Severity.MODERATE,
                        wcag="1.3.1",
                        remediation="Start the document with a single h1",
                    )
                )
            if previous and level > previous + 1:
                issues.append(
                    _issue(
                        "heading.order.skipped",
                        f"Heading level jumps from h{previous} to h{level}",
                        target=node.path,
                        severity=Severity.MINOR,
                        wcag="1.3.1",
                        remediation="Do not skip heading levels",
                        details={"previous": previous, "current": level},
                    )
                )
            previous = level
            seen_first = True
            if not node.text.strip() and not node.children:
                issues.append(
                    _issue(
                        "heading.empty",
                        "Heading has no accessible text",
                        target=node.path,
                        severity=Severity.SERIOUS,
                        wcag="2.4.6",
                        remediation="Add descriptive heading text",
                    )
                )
        return issues

    def _check_images(self, nodes: Sequence[ElementNode]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        for node in nodes:
            if node.normalized_tag != "img":
                continue
            if not node.has_attr("alt"):
                issues.append(
                    _issue(
                        "image.alt.missing",
                        "Image has no alt attribute",
                        target=node.path,
                        severity=Severity.SERIOUS,
                        wcag="1.1.1",
                        remediation="Add alt text or alt='' for decorative images",
                    )
                )
            elif node.attr("alt").strip() and len(node.attr("alt").strip()) > 125:
                issues.append(
                    _issue(
                        "image.alt.long",
                        "Image alt text is longer than 125 characters",
                        target=node.path,
                        severity=Severity.MINOR,
                        wcag="1.1.1",
                        remediation="Shorten the alt text and move detail into surrounding text",
                    )
                )
            elif node.attr("alt").lower().startswith(("image of", "picture of", "photo of")):
                issues.append(
                    _issue(
                        "image.alt.redundant",
                        "Image alt text begins with a redundant phrase",
                        target=node.path,
                        severity=Severity.INFO,
                        wcag="1.1.1",
                        remediation="Describe the image content directly",
                    )
                )
        return issues

    def _check_links(self, nodes: Sequence[ElementNode]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        for node in nodes:
            if node.normalized_tag != "a":
                continue
            text = compute_accessible_name(node).strip().lower()
            if not node.attr("href"):
                issues.append(
                    _issue(
                        "link.href.missing",
                        "Anchor has no href and is not keyboard focusable",
                        target=node.path,
                        severity=Severity.SERIOUS,
                        wcag="2.1.1",
                        remediation="Use a button for actions or add an href",
                    )
                )
            if text in GENERIC_LINK_TEXT:
                issues.append(
                    _issue(
                        "link.text.generic",
                        f"Link text '{text}' is not descriptive",
                        target=node.path,
                        severity=Severity.MODERATE,
                        wcag="2.4.4",
                        remediation="Describe the destination in the link text",
                    )
                )
            if node.attr("href", "#") == "#" and node.attr("role") == "button":
                issues.append(
                    _issue(
                        "link.role.button",
                        "Anchor with role=button should be a real button",
                        target=node.path,
                        severity=Severity.MINOR,
                        wcag="4.1.2",
                        remediation="Replace the anchor with a button element",
                    )
                )
            if node.attr("target") == "_blank" and not node.attr("rel"):
                issues.append(
                    _issue(
                        "link.new_window",
                        "Link opens in a new window without warning",
                        target=node.path,
                        severity=Severity.INFO,
                        wcag="3.2.5",
                        remediation="Indicate that the link opens a new window",
                    )
                )
        return issues

    def _check_controls(self, nodes: Sequence[ElementNode]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        for node in nodes:
            tag = node.normalized_tag
            if tag not in INTERACTIVE_TAGS:
                continue
            name = compute_accessible_name(node)
            if not name:
                issues.append(
                    _issue(
                        "control.label.missing",
                        f"{tag} control has no accessible label",
                        target=node.path,
                        severity=Severity.SERIOUS,
                        wcag="4.1.2",
                        remediation="Add visible text, aria-label, or an associated label",
                    )
                )
            is_text_input = tag == "input" and node.attr("type") in {
                "text",
                "email",
                "password",
                "search",
            }
            if is_text_input and not node.has_attr("id") and not node.has_attr("aria-label"):
                issues.append(
                    _issue(
                        "control.label.association",
                        "Text input cannot be associated with a label",
                        target=node.path,
                        severity=Severity.SERIOUS,
                        wcag="1.3.1",
                        remediation="Add an id and a matching label element",
                    )
                )
            if node.has_attr("placeholder") and not name:
                issues.append(
                    _issue(
                        "control.placeholder_only",
                        "Placeholder is used as the only label",
                        target=node.path,
                        severity=Severity.MODERATE,
                        wcag="3.3.2",
                        remediation="Add a persistent visible label",
                    )
                )
            if node.attr("aria-disabled") == "true" and is_focusable(node):
                issues.append(
                    _issue(
                        "control.aria_disabled",
                        "Control is aria-disabled but remains focusable",
                        target=node.path,
                        severity=Severity.INFO,
                        wcag="4.1.2",
                        remediation="Keep the control focusable but explain why it is disabled",
                    )
                )
        return issues

    def _check_tables(self, nodes: Sequence[ElementNode]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        for node in nodes:
            if node.normalized_tag != "table":
                continue
            descendants = node.descendants()
            has_header = any(item.normalized_tag == "th" for item in descendants)
            has_caption = any(item.normalized_tag == "caption" for item in descendants)
            if not has_header:
                issues.append(
                    _issue(
                        "table.header.missing",
                        "Table has no header cells",
                        target=node.path,
                        severity=Severity.MODERATE,
                        wcag="1.3.1",
                        remediation="Add th elements with scope attributes",
                    )
                )
            if not has_caption and not node.has_attr("aria-label"):
                issues.append(
                    _issue(
                        "table.caption.missing",
                        "Table has no caption or accessible name",
                        target=node.path,
                        severity=Severity.MINOR,
                        wcag="1.3.1",
                        remediation="Add a caption describing the table",
                    )
                )
        return issues

    def _check_motion(self, nodes: Sequence[ElementNode]) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        for node in nodes:
            style = node.attr("style").lower()
            if "animation" in style and "prefers-reduced-motion" not in style:
                issues.append(
                    _issue(
                        "motion.inline_animation",
                        "Inline animation has no reduced-motion fallback",
                        target=node.path,
                        severity=Severity.MINOR,
                        wcag="2.3.3",
                        remediation="Move animation into CSS with a prefers-reduced-motion guard",
                    )
                )
            if node.attr("data-reduce-motion") == "false":
                issues.append(
                    _issue(
                        "motion.override",
                        "Element explicitly disables reduced-motion handling",
                        target=node.path,
                        severity=Severity.MODERATE,
                        wcag="2.3.3",
                        remediation="Respect the user's reduced-motion preference",
                    )
                )
        return issues

    def _check_theme(self, theme: ThemeDefinition) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        for name in missing_tokens(theme):
            issues.append(
                _issue(
                    "theme.token.missing",
                    f"Theme {theme.name} is missing token {name}",
                    target=theme.name,
                    severity=Severity.MODERATE,
                    wcag="1.4.3",
                    remediation=f"Define the {name} token",
                )
            )
        pairs = palette_pairs(theme.tokens)
        for pair in pairs:
            if not pair.passed:
                issues.append(
                    _issue(
                        "theme.contrast",
                        f"{pair.name} contrast is {pair.ratio:.2f}, below {pair.required}",
                        target=theme.name,
                        severity=Severity.SERIOUS if pair.ratio < 3.0 else Severity.MODERATE,
                        wcag="1.4.3",
                        remediation="Adjust foreground or background color",
                        details={"pair": pair.name, "ratio": round(pair.ratio, 2)},
                    )
                )
        return issues

    def _check_palette(self, palette: Mapping[str, str]) -> list[AuditIssue]:
        report = build_report(
            {
                name: {"foreground": value, "background": "#ffffff"}
                for name, value in palette.items()
            }
        )
        return [
            _issue(
                "palette.contrast",
                f"{pair.name} contrast is {pair.ratio:.2f}, below {pair.required}",
                target=pair.name,
                severity=Severity.SERIOUS if pair.ratio < 3.0 else Severity.MODERATE,
                wcag="1.4.3",
                remediation="Choose a color with higher contrast",
            )
            for pair in report.failures
        ]


def audit_payload(
    payload: Mapping[str, Any],
    *,
    locale: str = "en",
    level: str = "AA",
) -> AuditReport:
    """Audit a payload containing nodes and optional theme or palette data."""
    nodes = nodes_from_payload(payload.get("nodes") or [])
    auditor = AccessibilityAuditor(locale=locale, level=WcagLevel(level.upper()))
    theme_payload = payload.get("theme")
    theme = None
    if isinstance(theme_payload, Mapping):
        from redscribe.v2.a11y.themes import theme_from_payload

        theme = theme_from_payload(theme_payload)
    palette_payload = payload.get("palette")
    palette = None
    if isinstance(palette_payload, Mapping):
        palette = {str(key): str(value) for key, value in palette_payload.items()}
    return auditor.audit(nodes, theme=theme, palette=palette)


def audit_summary(report: AuditReport) -> dict[str, Any]:
    """Return a compact summary of an audit report."""
    return {
        "score": round(report.score, 1),
        "passed": report.passed,
        "issues": len(report.issues),
        "critical": len(report.issues_for(Severity.CRITICAL)),
        "serious": len(report.issues_for(Severity.SERIOUS)),
        "elements": report.checked_elements,
        "level": report.level.value,
    }
