"""Tests for activity namespace registration and API routes."""

from __future__ import annotations

import pytest

from redscribe.v3.activity.service import ActivityService
from redscribe.v3.api.envelope import success
from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.namespaces import namespace_names
from redscribe.v3.namespaces.activity import (
    build_handlers,
    get_service,
    register,
    set_service,
)
from tests.v3_activity.conftest import BASE_TIME, DAY

ACTIONS = {
    "stream",
    "filters",
    "validate",
    "digest",
    "since",
    "mark",
    "retrospective",
    "redact",
    "entry",
    "stats",
    "health",
    "modes",
}


def _data(payload: dict[str, object]) -> dict[str, object]:
    """Unwrap an envelope and verify its shape."""
    assert "data" in payload
    assert "meta" in payload
    return dict(payload["data"])  # type: ignore[arg-type]


def test_register_activity_routes(service: ActivityService) -> None:
    router = V3Router()
    set_service(service)
    try:
        register(router)
    finally:
        set_service(None)
    assert router.namespaces() == ("activity",)
    assert {route.action for route in router.routes()} == ACTIONS
    assert all(route.path.startswith("/api/v3/activity/") for route in router.routes())


def test_namespace_is_discoverable() -> None:
    assert "activity" in namespace_names()


def test_health_and_modes(service: ActivityService) -> None:
    handlers = build_handlers(service)
    health = _data(handlers["health"]({}, {"x-request-id": "req_activity"}))
    assert health["status"] == "ok"
    assert health["entries"] == 8
    modes = _data(handlers["modes"]({}, {}))
    assert modes["densities"] == ["compact", "comfortable", "detailed"]
    assert modes["periods"] == ["daily", "weekly"]


def test_stream_route_filters_and_paginates(service: ActivityService) -> None:
    handlers = build_handlers(service)
    all_rows = _data(handlers["stream"]({"size": 2}, {}))
    assert all_rows["total"] == 8
    assert len(all_rows["entries"]) == 2
    filtered = _data(handlers["stream"]({"query": "kind:finding.created"}, {}))
    assert filtered["total"] == 1
    combined = _data(
        handlers["stream"]({"kinds": ["note.created", "note.updated"], "density": "compact"}, {})
    )
    assert combined["total"] == 2
    assert "payload" not in combined["entries"][0]
    warned = _data(handlers["stream"]({"query": "bogus:value", "timezone": "Mars/Olympus"}, {}))
    assert len(warned["warnings"]) >= 2


def test_filter_metadata_and_validation_routes(service: ActivityService) -> None:
    handlers = build_handlers(service)
    metadata = _data(handlers["filters"]({}, {}))
    assert metadata["operators"] == ["include", "exclude"]
    valid = _data(handlers["validate"]({"query": "kind:finding.created"}, {}))
    assert valid["valid"] is True
    invalid = _data(handlers["validate"]({"query": "nope:value"}, {}))
    assert invalid["valid"] is False


def test_digest_route_is_deterministic(service: ActivityService) -> None:
    handlers = build_handlers(service)
    first = _data(handlers["digest"]({"period": "weekly", "generated_at": 7}, {}))
    second = _data(handlers["digest"]({"period": "weekly", "generated_at": 7}, {}))
    assert first == second
    assert first["generated_at"] == 7.0
    assert len(first["digests"]) == 1
    anchored = _data(
        handlers["digest"]({"period": "daily", "anchor": BASE_TIME + DAY, "generated_at": 7}, {})
    )
    assert len(anchored["digests"]) == 1
    assert anchored["digests"][0]["key"] == "2023-11-15"


def test_visit_and_retrospective_routes(service: ActivityService) -> None:
    handlers = build_handlers(service)
    before = _data(handlers["since"]({"identity": "alice"}, {}))
    assert before["count"] == 8
    marker = _data(handlers["mark"]({"identity": "alice", "note": "now"}, {}))
    assert marker["sequence"] == 8
    after = _data(handlers["since"]({"identity": "alice"}, {}))
    assert after["count"] == 0
    summary = _data(handlers["retrospective"]({"start": BASE_TIME, "end": BASE_TIME + 5 * DAY}, {}))
    assert summary["total_events"] == 8
    assert summary["active_days"] == 5


def test_redact_entry_and_stats_routes(service: ActivityService) -> None:
    handlers = build_handlers(service)
    redacted = _data(handlers["redact"]({"payload": {"token": "abc", "title": "ok"}}, {}))
    assert redacted["payload"]["token"] == "[redacted]"
    assert redacted["report"]["applied"] is True
    entry = _data(handlers["entry"]({"sequence": 1}, {}))
    assert entry["jump"]["kind"] == "finding"
    assert _data(handlers["stats"]({}, {}))["entries"] == 8


def test_route_error_handling(service: ActivityService) -> None:
    handlers = build_handlers(service)
    with pytest.raises(V3Error) as density_error:
        handlers["stream"]({"density": "huge"}, {})
    assert density_error.value.code is V3ErrorCode.INVALID_CHOICE
    with pytest.raises(V3Error) as period_error:
        handlers["digest"]({"period": "monthly"}, {})
    assert period_error.value.code is V3ErrorCode.INVALID_CHOICE
    with pytest.raises(V3Error) as missing_error:
        handlers["retrospective"]({}, {})
    assert missing_error.value.code is V3ErrorCode.MISSING_FIELD
    with pytest.raises(V3Error) as order_error:
        handlers["retrospective"]({"start": 5, "end": 5}, {})
    assert order_error.value.code is V3ErrorCode.INVALID_REQUEST
    with pytest.raises(V3Error) as payload_error:
        handlers["redact"]({"payload": "bad"}, {})
    assert payload_error.value.code is V3ErrorCode.INVALID_TYPE
    with pytest.raises(V3Error) as sequence_error:
        handlers["entry"]({"sequence": "1"}, {})
    assert sequence_error.value.code is V3ErrorCode.INVALID_TYPE
    with pytest.raises(V3Error) as not_found_error:
        handlers["entry"]({"sequence": 999}, {})
    assert not_found_error.value.code is V3ErrorCode.NOT_FOUND
    with pytest.raises(V3Error) as number_error:
        handlers["digest"]({"anchor": "not-a-number"}, {})
    assert number_error.value.code is V3ErrorCode.INVALID_TYPE


def test_request_id_is_propagated(service: ActivityService) -> None:
    handlers = build_handlers(service)
    payload = handlers["health"]({}, {"x-request-id": "req_123"})
    assert payload["meta"]["request_id"] == "req_123"
    assert success({"ok": True}).as_dict()["meta"]["api_version"] == "3.0"


def test_service_singleton_accessors() -> None:
    original = get_service()
    assert isinstance(original, ActivityService)
    replacement = ActivityService()
    set_service(replacement)
    assert get_service() is replacement
    set_service(None)
    assert isinstance(get_service(), ActivityService)
