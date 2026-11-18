from __future__ import annotations

import pytest

from redscribe.v2.playbooks.errors import (
    DuplicateKeyError,
    NotFoundError,
    UnknownSnippetError,
    UnknownStepError,
    ValidationError,
)
from redscribe.v2.playbooks.services import PlaybookService


def _custom_payload(key: str = "custom") -> dict[str, object]:
    return {
        "key": key,
        "title": "Custom assessment",
        "description": "A small custom workflow",
        "status": "active",
        "category": "web",
        "tags": ["custom", "web"],
        "version": "1.0.0",
        "variables": [{"key": "target", "label": "Target", "required": True}],
        "steps": [
            {
                "id": "one",
                "title": "First step",
                "command_template": "echo {{ target }}",
                "estimated_minutes": 5,
            }
        ],
    }


def test_seeded_service_has_expected_catalog(service: PlaybookService) -> None:
    stats = service.stats()

    assert stats["playbooks"] >= 8
    assert stats["snippets"] > 40
    assert stats["templates"] >= 10
    assert stats["runs"] == 0
    assert sum(stats["status_counts"].values()) == stats["playbooks"]


def test_empty_service_starts_with_empty_repositories(empty_service: PlaybookService) -> None:
    stats = empty_service.stats()

    assert stats["playbooks"] == 0
    assert stats["snippets"] == 0
    assert stats["templates"] == 0


def test_options_are_stable(empty_service: PlaybookService) -> None:
    options = empty_service.options()

    assert "active" in options["statuses"]
    assert "action" in options["step_kinds"]
    assert "done" in options["step_statuses"]
    assert "text" in options["variable_kinds"]


def test_list_playbooks_filters_by_query_tags_status_and_category(
    service: PlaybookService,
) -> None:
    assert service.list_playbooks(query="binary")
    assert service.list_playbooks(tags=("forensics",))
    assert service.list_playbooks(status="active")
    assert service.list_playbooks(category="web")
    assert service.list_playbooks(limit=2).__len__() == 2


def test_create_get_and_duplicate_playbook(empty_service: PlaybookService) -> None:
    created = empty_service.create_playbook(_custom_payload())

    assert created.id == 1
    assert created.key == "custom"
    assert empty_service.get_playbook("custom") == created
    assert empty_service.histories["custom"].versions == ("1.0.0",)

    with pytest.raises(DuplicateKeyError):
        empty_service.create_playbook(_custom_payload())


def test_get_missing_playbook_raises(empty_service: PlaybookService) -> None:
    with pytest.raises(NotFoundError):
        empty_service.get_playbook("missing")


def test_update_playbook_bumps_version_and_records_history(
    empty_service: PlaybookService,
) -> None:
    empty_service.create_playbook(_custom_payload())
    updated = empty_service.update_playbook(
        "custom", {"title": "Updated assessment", "message": "Renamed", "author": "tester"}
    )

    assert updated.title == "Updated assessment"
    assert updated.version == "1.1.0"
    assert len(empty_service.histories["custom"].entries) == 2


def test_update_playbook_supports_explicit_bump(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    updated = empty_service.update_playbook("custom", {"bump": "major"})

    assert updated.version == "2.0.0"


def test_delete_and_clone_playbook(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    clone = empty_service.clone_playbook("custom", new_key="copy", title="Copy")

    assert clone.key == "copy"
    assert clone.title == "Copy"
    assert clone.version == "1.1.0"
    assert clone.status.value == "draft"

    removed = empty_service.delete_playbook("copy")
    assert removed.key == "copy"
    with pytest.raises(NotFoundError):
        empty_service.get_playbook("copy")


def test_validate_playbook_and_graph(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())

    assert empty_service.validate_playbook("custom") == ()

    graph = empty_service.playbook_graph("custom")
    assert graph["ok"] is True
    assert graph["playbook_key"] == "custom"
    assert graph["nodes"][0]["id"] == "one"


def test_step_graph_reports_ancestors_and_descendants(service: PlaybookService) -> None:
    key = service.list_playbooks(category="ctf")[0].key
    playbook = service.get_playbook(key)
    target = playbook.steps[-1]

    graph = service.step_graph(key, target.id)

    assert graph["step_id"] == target.id
    assert graph["ancestors"]
    assert graph["descendants"] == []


def test_step_graph_rejects_unknown_step(service: PlaybookService) -> None:
    key = service.list_playbooks()[0].key
    with pytest.raises(UnknownStepError):
        service.step_graph(key, "missing")


def test_add_update_move_link_unlink_and_remove_step(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    added = empty_service.add_step(
        "custom", {"id": "two", "title": "Second", "command_template": "echo second"}
    )
    assert added.id == "two"

    updated = empty_service.update_step("custom", "two", {"title": "Second updated"})
    assert updated.title == "Second updated"

    linked = empty_service.link_steps("custom", "two", "one")
    assert linked.depends_on == ("one",)

    unlinked = empty_service.unlink_steps("custom", "two", "one")
    assert unlinked.depends_on == ()

    moved = empty_service.move_step("custom", "two", {"position": 0})
    assert moved.id == "two"
    assert [step.id for step in empty_service.get_playbook("custom").steps] == ["two", "one"]

    removed = empty_service.remove_step("custom", "one")
    assert removed.id == "one"
    assert [step.id for step in empty_service.get_playbook("custom").steps] == ["two"]


def test_add_step_rejects_duplicate_id(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    with pytest.raises(ValidationError, match="Duplicate step"):
        empty_service.add_step("custom", {"id": "one", "title": "Duplicate"})


def test_set_step_checklist(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    step = empty_service.set_step_checklist(
        "custom",
        "one",
        {"items": [{"id": "c1", "label": "Confirm", "required": True}]},
    )

    assert [item.id for item in step.checklist] == ["c1"]
    assert step.checklist[0].required is True

    with pytest.raises(UnknownStepError):
        empty_service.set_step_checklist("custom", "missing", {"items": []})


def test_add_and_remove_variable(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    added = empty_service.add_variable(
        "custom", {"key": "ports", "label": "Ports", "kind": "list", "default": "80"}
    )

    assert added.key == "ports"

    with pytest.raises(ValidationError, match="Duplicate variable"):
        empty_service.add_variable("custom", {"key": "ports", "label": "Ports"})

    removed = empty_service.remove_variable("custom", "ports")
    assert removed.key == "ports"

    with pytest.raises(ValidationError, match="Unknown variable"):
        empty_service.remove_variable("custom", "ports")


def test_resolve_variables_through_service(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    resolved = empty_service.resolve_variables(
        "custom", {"target": "example.com", "values": {"target": "example.com"}}
    )

    assert resolved["values"]["target"] == "example.com"
    assert resolved["ok"] is True


def test_snippet_crud_search_use_and_stats(service: PlaybookService) -> None:
    created = service.create_snippet(
        {
            "key": "probe",
            "title": "Probe target",
            "command": "curl -I {{ target }}",
            "tags": ["web"],
        }
    )
    assert created.key == "probe"

    updated = service.update_snippet("probe", {"title": "Probe updated"})
    assert updated.title == "Probe updated"

    assert "probe" in [item.key for item in service.list_snippets(query="probe")]
    assert "probe" in [item.key for item in service.list_snippets(tags=("web",), limit=100)]

    used = service.use_snippet("probe", values={"target": "example.com"})
    assert used["command"] == "curl -I example.com"
    assert used["snippet"]["usage_count"] == 1
    assert service.snippet_stats()["total"] > 40

    removed = service.delete_snippet("probe")
    assert removed.key == "probe"
    with pytest.raises(UnknownSnippetError):
        service.get_snippet("probe")


def test_compose_snippets_through_service(service: PlaybookService) -> None:
    result = service.compose_snippet_keys(["nmap-quick-scan"], {"target": "example.com"})

    assert result["ok"] is True
    assert "example.com" in result["command"]

    with pytest.raises(UnknownSnippetError):
        service.compose_snippet_keys(["missing"])


def test_template_crud_render_and_history(service: PlaybookService) -> None:
    created = service.register_template(
        {
            "key": "custom-report",
            "name": "Custom report",
            "content": "# {{ title }}",
            "variables": [{"key": "title", "required": True}],
        }
    )
    assert created.key == "custom-report"
    assert service.get_template("custom-report") == created

    rendered = service.render_template("custom-report", {"title": "Result"})
    assert rendered["content"] == "# Result"

    assert service.template_history("custom-report")["versions"] == ["1.0.0"]
    assert [item.key for item in service.list_templates(category="general")]

    removed = service.delete_template("custom-report")
    assert removed.key == "custom-report"


def test_plan_preview_start_and_advance_run(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    payload = {"values": {"target": "example.com"}}

    plan = empty_service.plan_run("custom", payload)
    assert len(plan.steps) == 1

    preview = empty_service.preview_run("custom", payload)
    assert "Custom assessment" in preview["preview"]

    run = empty_service.start_run("custom", payload)
    assert run.status.value == "running"
    assert run.current_step == "one"

    advice = empty_service.next_step(run.id)
    assert advice is not None
    assert advice.step_id == "one"

    updated = empty_service.advance_run(
        run.id, {"step_id": "one", "status": "done", "message": "completed"}
    )
    assert updated.status.value == "completed"
    assert empty_service.run_progress(run.id)["percent"] == 100


def test_run_checklist_updates_through_service(empty_service: PlaybookService) -> None:
    payload = _custom_payload()
    payload["steps"][0]["checklist"] = [{"id": "c1", "label": "Confirm"}]
    empty_service.create_playbook(payload)
    run = empty_service.start_run("custom", {"values": {"target": "example.com"}})

    updated = empty_service.set_run_checklist(
        run.id, {"item_id": "c1", "state": "done", "note": "checked"}
    )
    assert updated.checklist["c1"] == "done"

    checklist = empty_service.run_checklist(run.id)
    assert checklist["states"]["c1"] == "done"
    assert checklist["progress"]["done"] == 1


def test_cancel_run_and_recent_keys(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    run = empty_service.start_run("custom", {"values": {"target": "example.com"}})
    assert empty_service.stats()["recent_keys"] == ["custom"]

    cancelled = empty_service.cancel_run(run.id, "No longer needed")
    assert cancelled.status.value == "cancelled"
    assert [item.id for item in empty_service.list_runs(playbook_key="custom")] == [run.id]


def test_recommendations_are_scored_and_explained(service: PlaybookService) -> None:
    results = service.recommend({"query": "binary", "tags": ["ctf"], "limit": 5})

    assert results
    assert all({"kind", "key", "score", "reason", "title"} <= set(item) for item in results)
    assert results[0]["score"] >= results[-1]["score"]

    context = service.recommender.context_for_target("https://example.com", query="web")
    assert "web" in context.tags

    mixed = service.recommender.mixed(context)
    assert mixed
    assert len({(item.kind, item.key) for item in mixed}) == len(mixed)


def test_export_import_replace_round_trip(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    bundle = empty_service.export(source="tests")

    assert bundle.manifest["playbooks"] == 1

    empty_service.reset()
    report = empty_service.import_bundle(bundle.as_dict(), strategy="replace")

    assert report.ok
    assert empty_service.get_playbook("custom").title == "Custom assessment"


def test_snapshot_restore_round_trip(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    empty_service.start_run("custom", {"values": {"target": "example.com"}})
    snapshot = empty_service.snapshot()

    restored = PlaybookService(seed=False)
    restored.restore(snapshot)

    assert restored.get_playbook("custom") == empty_service.get_playbook("custom")
    assert len(restored.runs) == len(empty_service.runs)
    assert restored.recent_keys == empty_service.recent_keys


def test_reset_restores_curated_data(empty_service: PlaybookService) -> None:
    empty_service.create_playbook(_custom_payload())
    empty_service.start_run("custom", {"values": {"target": "example.com"}})

    empty_service.reset()

    assert empty_service.get_playbook("web-app-assessment").key == "web-app-assessment"
    assert empty_service.stats()["runs"] == 0
    assert empty_service.stats()["recent_keys"] == []
