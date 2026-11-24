"""Tests for final release gate hardening."""

from __future__ import annotations

import json

from redscribe.v3.api.router import V3Router, register_system_routes
from redscribe.v3.release.gates import (
    GATE_DEFINITIONS,
    check_a11y_attributes,
    check_canonical_routes,
    check_design_tokens,
    check_namespace_contract,
    check_no_code_execution,
    check_no_network_imports,
    check_release_docs,
    check_release_routes,
    check_runtime_dependencies,
    check_suite_manifest,
    gate_manifest,
    run_hardening_gate,
    scan_tokens,
)
from redscribe.v3.release.models import RELEASE_ACTIONS, GateStatus

NAMESPACE_SOURCE = "def register(router):\n" + "\n".join(
    f'    router.add("release", "{action}", handler)' for action in RELEASE_ACTIONS
)

CSS_SOURCE = """
.release-panel {
  color: var(--v3-text);
  padding: var(--v3-space-3);
}
"""

TSX_SOURCE = """
export function Panel() {
  return <section data-surface="release" aria-label="Release panel" />;
}
"""


def test_gate_definitions_are_unique() -> None:
    ids = [definition.gate_id for definition in GATE_DEFINITIONS]
    assert len(ids) == len(set(ids))
    assert len(ids) == 10
    assert all(definition.title for definition in GATE_DEFINITIONS)


def test_gate_manifest_is_offline() -> None:
    manifest = gate_manifest()
    assert manifest["offline_only"] is True
    assert manifest["executes_user_code"] is False
    assert len(manifest["gates"]) == len(GATE_DEFINITIONS)


def test_scan_tokens_finds_sensitive_strings() -> None:
    findings = scan_tokens(
        {"module.py": "import socket\nimport json\n"},
        ("socket", "subprocess"),
    )
    assert findings == {"module.py": ("socket",)}


def test_no_network_imports_passes_clean_source() -> None:
    result = check_no_network_imports({"app.py": "import json\nfrom pathlib import Path\n"})
    assert result.status is GateStatus.PASS
    assert "Scanned 1 sources" in result.detail


def test_no_network_imports_flags_forbidden_module() -> None:
    result = check_no_network_imports({"app.py": "import urllib\n"})
    assert result.status is GateStatus.FAIL
    assert "app.py" in result.evidence[0]


def test_no_network_imports_without_sources_is_warning() -> None:
    assert check_no_network_imports({}).status is GateStatus.WARN


def test_no_code_execution_flags_dynamic_calls() -> None:
    result = check_no_code_execution({"app.py": "value = eval(text)\n"})
    assert result.status is GateStatus.FAIL


def test_no_code_execution_passes_normal_source() -> None:
    result = check_no_code_execution({"app.py": "value = compute(text)\n"})
    assert result.status is GateStatus.PASS


def test_runtime_dependencies_gate() -> None:
    assert check_runtime_dependencies("[project]\ndependencies = []\n").status is GateStatus.PASS
    fail = check_runtime_dependencies("[project]\ndependencies = ['requests']\n")
    assert fail.status is GateStatus.FAIL
    assert check_runtime_dependencies("").status is GateStatus.WARN


def test_namespace_contract_gate() -> None:
    assert check_namespace_contract(NAMESPACE_SOURCE, action_count=2).status is GateStatus.PASS
    assert check_namespace_contract(NAMESPACE_SOURCE, action_count=20).status is GateStatus.FAIL
    assert check_namespace_contract("print('hi')").status is GateStatus.FAIL
    assert check_namespace_contract("").status is GateStatus.WARN


def test_canonical_routes_gate() -> None:
    router = V3Router()
    register_system_routes(router)
    assert check_canonical_routes(router).status is GateStatus.PASS
    empty = check_canonical_routes(V3Router())
    assert empty.status is GateStatus.FAIL


def test_release_routes_gate() -> None:
    router = V3Router()
    register_system_routes(router)
    assert check_release_routes(router).status is GateStatus.FAIL
    from redscribe.v3.namespaces.release import register

    register(router)
    assert check_release_routes(router).status is GateStatus.PASS


def test_design_tokens_gate() -> None:
    assert check_design_tokens({"release.css": CSS_SOURCE}).status is GateStatus.PASS
    bad = ":root { --v3-space-3: 10px; }\n"
    assert check_design_tokens({"release.css": bad}).status is GateStatus.FAIL
    assert check_design_tokens({}).status is GateStatus.WARN


def test_a11y_attributes_gate() -> None:
    assert check_a11y_attributes({"Panel.tsx": TSX_SOURCE}).status is GateStatus.PASS
    assert check_a11y_attributes({"Panel.tsx": "<div />"}).status is GateStatus.FAIL
    assert check_a11y_attributes({}).status is GateStatus.WARN


def test_suite_manifest_gate() -> None:
    manifest = json.dumps(["release-polish-v3.test.ts", "other.test.ts"])
    assert check_suite_manifest(manifest).status is GateStatus.PASS
    assert check_suite_manifest("[]").status is GateStatus.FAIL
    assert check_suite_manifest("not-json").status is GateStatus.FAIL
    assert check_suite_manifest("").status is GateStatus.WARN


def test_release_docs_gate() -> None:
    good = "## Quickstart\n## Golden paths\n## Gates\nREADME.md\nCHANGELOG.md\n"
    assert check_release_docs(good).status is GateStatus.PASS
    assert check_release_docs("## Quickstart").status is GateStatus.FAIL
    assert check_release_docs("").status is GateStatus.WARN


def test_full_hardening_gate_is_clean_with_good_inputs() -> None:
    router = V3Router()
    register_system_routes(router)
    from redscribe.v3.namespaces.release import register

    register(router)
    docs = "## Quickstart\n## Golden paths\n## Gates\nREADME.md\nCHANGELOG.md\n"
    report = run_hardening_gate(
        {"src/redscribe/v3/namespaces/release.py": NAMESPACE_SOURCE},
        router=router,
        pyproject_text="[project]\ndependencies = []\n",
        css_sources={"release.css": CSS_SOURCE},
        component_sources={"Panel.tsx": TSX_SOURCE},
        manifest_text=json.dumps(["release-polish-v3.test.ts"]),
        docs_text=docs,
    )
    assert report.ok is True
    assert len(report.results) == len(GATE_DEFINITIONS)
    assert all(result.status is GateStatus.PASS for result in report.results)
    assert "| Gate | Status | Detail |" in report.markdown()


def test_hardening_gate_reports_failures() -> None:
    router = V3Router()
    register_system_routes(router)
    report = run_hardening_gate(
        {"bad.py": "import socket\n"},
        router=router,
        pyproject_text="dependencies = ['x']",
    )
    assert report.ok is False
    assert len(report.failures) >= 2
