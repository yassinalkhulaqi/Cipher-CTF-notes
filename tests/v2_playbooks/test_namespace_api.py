from __future__ import annotations

from typing import Any

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.contracts import V2Error
from redscribe.ui.web.v2.namespaces.playbooks import (
    PlaybooksNamespace,
    register,
    route_names,
)
from redscribe.ui.web.v2.routes import ApiV2
from redscribe.v2.playbooks.services import PlaybookService


@pytest.fixture
def namespace(vault: Vault) -> PlaybooksNamespace:
    service = PlaybookService()
    instance = PlaybooksNamespace(service)
    instance.register(ApiV2(vault))
    return instance


@pytest.fixture
def api(vault: Vault, namespace: PlaybooksNamespace) -> ApiV2:
    instance = ApiV2(vault)
    namespace.register(instance)
    return instance


def _payload(key: str = "custom") -> dict[str, Any]:
    return {
        "key": key,
        "title": "Custom assessment",
        "status": "active",
        "category": "web",
        "version": "1.0.0",
        "variables": [{"key": "target", "label": "Target", "required": True}],
        "steps": [
            {
                "id": "one",
                "title": "First step",
                "command_template": "echo {{ target }}",
                "checklist": [{"id": "c1", "label": "Confirm"}],
            }
        ],
    }


def test_route_inventory_contains_fifty_additive_routes(
    api: ApiV2, namespace: PlaybooksNamespace
) -> None:
    prefixes = ("playbooks.", "steps.", "variables.", "snippets.", "templates.", "runs.")
    names = [name for name in api.routes if name.startswith(prefixes)]

    assert len(names) == 50
    assert len(namespace.specs()) == 50
    assert len(set(route_names())) == 50
    assert "playbooks.list" in names
    assert "runs.set_checklist" in names
    assert "system.health" in api.routes


def test_register_uses_additive_hook(vault: Vault) -> None:
    api = ApiV2(vault)
    namespace = PlaybooksNamespace(PlaybookService(seed=False))

    namespace.register(api)

    assert len(api.routes) == 58
    assert api.route("snippets.list").mutating is False
    assert api.route("playbooks.create").mutating is True
    assert api.route("runs.start").entity_type == "run"


def test_register_requires_registration_hook() -> None:
    with pytest.raises(TypeError, match="registration hook"):
        PlaybooksNamespace().register(object())


def test_module_register_helper_binds_service(vault: Vault) -> None:
    api = ApiV2(vault)
    service = PlaybookService(seed=False)
    namespace = register(api, service)

    assert namespace.service is service
    assert "playbooks.stats" in api.routes


def test_playbooks_list_returns_paginated_data(api: ApiV2) -> None:
    result = api.invoke("playbooks.list", {"limit": 3})

    assert len(result.data) == 3
    assert result.page is not None
    assert result.page.limit == 3
    assert result.etag


def test_playbooks_list_filters_and_tags(api: ApiV2) -> None:
    result = api.invoke("playbooks.list", {"query": "binary", "tags": "ctf"})

    assert result.data
    assert all("binary" in str(item).casefold() for item in result.data)


def test_list_rejects_invalid_limit(api: ApiV2) -> None:
    with pytest.raises(V2Error) as excinfo:
        api.invoke("playbooks.list", {"limit": 9999})

    assert excinfo.value.status == 400
    assert excinfo.value.code == "invalid_request"


def test_create_get_update_clone_and_delete_playbook(api: ApiV2) -> None:
    created = api.invoke("playbooks.create", _payload())

    assert created.status == 201
    assert created.data["key"] == "custom"

    fetched = api.invoke("playbooks.get", {"key": "custom"})
    assert fetched.data["steps"][0]["id"] == "one"

    updated = api.invoke("playbooks.update", {"key": "custom", "title": "Renamed"})
    assert updated.data["title"] == "Renamed"
    assert updated.data["version"] == "1.1.0"

    cloned = api.invoke("playbooks.clone", {"key": "custom", "new_key": "copy"})
    assert cloned.status == 201
    assert cloned.data["key"] == "copy"

    deleted = api.invoke("playbooks.delete", {"key": "copy"})
    assert deleted.data["key"] == "copy"


def test_create_duplicate_maps_to_conflict(api: ApiV2) -> None:
    api.invoke("playbooks.create", _payload())
    with pytest.raises(V2Error) as excinfo:
        api.invoke("playbooks.create", _payload())

    assert excinfo.value.status == 409
    assert excinfo.value.code == "conflict"


def test_get_missing_maps_to_not_found(api: ApiV2) -> None:
    with pytest.raises(V2Error) as excinfo:
        api.invoke("playbooks.get", {"key": "missing"})

    assert excinfo.value.status == 404
    assert excinfo.value.code == "not_found"


def test_validate_graph_and_step_graph_routes(api: ApiV2) -> None:
    api.invoke("playbooks.create", _payload("graphbook"))
    validation = api.invoke("playbooks.validate", {"key": "graphbook"})
    assert validation.data["ok"] is True

    graph = api.invoke("playbooks.graph", {"key": "graphbook"})
    assert graph.data["ok"] is True
    assert graph.data["nodes"][0]["id"] == "one"

    neighborhood = api.invoke("playbooks.step_graph", {"key": "graphbook", "step_id": "one"})
    assert neighborhood.data["step_id"] == "one"


def test_recommend_stats_options_and_export_routes(api: ApiV2) -> None:
    recommendations = api.invoke("playbooks.recommend", {"query": "web"})
    assert isinstance(recommendations.data["recommendations"], list)

    stats = api.invoke("playbooks.stats", {})
    assert stats.data["playbooks"] >= 8

    options = api.invoke("playbooks.options", {})
    assert "step_kinds" in options.data

    exported = api.invoke("playbooks.export", {"source": "tests"})
    assert exported.data["kind"] == "redscribe-playbooks"


def test_import_and_reset_routes(api: ApiV2) -> None:
    bundle = api.invoke("playbooks.export", {"source": "tests"}).data
    imported = api.invoke("playbooks.import", {"bundle": bundle, "strategy": "replace"})
    assert imported.data["ok"] is True

    with pytest.raises(V2Error) as excinfo:
        api.invoke("playbooks.import", {"bundle": bundle, "strategy": "overlay"})
    assert excinfo.value.code == "invalid_choice"

    with pytest.raises(V2Error) as excinfo:
        api.invoke("playbooks.import", {})
    assert excinfo.value.code == "missing_field"

    reset = api.invoke("playbooks.reset", {})
    assert reset.data["runs"] == 0


def test_step_routes(api: ApiV2) -> None:
    api.invoke("playbooks.create", _payload("stepbook"))
    added = api.invoke(
        "steps.add",
        {
            "key": "stepbook",
            "step": {"id": "two", "title": "Second", "command_template": "echo two"},
        },
    )
    assert added.status == 201

    updated = api.invoke(
        "steps.update", {"key": "stepbook", "step_id": "two", "step": {"title": "Updated"}}
    )
    assert updated.data["title"] == "Updated"

    linked = api.invoke("steps.link", {"key": "stepbook", "step_id": "two", "depends_on": "one"})
    assert linked.data["depends_on"] == ["one"]

    unlinked = api.invoke(
        "steps.unlink", {"key": "stepbook", "step_id": "two", "depends_on": "one"}
    )
    assert unlinked.data["depends_on"] == []

    moved = api.invoke("steps.move", {"key": "stepbook", "step_id": "two", "position": 0})
    assert moved.data["id"] == "two"

    checklist = api.invoke(
        "steps.checklist",
        {
            "key": "stepbook",
            "step_id": "two",
            "items": [{"id": "c2", "label": "Second check"}],
        },
    )
    assert checklist.data["checklist"][0]["id"] == "c2"

    removed = api.invoke("steps.remove", {"key": "stepbook", "step_id": "two"})
    assert removed.data["id"] == "two"


def test_variable_routes(api: ApiV2) -> None:
    api.invoke("playbooks.create", _payload("varbook"))
    added = api.invoke(
        "variables.add",
        {"key": "varbook", "variable": {"key": "ports", "label": "Ports", "kind": "list"}},
    )
    assert added.status == 201

    resolved = api.invoke(
        "variables.resolve",
        {"key": "varbook", "target": "example.com", "values": {"target": "example.com"}},
    )
    assert resolved.data["values"]["target"] == "example.com"

    removed = api.invoke("variables.remove", {"key": "varbook", "name": "ports"})
    assert removed.data["key"] == "ports"


def test_snippet_routes(api: ApiV2) -> None:
    listed = api.invoke("snippets.list", {"limit": 4})
    assert len(listed.data) == 4

    created = api.invoke(
        "snippets.create",
        {
            "key": "probe",
            "title": "Probe",
            "command": "curl -I {{ target }}",
            "tags": ["web"],
        },
    )
    assert created.status == 201

    fetched = api.invoke("snippets.get", {"key": "probe"})
    assert fetched.data["key"] == "probe"

    updated = api.invoke("snippets.update", {"key": "probe", "title": "Probe updated"})
    assert updated.data["title"] == "Probe updated"

    used = api.invoke("snippets.use", {"key": "probe", "values": {"target": "example.com"}})
    assert used.data["command"] == "curl -I example.com"

    composed = api.invoke(
        "snippets.compose", {"keys": ["probe"], "values": {"target": "example.com"}}
    )
    assert composed.data["ok"] is True

    stats = api.invoke("snippets.stats", {})
    assert stats.data["total"] > 40

    deleted = api.invoke("snippets.delete", {"key": "probe"})
    assert deleted.data["key"] == "probe"

    with pytest.raises(V2Error) as excinfo:
        api.invoke("snippets.get", {"key": "probe"})
    assert excinfo.value.code == "not_found"


def test_snippet_validation_routes(api: ApiV2) -> None:
    with pytest.raises(V2Error) as excinfo:
        api.invoke("snippets.compose", {"keys": "probe"})
    assert excinfo.value.code == "invalid_type"

    with pytest.raises(V2Error) as excinfo:
        api.invoke("snippets.get", {})
    assert excinfo.value.code == "missing_field"


def test_template_routes(api: ApiV2) -> None:
    listed = api.invoke("templates.list", {"category": "playbooks"})
    assert [item["key"] for item in listed.data] == [
        "checklist-summary",
        "playbook-run",
        "step-log",
    ]

    registered = api.invoke(
        "templates.register",
        {
            "key": "custom-report",
            "name": "Custom report",
            "content": "# {{ title }}",
            "variables": [{"key": "title", "required": True}],
        },
    )
    assert registered.status == 201

    fetched = api.invoke("templates.get", {"key": "custom-report"})
    assert fetched.data["name"] == "Custom report"

    rendered = api.invoke(
        "templates.render", {"key": "custom-report", "values": {"title": "Result"}}
    )
    assert rendered.data["content"] == "# Result"

    history = api.invoke("templates.history", {"key": "custom-report"})
    assert history.data["versions"] == ["1.0.0"]

    deleted = api.invoke("templates.delete", {"key": "custom-report"})
    assert deleted.data["key"] == "custom-report"


def test_run_routes(api: ApiV2, namespace: PlaybooksNamespace) -> None:
    api.invoke("playbooks.create", _payload("runbook"))
    values = {"values": {"target": "example.com"}}

    plan = api.invoke("runs.plan", {"key": "runbook", **values})
    assert len(plan.data["steps"]) == 1

    preview = api.invoke("runs.preview", {"key": "runbook", **values})
    assert "Custom assessment" in preview.data["preview"]

    started = api.invoke("runs.start", {"key": "runbook", **values})
    assert started.status == 201
    run_id = started.data["id"]

    fetched = api.invoke("runs.get", {"id": run_id})
    assert fetched.data["id"] == run_id

    listed = api.invoke("runs.list", {"playbook_key": "runbook"})
    assert [item["id"] for item in listed.data] == [run_id]

    advice = api.invoke("runs.next", {"id": run_id})
    assert advice.data["step_id"] == "one"

    checklist = api.invoke("runs.checklist", {"id": run_id})
    assert checklist.data["states"] == {"c1": "pending"}

    updated_checklist = api.invoke(
        "runs.set_checklist",
        {"id": run_id, "item_id": "c1", "state": "done", "note": "checked"},
    )
    assert updated_checklist.data["checklist"]["c1"] == "done"

    advanced = api.invoke("runs.advance", {"id": run_id, "step_id": "one", "status": "done"})
    assert advanced.data["status"] == "completed"

    progress = api.invoke("runs.progress", {"id": run_id})
    assert progress.data["percent"] == 100

    assert namespace.service.get_run(run_id).status.value == "completed"


def test_run_missing_maps_to_not_found(api: ApiV2) -> None:
    with pytest.raises(V2Error) as excinfo:
        api.invoke("runs.get", {"id": 999})

    assert excinfo.value.status == 404
    assert excinfo.value.code == "not_found"
