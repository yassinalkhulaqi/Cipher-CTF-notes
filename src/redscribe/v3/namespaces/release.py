"""Release namespace routes for the V3 API.

Every action is added with ``router.add("release", action, handler)``; this
module is discovered by the B00 dynamic namespace loader and never edits a
central dispatch table. Handlers are read-only and deterministic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from redscribe.v3.api.router import V3Router
from redscribe.v3.entities.registry import default_registry
from redscribe.v3.release.changelog import build_migration_notes, build_release_changelog
from redscribe.v3.release.content import (
    ICON_LABELS,
    ONBOARDING_SPECS,
    SHOWCASE_ENTRIES,
    empty_state_payload,
    onboarding_payload,
    polish_payload,
    showcase_payload,
)
from redscribe.v3.release.docs_gen import build_doc_bundle, docs_manifest, proposed_readme
from redscribe.v3.release.gates import gate_manifest, run_hardening_gate
from redscribe.v3.release.manifest import readiness_summary, release_manifest
from redscribe.v3.release.models import RELEASE_VERSION
from redscribe.v3.release.scenarios import (
    SCENARIO_DESCRIPTIONS,
    run_all_scenarios,
    run_scenario,
    scenario_manifest,
)
from redscribe.v3.release.smoke import run_smoke


def _text_map(value: Any) -> dict[str, str]:
    """Coerce a body value into a string-to-string mapping."""
    if not isinstance(value, Mapping):
        return {}
    return {str(key): text for key, text in value.items() if isinstance(text, str)}


def _text(value: Any) -> str:
    """Coerce a body value into a string."""
    return value if isinstance(value, str) else ""


def register(router: V3Router) -> None:
    """Register all read-only release routes."""

    def manifest(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return release_manifest(router)

    def golden(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        requested = _text(body.get("name"))
        if requested:
            result = run_scenario(requested)
            return {"scenarios": [result.as_dict()], "ok": result.ok}
        results = run_all_scenarios()
        return {
            "scenarios": [result.as_dict() for result in results],
            "ok": all(result.ok for result in results),
            "catalogue": scenario_manifest(),
        }

    def smoke(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return run_smoke(router).as_dict()

    def gates(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return gate_manifest()

    def gate_audit(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        report = run_hardening_gate(
            _text_map(body.get("sources")),
            router=router,
            pyproject_text=_text(body.get("pyproject")),
            css_sources=_text_map(body.get("css")),
            component_sources=_text_map(body.get("components")),
            manifest_text=_text(body.get("manifest")),
            docs_text=_text(body.get("docs")),
        )
        return report.as_dict()

    def docs(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        bundle = build_doc_bundle(router)
        payload: dict[str, Any] = bundle.as_dict()
        if bool(body.get("rendered", False)):
            payload["rendered"] = bundle.render()
        payload["manifest"] = docs_manifest()
        payload["proposals"] = {
            "README.md": proposed_readme(router),
            "CHANGELOG.md": build_release_changelog().render(),
        }
        return payload

    def changelog(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        builder = build_release_changelog()
        return {
            "version": builder.version,
            "released_on": builder.released_on,
            "entries": [entry.as_dict() for entry in builder.entries()],
            "rendered": builder.render(),
        }

    def migration_notes(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        builder = build_migration_notes()
        return {
            "notes": [note.as_dict() for note in builder.notes()],
            "rendered": builder.render(),
        }

    def readiness(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        scenarios = run_all_scenarios()
        smoke_report = run_smoke(router)
        audit = run_hardening_gate(
            _text_map(body.get("sources")),
            router=router,
            pyproject_text=_text(body.get("pyproject")),
            css_sources=_text_map(body.get("css")),
            component_sources=_text_map(body.get("components")),
            manifest_text=_text(body.get("manifest")),
            docs_text=_text(body.get("docs")),
        )
        evidential = bool(body.get("gates_evaluated", False)) and audit.ok
        payload = readiness_summary(
            golden_ok=all(result.ok for result in scenarios),
            smoke_ok=smoke_report.ok,
            gates_ok=evidential,
            golden_count=len(scenarios),
            smoke_count=len(smoke_report.checks),
            gate_count=len(audit.results),
        )
        payload["version"] = RELEASE_VERSION
        return payload

    def onboarding(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {
            "steps": list(onboarding_payload()),
            "required": sum(1 for step in ONBOARDING_SPECS if step.required),
            "empty_states": list(empty_state_payload()),
        }

    def showcase(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {
            "entries": list(showcase_payload()),
            "icons": [
                {"icon": icon, "label": label, "kind": kind} for icon, label, kind in ICON_LABELS
            ],
            "kind_labels": default_registry.labels(),
            "kind_colors": default_registry.colors(),
        }

    def polish(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        payload = polish_payload()
        payload["catalogue"] = list(SCENARIO_DESCRIPTIONS)
        payload["showcase_count"] = len(SHOWCASE_ENTRIES)
        return payload

    router.add("release", "manifest", manifest, public=True)
    router.add("release", "golden", golden, public=True)
    router.add("release", "smoke", smoke, public=True)
    router.add("release", "gates", gates, public=True)
    router.add("release", "gate_audit", gate_audit)
    router.add("release", "docs", docs, public=True)
    router.add("release", "changelog", changelog, public=True)
    router.add("release", "migration_notes", migration_notes, public=True)
    router.add("release", "readiness", readiness)
    router.add("release", "onboarding", onboarding, public=True)
    router.add("release", "showcase", showcase, public=True)
    router.add("release", "polish", polish, public=True)
