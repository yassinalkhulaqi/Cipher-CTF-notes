"""Tests for documentation generation and changelog builders."""

from __future__ import annotations

import pytest

from redscribe.v3.api.router import V3Router, register_system_routes
from redscribe.v3.release.changelog import (
    CHANGELOG_CATEGORIES,
    ChangelogBuilder,
    MigrationNoteBuilder,
    build_migration_notes,
    build_release_changelog,
    build_release_note,
)
from redscribe.v3.release.docs_gen import (
    build_doc_bundle,
    docs_manifest,
    fenced,
    proposed_changelog,
    proposed_migration_notes,
    proposed_readme,
    release_file_proposals,
    render_capability_table,
    render_gate_section,
    render_kind_table,
    render_phase_table,
    render_route_table,
    render_scenario_table,
)
from redscribe.v3.release.gates import GATE_DEFINITIONS
from redscribe.v3.release.scenarios import run_all_scenarios
from redscribe.v3.release.smoke import run_smoke


def _router() -> V3Router:
    router = V3Router()
    register_system_routes(router)
    from redscribe.v3.namespaces.release import register

    register(router)
    return router


def test_changelog_builder_groups_by_category() -> None:
    builder = ChangelogBuilder(version="9.9.9", released_on="2026-01-01")
    builder.add("Added", "Beta feature", "Details here", "B99")
    builder.add("Fixed", "A bug", "Details here")
    builder.add("Added", "Alpha feature", "Details here")
    grouped = builder.by_category()
    assert list(grouped["Added"][0].title) == list("Alpha feature")
    assert grouped["Fixed"][0].reference == ""
    rendered = builder.render()
    assert rendered.startswith("## [9.9.9] - 2026-01-01")
    assert "### Added" in rendered
    assert "### Fixed" in rendered
    assert "(B99)" in rendered
    assert builder.as_dict()["version"] == "9.9.9"


def test_changelog_builder_rejects_unknown_category() -> None:
    with pytest.raises(ValueError, match="Unknown changelog category"):
        ChangelogBuilder().add("Nope", "Title", "Detail")


def test_build_release_changelog_covers_all_categories() -> None:
    builder = build_release_changelog()
    categories = {entry.category for entry in builder.entries()}
    assert categories == set(CHANGELOG_CATEGORIES)
    assert len(builder.entries()) >= 9
    assert "B14" in {entry.reference for entry in builder.entries()}


def test_migration_note_builder() -> None:
    builder = MigrationNoteBuilder()
    builder.add("4", "5", "Upgrade", "Run migrations", note="Safe")
    builder.add("5", "6", "Review", "Check config", automated=False)
    rendered = builder.render()
    assert "# V3 migration notes" in rendered
    assert "## 1. Upgrade (`4` -> `5`)" in rendered
    assert "- Mode: manual" in rendered
    assert builder.as_dict()["notes"][0]["automated"] is True
    assert len(build_migration_notes().notes()) >= 3


def test_release_note_includes_route_count() -> None:
    note = build_release_note(_router())
    assert "- Release: 3.0.0" in note
    assert "Registered routes in this run: 0" not in note
    assert "capture -> finding" in note


def test_fenced_helper() -> None:
    rendered = fenced("# Title\n\nBody")
    assert rendered.startswith("````markdown\n")
    assert rendered.endswith("\n````")
    assert "# Title" in rendered


def test_table_renderers() -> None:
    router = _router()
    assert "| Route | Methods | Public |" in render_route_table(router)
    assert "/api/v3/release/manifest" in render_route_table(router)
    assert "| Capability | Default |" in render_capability_table()
    assert "| Kind | Label | Token color |" in render_kind_table()
    assert "| Order | Phase | Identifier |" in render_phase_table()
    assert "| Scenario | Result | Steps | Phases |" in render_scenario_table(run_all_scenarios())


def test_render_gate_section_without_report() -> None:
    rendered = render_gate_section(None)
    assert "| Gate | Title | Severity |" in rendered
    assert GATE_DEFINITIONS[0].gate_id in rendered


def test_render_gate_section_with_report() -> None:
    from redscribe.v3.release.models import GateReport, GateResult, GateStatus

    report = GateReport(results=(GateResult("g1", "Gate one", GateStatus.PASS, "all good"),))
    rendered = render_gate_section(report)
    assert "1 gates evaluated" in rendered
    assert "`g1`" in rendered
    assert "all good" in rendered


def test_doc_bundle_has_all_sections() -> None:
    bundle = build_doc_bundle(_router())
    ids = [section.section_id for section in bundle.sections]
    assert ids == [
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
    ]
    rendered = bundle.render()
    assert "# RedScribe V3 Release Guide" in rendered
    assert "## Golden paths" in rendered
    assert "## Proposed CHANGELOG.md" in rendered
    assert "````markdown" in rendered
    assert bundle.as_dict()["version"] == "3.0.0"


def test_doc_bundle_embeds_reports() -> None:
    router = _router()
    bundle = build_doc_bundle(router, smoke=run_smoke(router))
    smoke_section = next(section for section in bundle.sections if section.section_id == "smoke")
    assert "checks passed" in smoke_section.body
    assert "api.envelope_roundtrip" in smoke_section.body


def test_proposed_documents_do_not_mutate_shared_files() -> None:
    proposals = release_file_proposals(_router())
    assert set(proposals) == {"README.md", "CHANGELOG.md", "docs/v3/release.md"}
    assert proposals["README.md"].startswith("# RedScribe")
    assert proposals["CHANGELOG.md"].startswith("## [3.0.0]")
    assert "## Proposed README.md" in proposals["docs/v3/release.md"]


def test_proposed_helpers_are_consistent() -> None:
    assert proposed_changelog() == build_release_changelog().render()
    assert proposed_migration_notes() == build_migration_notes().render()
    assert "## Quickstart" in proposed_readme(_router())


def test_docs_manifest() -> None:
    manifest = docs_manifest()
    assert manifest["version"] == "3.0.0"
    assert len(manifest["sections"]) == 13
    assert manifest["gate_count"] == len(GATE_DEFINITIONS)
    assert "release_actions" in manifest
