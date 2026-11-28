"""Tests for v4 automation API envelopes, errors, routes and persistence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

import pytest

from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.automation_v4 import register
from redscribe.v4.automation_v4.api import (
    WRITE_ACTIONS,
    Action,
    AutomationApi,
    AutomationRequest,
    as_api_error,
    build_api,
)
from redscribe.v4.automation_v4.service import DagValidationError
from redscribe.v4.automation_v4.storage import RunStore, StoreError
from redscribe.v4.automation_v4.types import (
    DagEdge,
    DagNode,
    Frequency,
    NodeKind,
    PlaybookDag,
    RunStatus,
    Schedule,
)
from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.clock import Clock
from redscribe.v4.contracts import ApiError, Capability, CapabilitySet, ErrorCode
from redscribe.v4.events import EventKind

FROZEN = datetime(2026, 1, 5, 9, 30, tzinfo=timezone.utc)


def node(node_id: str, kind: NodeKind = NodeKind.SETUP, *deps: str) -> DagNode:
    return DagNode(
        id=node_id,
        label=f"Node {node_id}",
        kind=kind,
        depends_on=deps,
        params={"target": node_id},
    )


def chain() -> PlaybookDag:
    return PlaybookDag(
        id="pb-1",
        name="Chain",
        nodes=(node("a"), node("b", NodeKind.COLLECT, "a"), node("c", NodeKind.REPORT, "b")),
        edges=(DagEdge("a", "b"), DagEdge("b", "c")),
    )


def cycle() -> PlaybookDag:
    return PlaybookDag(
        id="pb-cycle",
        name="Cycle",
        nodes=(
            node("a", NodeKind.SETUP, "b"),
            node("b", NodeKind.COLLECT, "a"),
        ),
    )


def api_with(store: RunStore | None = None) -> tuple[AutomationApi, RunStore]:
    active = store or RunStore()
    api = build_api(store=active, clock=Clock(FROZEN))
    active.put_dag(chain())
    return api, active


def meta(payload: Mapping[str, object]) -> Mapping[str, object]:
    assert "meta" in payload
    result = payload["meta"]
    assert isinstance(result, Mapping)
    return result


def data(payload: Mapping[str, object]) -> Mapping[str, object]:
    assert "data" in payload
    result = payload["data"]
    assert isinstance(result, Mapping)
    return result


def test_action_enum_is_stable() -> None:
    assert Action.parse(" dry-run ") is Action.DRY_RUN
    assert Action.parse("PLAN-SCHEDULE") is Action.PLAN_SCHEDULE
    assert "describe" in [action.value for action in Action]
    assert (
        frozenset(
            {
                Action.START,
                Action.COMPLETE,
                Action.CANCEL,
                Action.PLAN_SCHEDULE,
            }
        )
        == WRITE_ACTIONS
    )
    with pytest.raises(ApiError, match="unknown action"):
        Action.parse("delete-everything")


def test_request_decodes_all_fields() -> None:
    request = AutomationRequest.from_payload(
        "dry-run",
        {
            "page": 2,
            "page_size": 10,
            "playbook_id": "pb-1",
            "run_id": "run-1",
            "schedule_id": "s-1",
            "status": "succeeded",
            "dag": chain().to_dict(),
            "fail_nodes": ["b"],
            "schedule": Schedule("s", "pb", Frequency.INTERVAL).to_dict(),
            "request_id": "req-1",
        },
    )
    assert request.action is Action.DRY_RUN
    assert request.page == 2
    assert request.page_size == 10
    assert request.playbook_id == "pb-1"
    assert request.run_id == "run-1"
    assert request.schedule_id == "s-1"
    assert request.status == "succeeded"
    assert request.fail_nodes == ("b",)
    assert request.request_id == "req-1"
    assert request.dag["id"] == "pb-1"
    assert request.schedule["id"] == "s"


def test_request_defaults_and_validation() -> None:
    request = AutomationRequest.from_payload("describe")
    assert request.page == 1
    assert request.page_size == 50
    assert request.dag == {}
    assert request.fail_nodes == ()
    with pytest.raises(ApiError, match="page must be an integer"):
        AutomationRequest.from_payload("describe", {"page": "2"})
    with pytest.raises(ApiError, match="page_size must be an integer"):
        AutomationRequest.from_payload("describe", {"page_size": True})
    with pytest.raises(ApiError, match="dag must be an object"):
        AutomationRequest.from_payload("describe", {"dag": []})
    with pytest.raises(ApiError, match="schedule must be an object"):
        AutomationRequest.from_payload("describe", {"schedule": 1})


def test_describe_envelope_has_version_and_request_id() -> None:
    api, _ = api_with()
    payload = api.handle_payload("describe", {"request_id": "req-123"})
    assert "error" not in payload
    assert meta(payload)["version"] == "v4"
    assert meta(payload)["request_id"] == "req-123"
    assert meta(payload)["page"] == 1
    assert data(payload)["service"] == "playbook-automation"
    assert "dry-run" in data(payload)["actions"]
    assert set(data(payload)["capabilities"]) >= {"read", "automate", "delete"}


def test_generated_request_id_is_non_empty() -> None:
    api, _ = api_with()
    payload = api.handle_payload("describe")
    assert str(meta(payload)["request_id"])


def test_validate_action_success_and_failure() -> None:
    api, store = api_with()
    store.put_dag(cycle())
    valid = api.handle_payload("validate", {"playbook_id": "pb-1"})
    assert data(valid)["ok"] is True
    assert data(valid)["order"] == ["a", "b", "c"]
    invalid = api.handle_payload("validate", {"playbook_id": "pb-cycle"})
    assert data(invalid)["ok"] is False
    assert data(invalid)["cycles"] == [["a", "b"]]
    inline = api.handle_payload("validate", {"dag": chain().to_dict()})
    assert data(inline)["ok"] is True
    missing = api.handle_payload("validate")
    assert missing["error"]["code"] == ErrorCode.INVALID_INPUT.value


def test_playbooks_action_filters_and_paginates() -> None:
    api, store = api_with()
    second = PlaybookDag("pb-2", "Other", nodes=(node("x"),))
    store.put_dag(second)
    all_page = api.handle_payload("playbooks", {"page": 1, "page_size": 1})
    assert len(data(all_page)["items"]) == 1
    assert data(all_page)["total"] == 2
    assert data(all_page)["page_size"] == 1
    assert meta(all_page)["next_cursor"]
    second_page = api.handle_payload("playbooks", {"page": 2, "page_size": 1})
    assert data(second_page)["items"][0]["id"] == "pb-2"
    filtered = api.handle_payload("playbooks", {"playbook_id": "pb-1"})
    assert data(filtered)["total"] == 1
    empty = api.handle_payload("playbooks", {"playbook_id": "missing"})
    assert data(empty)["total"] == 0


def test_dry_run_action_returns_trace() -> None:
    api, _ = api_with()
    payload = api.handle_payload("dry-run", {"playbook_id": "pb-1"})
    trace = data(payload)["trace"]
    assert data(payload)["status"] == "succeeded"
    assert [step["node_id"] for step in trace] == ["a", "b", "c"]
    assert data(payload)["waves"] == 3
    assert len(data(payload)["digest"]) == 24
    failed = api.handle_payload("dry-run", {"playbook_id": "pb-1", "fail_nodes": ["b"]})
    assert data(failed)["status"] == "failed"
    assert data(failed)["trace"][2]["status"] == "skipped"


def test_dry_run_rejects_invalid_graph_via_envelope() -> None:
    api, store = api_with()
    store.put_dag(cycle())
    payload = api.handle_payload("dry-run", {"playbook_id": "pb-cycle"})
    assert payload["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert "invalid" in payload["error"]["message"]
    assert "cycle_detected" in payload["error"]["details"]


def test_run_lifecycle_through_api() -> None:
    api, store = api_with()
    started = api.handle_payload("start", {"playbook_id": "pb-1"})
    run_id = str(data(started)["id"])
    assert data(started)["status"] == "running"
    assert data(started)["trigger"] == "api"
    listed = api.handle_payload("runs", {"playbook_id": "pb-1", "page_size": 5})
    assert data(listed)["total"] == 1
    assert data(listed)["items"][0]["id"] == run_id
    one = api.handle_payload("run", {"run_id": run_id})
    assert data(one)["id"] == run_id
    completed = api.handle_payload("complete", {"run_id": run_id})
    assert data(completed)["status"] == "succeeded"
    assert len(data(completed)["trace"]) == 3
    assert store.require(run_id).status is RunStatus.SUCCEEDED
    succeeded = api.handle_payload("runs", {"status": "succeeded"})
    assert data(succeeded)["total"] == 1
    bad_status = api.handle_payload("runs", {"status": "unknown"})
    assert bad_status["error"]["code"] == ErrorCode.INVALID_INPUT.value


def test_cancel_and_conflict_through_api() -> None:
    api, store = api_with()
    started = api.handle_payload("start", {"playbook_id": "pb-1"})
    run_id = str(data(started)["id"])
    cancelled = api.handle_payload("cancel", {"run_id": run_id})
    assert data(cancelled)["status"] == "cancelled"
    again = api.handle_payload("cancel", {"run_id": run_id})
    assert again["error"]["code"] == ErrorCode.CONFLICT.value
    complete = api.handle_payload("complete", {"run_id": run_id})
    assert complete["error"]["code"] == ErrorCode.CONFLICT.value
    assert store.require(run_id).status is RunStatus.CANCELLED


def test_run_routes_error_envelopes() -> None:
    api, _ = api_with()
    assert api.handle_payload("run", {"run_id": "missing"})["error"]["code"] == "not_found"
    assert api.handle_payload("start")["error"]["code"] == "invalid_input"
    assert api.handle_payload("complete", {"run_id": "missing"})["error"]["code"] == "not_found"
    assert api.handle_payload("cancel", {"run_id": "missing"})["error"]["code"] == "not_found"
    assert api.handle_payload("unknown-action")["error"]["code"] == "invalid_input"


def test_schedule_actions() -> None:
    api, store = api_with()
    schedule = Schedule(
        "s-1",
        "pb-1",
        Frequency.DAILY,
        hour=7,
        minute=30,
        next_run="2026-01-05T08:00:00.000Z",
    )
    planned = api.handle_payload("plan-schedule", {"schedule": schedule.to_dict()})
    assert data(planned)["next_run"] == "2026-01-06T07:30:00.000Z"
    assert store.get_schedule("s-1") is not None
    listed = api.handle_payload("schedules", {"playbook_id": "pb-1"})
    assert data(listed)["total"] == 1
    assert data(listed)["items"][0]["id"] == "s-1"
    all_schedules = api.handle_payload("schedules")
    assert data(all_schedules)["total"] == 1
    due = api.handle_payload("due")
    assert data(due)["total"] == 0
    store.put_schedule(schedule)
    due_now = api.handle_payload("due")
    assert data(due_now)["total"] == 1
    invalid = api.handle_payload("plan-schedule")
    assert invalid["error"]["code"] == "invalid_input"
    bad_schedule = api.handle_payload("plan-schedule", {"schedule": {"interval_minutes": 0}})
    assert bad_schedule["error"]["code"] == "invalid_input"


def test_stats_action() -> None:
    api, _ = api_with()
    api.handle_payload("start", {"playbook_id": "pb-1"})
    stats = api.handle_payload("stats")
    assert data(stats)["runs"] == 1
    assert data(stats)["playbooks"] == 1
    assert data(stats)["terminal_runs"] == 0


def test_api_capability_and_gate_checks() -> None:
    store = RunStore()
    store.put_dag(chain())
    read_only = CapabilitySet(frozenset({Capability.READ}))
    gate = FeatureGate(CapabilitySet.full())
    api = build_api(store=store, gate=gate, capabilities=read_only, clock=Clock(FROZEN))
    assert "error" not in api.handle_payload("describe")
    for action in ("start", "cancel", "plan-schedule"):
        payload = api.handle_payload(action, {"playbook_id": "pb-1"})
        assert payload["error"]["code"] == ErrorCode.FORBIDDEN.value
    no_read = CapabilitySet(frozenset({Capability.AUTOMATE}))
    api_no_read = build_api(store=store, capabilities=no_read, clock=Clock(FROZEN))
    assert api_no_read.handle_payload("describe")["error"]["code"] == "forbidden"
    disabled = FeatureGate(CapabilitySet.full(), version="v3")
    api_disabled = build_api(store=store, gate=disabled, clock=Clock(FROZEN))
    assert api_disabled.handle_payload("describe")["error"]["code"] == "forbidden"
    assert api_disabled.gate.is_enabled(FeatureFlag.AUTOMATION) is False


def test_cancel_requires_delete_capability() -> None:
    store = RunStore()
    store.put_dag(chain())
    capabilities = CapabilitySet(frozenset({Capability.READ, Capability.AUTOMATE}))
    api = build_api(store=store, capabilities=capabilities, clock=Clock(FROZEN))
    run = api.handle_payload("start", {"playbook_id": "pb-1"})
    run_id = str(data(run)["id"])
    denied = api.handle_payload("cancel", {"run_id": run_id})
    assert denied["error"]["code"] == "forbidden"
    allowed_api = build_api(store=store, clock=Clock(FROZEN))
    assert data(allowed_api.handle_payload("cancel", {"run_id": run_id}))["status"] == "cancelled"


def test_route_registration() -> None:
    api, _ = api_with()
    registry = RouteRegistry()
    routes = api.register(registry)
    assert len(routes) == 6
    assert routes[0].full_path == "/api/v4/automation"
    assert "/api/v4/automation/dry-run" in [route.full_path for route in routes]
    assert len(registry) == 6
    assert registry.serialize() == registry.serialize()
    with pytest.raises(ValueError, match="route already registered"):
        api.register(registry)


def test_package_register_hook_is_kernel_compatible() -> None:
    routes = register(RouteRegistry())
    assert len(routes) == 6
    assert routes[0].name.startswith("playbook-automation:")
    api, _ = api_with()
    assert len(register(api)) == 6
    assert len(register(object())) == 6


def test_as_api_error_mapping() -> None:
    assert as_api_error(ApiError(ErrorCode.CONFLICT, "x")).code is ErrorCode.CONFLICT
    validation = as_api_error(DagValidationError("bad", ("cycle_detected",)))
    assert validation.code is ErrorCode.INVALID_INPUT
    assert validation.details == ("cycle_detected",)
    assert as_api_error(StoreError("missing")).code is ErrorCode.NOT_FOUND
    assert as_api_error(TypeError("type")).code is ErrorCode.INVALID_INPUT
    assert as_api_error(RuntimeError("boom")).code is ErrorCode.INTERNAL
    assert "error" in as_api_error(RuntimeError("boom")).to_dict()


def test_event_kinds_are_shared_with_kernel() -> None:
    assert EventKind.RUN_STARTED.value == "run.started"
    assert EventKind.RUN_FINISHED.value == "run.finished"


def test_store_crud_and_indexes() -> None:
    store = RunStore()
    run = store.put_dag(chain()).id
    from redscribe.v4.automation_v4.types import RunRecord

    first = RunRecord("r1", run, RunStatus.RUNNING, "2026-01-01T00:00:00.000Z")
    second = RunRecord(
        "r2", run, RunStatus.SUCCEEDED, "2026-01-02T00:00:00.000Z", "2026-01-02T00:01:00.000Z"
    )
    store.put(first)
    store.put(second)
    assert store.get("r1") == first
    assert store.by_playbook(run) == (first, second)
    assert store.by_status(RunStatus.RUNNING) == (first,)
    assert store.history(run, RunStatus.SUCCEEDED) == (second,)
    assert store.recent(1) == (second,)
    assert store.recent(0) == ()
    assert store.stats().runs == 2
    assert store.stats().terminal_runs == 1
    assert store.describe() == "runs=2 schedules=0 playbooks=1"
    assert store.delete("r1") == first
    assert store.get("r1") is None
    with pytest.raises(StoreError, match="unknown run"):
        store.delete("r1")


def test_store_schedule_and_dag_indexes() -> None:
    store = RunStore()
    store.put_dag(chain())
    store.put_dag(PlaybookDag("pb-2", "Second"))
    assert [dag.id for dag in store.all_dags()] == ["pb-1", "pb-2"]
    assert store.require_dag("pb-1").name == "Chain"
    with pytest.raises(StoreError, match="unknown playbook"):
        store.require_dag("missing")
    first = Schedule("s1", "pb-1", Frequency.INTERVAL, next_run="2026-01-02T00:00:00.000Z")
    second = Schedule("s2", "pb-1", Frequency.DAILY, next_run="2026-01-01T00:00:00.000Z")
    store.put_schedule(first)
    store.put_schedule(second)
    store.put_schedule(second.with_next_run("2026-01-03T00:00:00.000Z"))
    assert store.get_schedule("s2") is not None
    assert [item.id for item in store.schedules_for("pb-1")] == ["s1", "s2"]
    assert [item.id for item in store.all_schedules()] == ["s1", "s2"]
    assert store.delete_schedule("s1") == first
    with pytest.raises(StoreError, match="unknown schedule"):
        store.delete_schedule("s1")


def test_store_export_import_round_trip() -> None:
    store = RunStore()
    store.put_dag(chain())
    from redscribe.v4.automation_v4.types import RunRecord

    store.put(
        RunRecord(
            "r1",
            "pb-1",
            RunStatus.SUCCEEDED,
            "2026-01-01T00:00:00.000Z",
            "2026-01-01T00:01:00.000Z",
        )
    )
    store.put_schedule(Schedule("s1", "pb-1", Frequency.INTERVAL))
    exported = store.export()
    assert exported["schema_version"] == 1
    assert len(exported["runs"]) == 1
    assert len(exported["playbooks"]) == 1
    restored = RunStore()
    assert restored.import_snapshot(exported) == (1, 1)
    assert restored.export() == exported
    assert restored.stats() == store.stats()
    bad = dict(exported)
    bad["schema_version"] = 99
    with pytest.raises(StoreError, match="unsupported schema version"):
        restored.import_snapshot(bad)
    bad_runs = dict(exported)
    bad_runs["runs"] = [exported["runs"][0], exported["runs"][0]]
    with pytest.raises(StoreError, match="duplicate run id"):
        restored.import_snapshot(bad_runs)


def test_store_prune_keeps_newest_per_playbook() -> None:
    store = RunStore()
    from redscribe.v4.automation_v4.types import RunRecord

    for index in range(4):
        store.put(
            RunRecord(
                f"r{index}",
                "pb-1",
                RunStatus.RUNNING,
                f"2026-01-0{index + 1}T00:00:00.000Z",
            )
        )
    assert store.prune(2) == 2
    assert [run.id for run in store.by_playbook("pb-1")] == ["r2", "r3"]
    with pytest.raises(StoreError, match="keep must be >= 1"):
        store.prune(0)
    with pytest.raises(StoreError, match="limit must be >= 0"):
        store.recent(-1)


def test_store_rejects_malformed_snapshots() -> None:
    store = RunStore()
    with pytest.raises(StoreError, match="runs and schedules must be arrays"):
        store.import_snapshot({"runs": {}, "schedules": []})
    with pytest.raises(StoreError, match="playbooks must be an array"):
        store.import_snapshot({"runs": [], "schedules": [], "playbooks": 1})
    with pytest.raises(StoreError, match="schedule entries must be objects"):
        store.import_snapshot({"runs": [], "schedules": [1]})
    with pytest.raises(StoreError, match="playbook entries must be objects"):
        store.import_snapshot({"runs": [], "schedules": [], "playbooks": [1]})
    with pytest.raises(StoreError, match="duplicate schedule id in snapshot"):
        store.import_snapshot(
            {
                "runs": [],
                "schedules": [
                    Schedule("s", "pb", Frequency.INTERVAL).to_dict(),
                    Schedule("s", "pb", Frequency.INTERVAL).to_dict(),
                ],
            }
        )
    assert RunStore.summary_text(7) == ""


def test_api_handles_unexpected_domain_errors() -> None:
    api, _ = api_with()

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("unexpected")

    api.executor.execute = broken  # type: ignore[method-assign]
    payload = api.handle_payload("dry-run", {"playbook_id": "pb-1"})
    assert payload["error"]["code"] == ErrorCode.INTERNAL.value
