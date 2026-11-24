"""Documentation generation helpers for the V3 release.

Generators are pure string builders: they take already-computed reports and
emit Markdown. The release guide carries the *proposed* README and CHANGELOG
content in fenced blocks so no shared file is edited by this branch.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from redscribe.v3.api.router import V3Router, register_system_routes
from redscribe.v3.capabilities import ALL_CAPABILITIES
from redscribe.v3.config import default_config
from redscribe.v3.entities.registry import default_registry
from redscribe.v3.release.changelog import (
    build_migration_notes,
    build_release_changelog,
    build_release_note,
)
from redscribe.v3.release.content import (
    ANIMATION_AUDITS,
    BREAKPOINTS,
    ONBOARDING_SPECS,
    POLISH_CHECKS,
)
from redscribe.v3.release.gates import GATE_DEFINITIONS, gate_manifest
from redscribe.v3.release.models import (
    RELEASE_ACTIONS,
    RELEASE_VERSION,
    DocBundle,
    DocSection,
    GateReport,
    ReleasePhase,
    ScenarioResult,
    SmokeReport,
)
from redscribe.v3.release.scenarios import SCENARIO_DESCRIPTIONS, run_all_scenarios

_QUICKSTART = """```bash
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
PYTHONPATH=src python3 -m ruff check .
PYTHONPATH=src python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
cd frontend && REDSCRIBE_SKIP_TYPECHECK=1 npm test
python3 scripts/loc_gate.py --baseline c65e699 --min-net 2000 --min-test-loc 600
```"""


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Render a Markdown table."""
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |")
    return "\n".join(lines)


def render_route_table(router: V3Router) -> str:
    """Render the registered release route surface."""
    rows = [
        (route.path, ", ".join(route.methods), "yes" if route.public else "no")
        for route in router.routes()
        if route.namespace in {"release", "system"}
    ]
    return _table(("Route", "Methods", "Public"), rows)


def render_capability_table() -> str:
    """Render the capability catalogue."""
    return _table(("Capability", "Default"), ((name, "enabled") for name in ALL_CAPABILITIES))


def render_kind_table() -> str:
    """Render entity kind labels and colors."""
    rows = (
        (spec.kind.value if hasattr(spec.kind, "value") else str(spec.kind), spec.label, spec.color)
        for spec in default_registry.all()
    )
    return _table(("Kind", "Label", "Token color"), rows)


def render_phase_table() -> str:
    """Render the seven golden-path phases."""
    rows = ((phase.position + 1, phase.label, phase.value) for phase in ReleasePhase.ordered())
    return _table(("Order", "Phase", "Identifier"), rows)


def render_scenario_table(scenarios: Sequence[ScenarioResult]) -> str:
    """Render golden-path scenario results."""
    rows = (
        (
            result.name,
            "PASS" if result.ok else "FAIL",
            f"{result.passed_count}/{len(result.steps)}",
            ", ".join(result.phases),
        )
        for result in scenarios
    )
    return _table(("Scenario", "Result", "Steps", "Phases"), rows)


def render_smoke_section(report: SmokeReport) -> str:
    """Render smoke results and the summary line."""
    summary = (
        f"{report.passed_count}/{len(report.checks)} checks passed; {report.failed_count} failed."
    )
    return f"{summary}\n\n{report.markdown()}"


def render_gate_section(report: GateReport | None) -> str:
    """Render hardening results or the gate catalogue when not yet run."""
    if report is not None:
        return f"{len(report.results)} gates evaluated.\n\n{report.markdown()}"
    return _table(
        ("Gate", "Title", "Severity"),
        (
            (definition.gate_id, definition.title, definition.severity)
            for definition in GATE_DEFINITIONS
        ),
    )


def render_onboarding_section() -> str:
    """Render the first-run flow as a checklist."""
    lines = []
    for step in ONBOARDING_SPECS:
        marker = "required" if step.required else "optional"
        lines.append(
            f"- **{step.title}** ({marker}) — {step.description} `data-step={step.step_id}`"
        )
    return "\n".join(lines)


def render_polish_section() -> str:
    """Render the responsive and animation polish checklist."""
    lines = []
    for check in POLISH_CHECKS:
        status = "done" if check.done else "open"
        lines.append(f"- `{check.check_id}` — {check.label} ({status})")
    lines.append("")
    lines.append("Animation audit:")
    for audit in ANIMATION_AUDITS:
        safe = "safe" if audit.reduced_motion_safe else "needs fallback"
        lines.append(f"- `{audit.surface}` — {audit.property_name} ({safe})")
    lines.append("")
    lines.append("Breakpoints: " + ", ".join(f"{name} {width}px" for name, width in BREAKPOINTS))
    return "\n".join(lines)


def build_doc_bundle(
    router: V3Router | None = None,
    *,
    smoke: SmokeReport | None = None,
    gates: GateReport | None = None,
) -> DocBundle:
    """Build the complete release guide from supplied reports."""
    target = router
    if target is None:
        target = V3Router()
        register_system_routes(target)
        from redscribe.v3.namespaces.release import register as register_release

        register_release(target)
    scenarios = run_all_scenarios()
    sections = (
        DocSection(
            "overview",
            "Overview",
            (
                f"RedScribe V3 release {RELEASE_VERSION} is additive: V2 routes and behaviour "
                "remain intact. Every branch registers routes, entity kinds, migrations, and "
                "tokens as data through the B00 contracts. The app remains offline-only, with "
                "no runtime dependencies, no network calls, and no code-execution path."
            ),
        ),
        DocSection("quickstart", "Quickstart", _QUICKSTART),
        DocSection(
            "golden-paths",
            "Golden paths",
            (
                render_phase_table()
                + "\n\n"
                + render_scenario_table(scenarios)
                + "\n\nAll scenario names are documented in "
                + ", ".join(f"`{name}`" for name in SCENARIO_DESCRIPTIONS)
                + "."
            ),
        ),
        DocSection(
            "api",
            "API surface",
            (
                "Every response uses `{ data, meta }` or `{ error, meta }`. Stable error codes "
                "and opaque cursors are supplied by B00.\n\n"
                + render_route_table(target)
                + "\n\n"
                + render_capability_table()
            ),
        ),
        DocSection("design-system", "Design system v3", render_kind_table()),
        DocSection("onboarding", "Onboarding and first run", render_onboarding_section()),
        DocSection("polish", "Responsive and animation polish", render_polish_section()),
        DocSection(
            "smoke",
            "Release smoke suite",
            render_smoke_section(smoke)
            if smoke is not None
            else "Run `release.smoke` to generate this section.",
        ),
        DocSection("gates", "Gates", render_gate_section(gates)),
        DocSection("changelog", "Proposed CHANGELOG.md", fenced(proposed_changelog())),
        DocSection("readme", "Proposed README.md", fenced(proposed_readme(target))),
        DocSection(
            "migration",
            "Migration notes",
            build_migration_notes().render(),
        ),
        DocSection("checklist", "Release checklist", _release_checklist()),
    )
    return DocBundle(title="RedScribe V3 Release Guide", version=RELEASE_VERSION, sections=sections)


def fenced(text: str, language: str = "markdown") -> str:
    """Wrap generated content in a four-backtick fence."""
    return f"````{language}\n{text.rstrip()}\n````"


def proposed_readme(router: V3Router | None = None) -> str:
    """Render proposed README content (never written directly)."""
    route_count = len(router.routes()) if router is not None else 0
    return "\n".join(
        [
            "# RedScribe",
            "",
            "A local-first notebook for CTFs, penetration tests, and security research.",
            "",
            "## Why",
            "",
            "RedScribe keeps captures, findings, evidence, and reports in one local vault.",
            "V3 adds a universal entity layer, typed events, and a stable API envelope while",
            "preserving every V2 feature and route.",
            "",
            "## Highlights",
            "",
            "- Universal entity identities and typed relationships",
            "- Correlated local event stream with redaction and durable outbox",
            "- Evidence vault with hashes and custody records",
            "- Graph workbench, playbooks, reporting, search, sync, and extensions as data",
            "- Design system v3 with onboarding and reduced-motion support",
            "",
            "## Quickstart",
            "",
            _QUICKSTART,
            "",
            "## Release state",
            "",
            f"- API version: {default_config.api_version}",
            f"- Schema version: {default_config.schema_version}",
            f"- Registered routes: {route_count}",
            "- Offline only: yes",
            "- Runtime dependencies: none",
            "",
            "See `docs/v3/release.md` for golden paths, smoke results, and gate evidence.",
        ]
    )


def proposed_changelog() -> str:
    """Render proposed CHANGELOG content."""
    return build_release_changelog().render()


def proposed_migration_notes() -> str:
    """Render proposed migration-note content."""
    return build_migration_notes().render()


def release_file_proposals(
    router: V3Router | None = None,
    *,
    smoke: SmokeReport | None = None,
    gates: GateReport | None = None,
) -> dict[str, str]:
    """Return the proposed content for shared documentation files."""
    bundle = build_doc_bundle(router, smoke=smoke, gates=gates)
    return {
        "README.md": proposed_readme(router),
        "CHANGELOG.md": proposed_changelog(),
        "docs/v3/release.md": bundle.render(),
    }


def docs_manifest() -> dict[str, Any]:
    """Return a JSON-safe manifest of generator capabilities."""
    return {
        "version": RELEASE_VERSION,
        "sections": [
            "overview",
            "quickstart",
            "golden-paths",
            "api",
            "design-system",
            "onboarding",
            "polish",
            "smoke",
            "gates",
            "changelog",
            "readme",
            "migration",
            "checklist",
        ],
        "release_actions": list(RELEASE_ACTIONS),
        "gate_count": len(GATE_DEFINITIONS),
        "gate_manifest": gate_manifest(),
        "release_note": build_release_note(),
    }


def _release_checklist() -> str:
    """Render the final release checklist."""
    return "\n".join(
        [
            "- [ ] All branch refs green on the full gate matrix",
            "- [ ] Golden-path scenarios reported as PASS",
            "- [ ] Smoke suite reported as PASS",
            "- [ ] Hardening gates reported as PASS (warnings reviewed)",
            "- [ ] Full program LOC report produced",
            "- [ ] Proposed README and CHANGELOG content reviewed and applied by a maintainer",
        ]
    )
