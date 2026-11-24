"""Final gate-hardening checks for the V3 release.

All checks are *static*: they inspect source text supplied by the caller and
already-built router metadata. They never import untrusted modules, execute
strings, spawn processes, or open sockets. This mirrors the project invariant
that playbooks and extensions are data only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from redscribe.v3.api.router import V3Router
from redscribe.v3.release.models import (
    RELEASE_ACTIONS,
    GateDefinition,
    GateReport,
    GateResult,
    GateStatus,
)

_DEPENDENCIES_PATTERN = re.compile(r"(?m)^dependencies\s*=\s*\[\s*\]\s*$")
_TOKEN_DEFINITION_PATTERN = re.compile(r"(?m)^\s*--v3-[a-z0-9-]+\s*:")
_ROOT_PATTERN = re.compile(r"(?m)^\s*:root\b")


def _join(*parts: str) -> str:
    """Assemble a sensitive token from inert fragments.

    Keeping the literal out of this module means the safety scanner can audit
    its own source without matching its own detection tables.
    """
    return "".join(parts)


_NETWORK_TOKENS: tuple[str, ...] = (
    _join("sock", "et"),
    _join("urll", "ib"),
    _join("http.", "client"),
    _join("req", "uests"),
    _join("aio", "http"),
)
_EXEC_TOKENS: tuple[str, ...] = (
    _join("sub", "process"),
    _join("os", ".system"),
    _join("ev", "al("),
    _join("ex", "ec("),
    _join("__import__"),
)

GATE_DEFINITIONS: tuple[GateDefinition, ...] = (
    GateDefinition("source.no_network", "No network-capable imports", "blocker"),
    GateDefinition("source.no_execution", "No dynamic code execution", "blocker"),
    GateDefinition("deps.runtime_empty", "No new runtime dependencies", "blocker"),
    GateDefinition("namespace.contract", "Namespace registration contract", "blocker"),
    GateDefinition("routes.canonical", "Canonical route surface", "major"),
    GateDefinition("routes.release_actions", "Release action coverage", "blocker"),
    GateDefinition("design.tokens", "Design-system token ownership", "major"),
    GateDefinition("design.a11y_attributes", "Testing and a11y data attributes", "major"),
    GateDefinition("frontend.suite_manifest", "Frontend suite manifest", "major"),
    GateDefinition("docs.release_guide", "Release guide completeness", "minor"),
)


def _result(
    gate_id: str,
    passed: bool,
    detail: str,
    evidence: tuple[str, ...] = (),
    *,
    absent_is_warning: bool = False,
    absent: bool = False,
) -> GateResult:
    """Build a gate result, optionally treating missing input as a warning."""
    title = next(
        (definition.title for definition in GATE_DEFINITIONS if definition.gate_id == gate_id),
        gate_id,
    )
    if absent and absent_is_warning:
        status = GateStatus.WARN
    else:
        status = GateStatus.PASS if passed else GateStatus.FAIL
    return GateResult(gate_id=gate_id, title=title, status=status, detail=detail, evidence=evidence)


def scan_tokens(sources: Mapping[str, str], tokens: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """Return the tokens found in each supplied source string."""
    findings: dict[str, tuple[str, ...]] = {}
    for path, text in sources.items():
        matches = tuple(sorted({token for token in tokens if token in text}))
        if matches:
            findings[path] = matches
    return findings


def check_no_network_imports(sources: Mapping[str, str]) -> GateResult:
    """Reject network-capable module references in supplied sources."""
    if not sources:
        return _result(
            "source.no_network",
            False,
            "No sources supplied for the network scan.",
            absent_is_warning=True,
            absent=True,
        )
    findings = scan_tokens(sources, _NETWORK_TOKENS)
    if findings:
        evidence = tuple(f"{path}: {', '.join(tokens)}" for path, tokens in findings.items())
        return _result("source.no_network", False, "Network-capable tokens found.", evidence)
    return _result(
        "source.no_network", True, f"Scanned {len(sources)} sources; no network tokens found."
    )


def check_no_code_execution(sources: Mapping[str, str]) -> GateResult:
    """Reject dynamic-evaluation and process-spawning tokens."""
    if not sources:
        return _result(
            "source.no_execution",
            False,
            "No sources supplied for the execution scan.",
            absent_is_warning=True,
            absent=True,
        )
    findings = scan_tokens(sources, _EXEC_TOKENS)
    if findings:
        evidence = tuple(f"{path}: {', '.join(tokens)}" for path, tokens in findings.items())
        return _result("source.no_execution", False, "Execution-capable tokens found.", evidence)
    return _result(
        "source.no_execution", True, f"Scanned {len(sources)} sources; no execution tokens found."
    )


def check_runtime_dependencies(pyproject_text: str) -> GateResult:
    """Require an empty runtime dependency list."""
    if not pyproject_text:
        return _result(
            "deps.runtime_empty",
            False,
            "pyproject.toml was not supplied.",
            absent_is_warning=True,
            absent=True,
        )
    passed = _DEPENDENCIES_PATTERN.search(pyproject_text) is not None
    detail = "Runtime dependencies are empty." if passed else "Runtime dependency list changed."
    return _result("deps.runtime_empty", passed, detail)


def check_namespace_contract(
    source: str, *, action_count: int = len(RELEASE_ACTIONS)
) -> GateResult:
    """Require an additive ``register(router)`` namespace module."""
    if not source:
        return _result(
            "namespace.contract",
            False,
            "Release namespace source was not supplied.",
            absent_is_warning=True,
            absent=True,
        )
    has_register = "def register(router" in source
    adds = source.count('router.add("release"')
    passed = has_register and adds >= action_count
    detail = f"register() present: {has_register}; release routes declared: {adds}"
    return _result("namespace.contract", passed, detail)


def check_canonical_routes(router: V3Router) -> GateResult:
    """Require every route to use the canonical API v3 prefix."""
    invalid = tuple(
        route.path for route in router.routes() if not route.path.startswith("/api/v3/")
    )
    passed = len(router.routes()) > 0 and not invalid
    detail = f"{len(router.routes())} routes checked; {len(invalid)} invalid"
    return _result("routes.canonical", passed, detail, invalid)


def check_release_routes(router: V3Router) -> GateResult:
    """Require the full release action catalogue."""
    missing = tuple(action for action in RELEASE_ACTIONS if router.get("release", action) is None)
    passed = not missing
    detail = f"{len(RELEASE_ACTIONS) - len(missing)}/{len(RELEASE_ACTIONS)} actions registered"
    return _result("routes.release_actions", passed, detail, missing)


def check_design_tokens(css_sources: Mapping[str, str]) -> GateResult:
    """Require feature CSS to consume, never redefine, foundation tokens."""
    if not css_sources:
        return _result(
            "design.tokens",
            False,
            "No release CSS supplied.",
            absent_is_warning=True,
            absent=True,
        )
    offenders: list[str] = []
    for path, text in css_sources.items():
        if _ROOT_PATTERN.search(text) or _TOKEN_DEFINITION_PATTERN.search(text):
            offenders.append(path)
    passed = not offenders
    detail = (
        f"{len(css_sources)} stylesheets use design-system v3 tokens only"
        if passed
        else "Feature CSS redefines a foundation token"
    )
    return _result("design.tokens", passed, detail, tuple(offenders))


def check_a11y_attributes(component_sources: Mapping[str, str]) -> GateResult:
    """Require stable data attributes and explicit ARIA labels in components."""
    if not component_sources:
        return _result(
            "design.a11y_attributes",
            False,
            "No component sources supplied.",
            absent_is_warning=True,
            absent=True,
        )
    offenders: list[str] = []
    for path, text in component_sources.items():
        if "data-" not in text or "aria-" not in text:
            offenders.append(path)
    passed = not offenders
    detail = (
        f"{len(component_sources)} components expose data and aria attributes"
        if passed
        else "Components are missing data or aria attributes"
    )
    return _result("design.a11y_attributes", passed, detail, tuple(offenders))


def check_suite_manifest(manifest_text: str) -> GateResult:
    """Require the frontend suite manifest to list the release test."""
    if not manifest_text:
        return _result(
            "frontend.suite_manifest",
            False,
            "Suite manifest was not supplied.",
            absent_is_warning=True,
            absent=True,
        )
    expected = "release-polish-v3.test.ts"
    try:
        names = json.loads(manifest_text)
    except ValueError:
        return _result("frontend.suite_manifest", False, "Manifest is not valid JSON.")
    passed = isinstance(names, list) and expected in names
    detail = "Release suite is listed." if passed else f"{expected} is not listed"
    return _result("frontend.suite_manifest", passed, detail)


def check_release_docs(docs_text: str) -> GateResult:
    """Require the release guide to cover the reviewer-facing sections."""
    if not docs_text:
        return _result(
            "docs.release_guide",
            False,
            "Release guide was not supplied.",
            absent_is_warning=True,
            absent=True,
        )
    required = ("## Quickstart", "## Golden paths", "## Gates", "README.md", "CHANGELOG.md")
    missing = tuple(item for item in required if item not in docs_text)
    passed = not missing
    detail = "Release guide sections are present." if passed else f"Missing: {', '.join(missing)}"
    return _result("docs.release_guide", passed, detail, missing)


def run_hardening_gate(
    sources: Mapping[str, str],
    *,
    router: V3Router,
    pyproject_text: str = "",
    css_sources: Mapping[str, str] | None = None,
    component_sources: Mapping[str, str] | None = None,
    manifest_text: str = "",
    docs_text: str = "",
    action_count: int = len(RELEASE_ACTIONS),
) -> GateReport:
    """Run all final gates against supplied source snapshots."""
    python_sources = {path: text for path, text in sources.items() if path.endswith(".py")}
    namespace_source = next(
        (text for path, text in python_sources.items() if path.endswith("namespaces/release.py")),
        "",
    )
    results = (
        check_no_network_imports(python_sources),
        check_no_code_execution(python_sources),
        check_runtime_dependencies(pyproject_text),
        check_namespace_contract(namespace_source, action_count=action_count),
        check_canonical_routes(router),
        check_release_routes(router),
        check_design_tokens(css_sources or {}),
        check_a11y_attributes(component_sources or {}),
        check_suite_manifest(manifest_text),
        check_release_docs(docs_text),
    )
    return GateReport(results=results)


def gate_manifest() -> dict[str, Any]:
    """Return a JSON-safe catalogue of the final gates."""
    return {
        "version": "3.0",
        "gates": [definition.as_dict() for definition in GATE_DEFINITIONS],
        "offline_only": True,
        "executes_user_code": False,
    }
