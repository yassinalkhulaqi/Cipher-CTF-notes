"""ARIA role metadata, accessible-name computation, and ARIA validation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v2.a11y.models import (
    AriaIssue,
    AriaReport,
    ElementNode,
    Severity,
)

ID_REFERENCE_RE = re.compile(r"[A-Za-z][\w:.-]*")

GLOBAL_ARIA_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "aria-atomic",
        "aria-busy",
        "aria-controls",
        "aria-current",
        "aria-describedby",
        "aria-description",
        "aria-details",
        "aria-disabled",
        "aria-dropeffect",
        "aria-errormessage",
        "aria-flowto",
        "aria-grabbed",
        "aria-haspopup",
        "aria-hidden",
        "aria-invalid",
        "aria-keyshortcuts",
        "aria-label",
        "aria-labelledby",
        "aria-live",
        "aria-owns",
        "aria-relevant",
        "aria-roledescription",
    }
)


@dataclass(frozen=True, slots=True)
class RoleSpec:
    """Metadata describing one ARIA role."""

    name: str
    category: str
    properties: frozenset[str] = field(default_factory=frozenset)
    required_properties: frozenset[str] = field(default_factory=frozenset)
    required_context: frozenset[str] = field(default_factory=frozenset)
    name_from_content: bool = True
    abstract: bool = False
    focusable: bool = False
    description: str = ""

    def allows(self, attribute: str) -> bool:
        return attribute in self.properties or attribute in GLOBAL_ARIA_ATTRIBUTES

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "properties": sorted(self.properties),
            "required_properties": sorted(self.required_properties),
            "required_context": sorted(self.required_context),
            "name_from_content": self.name_from_content,
            "abstract": self.abstract,
            "focusable": self.focusable,
            "description": self.description,
        }


def _role(
    name: str,
    category: str,
    properties: str = "",
    required: str = "",
    context: str = "",
    *,
    name_from_content: bool = True,
    abstract: bool = False,
    focusable: bool = False,
    description: str = "",
) -> RoleSpec:
    return RoleSpec(
        name=name,
        category=category,
        properties=frozenset(part for part in properties.split() if part),
        required_properties=frozenset(part for part in required.split() if part),
        required_context=frozenset(part for part in context.split() if part),
        name_from_content=name_from_content,
        abstract=abstract,
        focusable=focusable,
        description=description,
    )


ROLE_REGISTRY: dict[str, RoleSpec] = {
    spec.name: spec
    for spec in (
        _role("alert", "status", focusable=False, description="Important time-sensitive message"),
        _role("alertdialog", "dialog", focusable=True, description="Modal warning dialog"),
        _role("application", "structure", description="Application-specific keyboard model"),
        _role("article", "structure", description="Independent content composition"),
        _role("banner", "landmark", description="Site-wide header landmark"),
        _role(
            "button",
            "widget",
            "aria-pressed aria-expanded aria-haspopup",
            focusable=True,
            description="Clickable action",
        ),
        _role("cell", "structure", "aria-colindex aria-rowindex"),
        _role(
            "checkbox",
            "widget",
            "aria-checked aria-required",
            required="aria-checked",
            focusable=True,
        ),
        _role("columnheader", "structure", "aria-sort", focusable=True),
        _role(
            "combobox",
            "widget",
            "aria-expanded aria-autocomplete aria-controls",
            required="aria-expanded aria-controls",
            focusable=True,
        ),
        _role("complementary", "landmark", description="Supporting content landmark"),
        _role("contentinfo", "landmark", description="Site-wide footer landmark"),
        _role("definition", "structure"),
        _role(
            "dialog",
            "window",
            "aria-modal",
            focusable=True,
            description="Modal or non-modal dialog",
        ),
        _role("directory", "structure"),
        _role("document", "structure"),
        _role("feed", "structure"),
        _role("figure", "structure"),
        _role("form", "landmark"),
        _role("grid", "composite", "aria-rowcount aria-colcount", focusable=True),
        _role("gridcell", "widget", "aria-selected aria-readonly", focusable=True),
        _role("group", "structure"),
        _role(
            "heading",
            "structure",
            "aria-level",
            required="aria-level",
            description="Section heading with required level",
        ),
        _role(
            "img",
            "widget",
            name_from_content=False,
            description="Graphic requiring an accessible name",
        ),
        _role("link", "widget", "aria-current", focusable=True),
        _role("list", "structure"),
        _role("listbox", "composite", "aria-multiselectable", focusable=True),
        _role("listitem", "structure", context="list"),
        _role("log", "status"),
        _role("main", "landmark", description="Primary content landmark"),
        _role("marquee", "status"),
        _role("math", "structure"),
        _role("menu", "composite", focusable=True),
        _role("menubar", "composite", focusable=True),
        _role("menuitem", "widget", "aria-disabled", focusable=True),
        _role(
            "menuitemcheckbox", "widget", "aria-checked", required="aria-checked", focusable=True
        ),
        _role("menuitemradio", "widget", "aria-checked", required="aria-checked", focusable=True),
        _role("navigation", "landmark", description="Navigation landmark"),
        _role("none", "presentation", abstract=False),
        _role("note", "structure"),
        _role("option", "widget", "aria-selected", required="aria-selected", focusable=True),
        _role("presentation", "presentation"),
        _role("progressbar", "widget", "aria-valuenow aria-valuemin aria-valuemax"),
        _role("radio", "widget", "aria-checked", required="aria-checked", focusable=True),
        _role("radiogroup", "composite", required="", focusable=True),
        _role("region", "landmark"),
        _role("row", "structure", "aria-rowindex"),
        _role("rowgroup", "structure"),
        _role("rowheader", "structure", "aria-sort", focusable=True),
        _role(
            "scrollbar",
            "widget",
            "aria-valuenow aria-controls",
            required="aria-valuenow",
            focusable=True,
        ),
        _role("search", "landmark"),
        _role("searchbox", "widget", "aria-autocomplete", focusable=True),
        _role("separator", "structure", "aria-orientation"),
        _role(
            "slider",
            "widget",
            "aria-valuenow aria-valuemin aria-valuemax",
            required="aria-valuenow",
            focusable=True,
        ),
        _role(
            "spinbutton",
            "widget",
            "aria-valuenow aria-valuenow",
            required="aria-valuenow",
            focusable=True,
        ),
        _role("status", "status"),
        _role("switch", "widget", "aria-checked", required="aria-checked", focusable=True),
        _role("tab", "widget", "aria-selected", required="aria-selected", focusable=True),
        _role("table", "structure", "aria-colcount aria-rowcount"),
        _role("tablist", "composite", focusable=True),
        _role("tabpanel", "structure"),
        _role("term", "structure"),
        _role("textbox", "widget", "aria-multiline aria-autocomplete", focusable=True),
        _role("timer", "status"),
        _role("toolbar", "composite", focusable=True),
        _role("tooltip", "status"),
        _role("tree", "composite", focusable=True),
        _role("treegrid", "composite", focusable=True),
        _role("treeitem", "widget", "aria-expanded aria-selected", focusable=True),
    )
}

DEPRECATED_ROLES: frozenset[str] = frozenset({"directory", "marquee"})
INTERACTIVE_TAGS: frozenset[str] = frozenset(
    {"button", "input", "select", "textarea", "a", "summary"}
)
VOID_TEXT_TAGS: frozenset[str] = frozenset({"img", "input", "br", "hr", "meta", "link"})


def known_roles() -> tuple[str, ...]:
    """Return all registered ARIA role names."""
    return tuple(sorted(ROLE_REGISTRY))


def role_spec(role: str) -> RoleSpec | None:
    """Look up a role specification."""
    return ROLE_REGISTRY.get(role.strip().lower())


def _text_of(node: ElementNode) -> str:
    pieces = [node.text.strip()]
    for child in node.children:
        pieces.append(_text_of(child))
    return " ".join(piece for piece in pieces if piece)


def _reference_texts(reference: str, lookup: Mapping[str, str]) -> list[str]:
    result: list[str] = []
    for token in ID_REFERENCE_RE.findall(reference):
        value = lookup.get(token)
        if value:
            result.append(value)
    return result


def compute_accessible_name(
    node: ElementNode,
    *,
    name_lookup: Mapping[str, str] | None = None,
    allow_content: bool = True,
) -> str:
    """Compute a practical accessible name for an element."""
    lookup = name_lookup or {}
    labelledby = node.attr("aria-labelledby")
    if labelledby:
        referenced = _reference_texts(labelledby, lookup)
        if referenced:
            return " ".join(referenced).strip()
    label = node.attr("aria-label").strip()
    if label:
        return label
    if node.normalized_tag == "input":
        label_by = node.attr("aria-labelledby")
        if label_by and label_by in lookup:
            return lookup[label_by]
        title = node.attr("title").strip()
        if title:
            return title
        placeholder = node.attr("placeholder").strip()
        if placeholder:
            return placeholder
        return ""
    title = node.attr("title").strip()
    if allow_content:
        content = _text_of(node)
        if content:
            return content
    return title


def _collect_id_names(nodes: Sequence[ElementNode]) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in nodes:
        element_id = node.element_id
        if element_id:
            result[element_id] = compute_accessible_name(node) or _text_of(node)
        result.update(_collect_id_names(node.children))
    return result


def _ancestor_roles(nodes: Sequence[ElementNode], target: ElementNode) -> list[str]:
    for node in nodes:
        if node is target:
            return []
        found = _ancestor_roles(node.children, target)
        if found is not None:
            return [node.role, *found]
    return []


def validate_tree(
    nodes: Sequence[ElementNode],
    *,
    strict: bool = True,
) -> AriaReport:
    """Validate ARIA usage in a tree of simplified elements."""
    issues: list[AriaIssue] = []
    roles: list[str] = []
    names: dict[str, str] = {}
    all_nodes: list[ElementNode] = []
    for node in nodes:
        all_nodes.append(node)
        all_nodes.extend(node.descendants())
    lookup = _collect_id_names(all_nodes)

    for node in all_nodes:
        target = node.path or node.attr("aria-label") or node.normalized_tag
        role = node.role
        if role:
            roles.append(role)
            spec = role_spec(role)
            if spec is None:
                issues.append(
                    AriaIssue(
                        "aria-unknown-role",
                        f"Unknown ARIA role '{role}'",
                        target,
                        Severity.SERIOUS if strict else Severity.MINOR,
                        "Use a role from the WAI-ARIA specification",
                    )
                )
            else:
                if role in DEPRECATED_ROLES:
                    issues.append(
                        AriaIssue(
                            "aria-deprecated-role",
                            f"Role '{role}' is deprecated",
                            target,
                            Severity.INFO,
                            "Prefer a semantic HTML element or a current role",
                        )
                    )
                if spec.abstract:
                    issues.append(
                        AriaIssue(
                            "aria-abstract-role",
                            f"Abstract role '{role}' cannot be used directly",
                            target,
                            Severity.SERIOUS,
                            "Choose a concrete child role",
                        )
                    )
                for required in sorted(spec.required_properties):
                    if not node.has_attr(required):
                        issues.append(
                            AriaIssue(
                                "aria-missing-property",
                                f"Role '{role}' requires {required}",
                                target,
                                Severity.MODERATE,
                                f"Add {required} with a valid value",
                            )
                        )
                for attribute in sorted(node.attrs):
                    if not attribute.startswith("aria-"):
                        continue
                    if attribute in GLOBAL_ARIA_ATTRIBUTES or spec.allows(attribute):
                        continue
                    issues.append(
                        AriaIssue(
                            "aria-invalid-property",
                            f"{attribute} is not allowed on role '{role}'",
                            target,
                            Severity.MINOR,
                            "Remove the attribute or choose a compatible role",
                        )
                    )
                if spec.required_context:
                    ancestors = set(_ancestor_roles(nodes, node))
                    if ancestors and not ancestors & spec.required_context:
                        issues.append(
                            AriaIssue(
                                "aria-invalid-context",
                                f"Role '{role}' requires a "
                                f"{sorted(spec.required_context)[0]} ancestor",
                                target,
                                Severity.MODERATE,
                                "Wrap the element in the required owner role",
                            )
                        )

        for attribute in ("aria-labelledby", "aria-describedby", "aria-controls", "aria-owns"):
            value = node.attr(attribute)
            for token in ID_REFERENCE_RE.findall(value):
                if token not in lookup:
                    issues.append(
                        AriaIssue(
                            "aria-missing-reference",
                            f"{attribute} references missing id '{token}'",
                            target,
                            Severity.SERIOUS,
                            "Add a matching id to the referenced element",
                        )
                    )

        hidden_spec = role_spec(role) if role else None
        hidden_focusable = hidden_spec is not None and hidden_spec.focusable
        if node.attr("aria-hidden") == "true" and (
            node.normalized_tag in INTERACTIVE_TAGS or hidden_focusable
        ):
            issues.append(
                AriaIssue(
                    "aria-hidden-focusable",
                    "Focusable element is hidden from assistive technology",
                    target,
                    Severity.CRITICAL,
                    "Remove aria-hidden or make the element non-focusable",
                )
            )

        if role in {"img", "button", "link", "checkbox", "switch", "textbox"} or (
            node.normalized_tag in {"img", "button", "a"}
        ):
            name = compute_accessible_name(node, name_lookup=lookup)
            names[target] = name
            if (not name and node.normalized_tag != "a") or (
                not name and node.normalized_tag == "a" and not node.descendants()
            ):
                issues.append(
                    AriaIssue(
                        "aria-missing-name",
                        "Interactive element has no accessible name",
                        target,
                        Severity.SERIOUS,
                        "Add visible text, aria-label, or aria-labelledby",
                    )
                )

        if node.normalized_tag == "img" and not node.has_attr("alt"):
            issues.append(
                AriaIssue(
                    "aria-missing-alt",
                    "Image is missing an alt attribute",
                    target,
                    Severity.SERIOUS,
                    "Add descriptive alt text or alt='' for decorative images",
                )
            )

        if role == "heading":
            level = node.attr("aria-level")
            try:
                number = int(level)
            except ValueError:
                number = -1
            if number < 1 or number > 6:
                issues.append(
                    AriaIssue(
                        "aria-invalid-level",
                        "Heading aria-level must be an integer from 1 to 6",
                        target,
                        Severity.MODERATE,
                        "Set aria-level to a value between 1 and 6",
                    )
                )

        for attribute, value in node.attrs.items():
            if (
                attribute.startswith("aria-")
                and attribute.endswith(("now", "min", "max"))
                and value
            ):
                try:
                    float(value)
                except ValueError:
                    issues.append(
                        AriaIssue(
                            "aria-invalid-number",
                            f"{attribute} must be numeric",
                            target,
                            Severity.MODERATE,
                            "Provide a numeric value",
                        )
                    )

    return AriaReport(
        issues=tuple(issues),
        roles_seen=tuple(dict.fromkeys(roles)),
        accessible_names=names,
        checked=len(all_nodes),
    )


def validate_attribute(attribute: str, value: str, *, role: str = "") -> list[str]:
    """Validate a single ARIA attribute value."""
    problems: list[str] = []
    if attribute not in GLOBAL_ARIA_ATTRIBUTES:
        spec = role_spec(role)
        if spec is None or not spec.allows(attribute):
            problems.append(f"{attribute} is not valid for role '{role}'")
    if attribute in {
        "aria-hidden",
        "aria-disabled",
        "aria-busy",
        "aria-selected",
        "aria-checked",
        "aria-expanded",
        "aria-invalid",
        "aria-modal",
    } and value not in {"true", "false"}:
        problems.append(f"{attribute} must be 'true' or 'false'")
    if attribute == "aria-live" and value not in {"off", "polite", "assertive"}:
        problems.append("aria-live must be off, polite, or assertive")
    if attribute == "aria-level":
        try:
            number = int(value)
        except ValueError:
            problems.append("aria-level must be numeric")
        else:
            if number < 1:
                problems.append("aria-level must be at least 1")
    if attribute == "aria-orientation" and value not in {"horizontal", "vertical", "undefined"}:
        problems.append("aria-orientation has an invalid value")
    if attribute in {"aria-valuemin", "aria-valuemax", "aria-valuenow"} and value:
        try:
            float(value)
        except ValueError:
            problems.append(f"{attribute} must be numeric")
    return problems


def role_summary() -> dict[str, Any]:
    """Return a compact summary of the ARIA role registry."""
    categories: dict[str, int] = {}
    for spec in ROLE_REGISTRY.values():
        categories[spec.category] = categories.get(spec.category, 0) + 1
    return {
        "roles": len(ROLE_REGISTRY),
        "categories": dict(sorted(categories.items())),
        "global_attributes": sorted(GLOBAL_ARIA_ATTRIBUTES),
        "deprecated_roles": sorted(DEPRECATED_ROLES),
    }


def accessible_name_map(nodes: Sequence[ElementNode]) -> dict[str, str]:
    """Build an id-to-accessible-name map for a set of element trees."""
    result: dict[str, str] = {}
    for node in nodes:
        result.update(_collect_id_names([node]))
    return result
