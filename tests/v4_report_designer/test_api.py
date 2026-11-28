"""Tests for v4 report API envelopes, authorization, events and routes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.capabilities import FeatureFlag, FeatureGate, FeatureRequirement
from redscribe.v4.clock import Clock
from redscribe.v4.contracts import Capability, CapabilitySet, ErrorCode
from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox
from redscribe.v4.report_designer import register as register_package
from redscribe.v4.report_designer.api import (
    ROUTE_PREFIXES,
    Action,
    ReportApi,
    ReportRequest,
    as_api_error,
    build_api,
    register,
)
from redscribe.v4.report_designer.service import ThemeError, ThemeResolver
from redscribe.v4.report_designer.storage import StoreError
from redscribe.v4.report_designer.types import ReportSection, SectionKind


def sequence() -> Callable[[], str]:
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"req-{counter:04d}"

    return next_id


def fixture_api(
    capabilities: CapabilitySet | None = None,
    gate: FeatureGate | None = None,
) -> tuple[ReportApi, EventBus, InMemoryOutbox, Clock]:
    outbox = InMemoryOutbox()
    bus = EventBus(outbox=outbox)
    clock = Clock(frozen_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
    api = build_api(
        capabilities=capabilities or CapabilitySet.full(),
        gate=gate or FeatureGate(CapabilitySet.full()),
        bus=bus,
        clock=clock,
        id_factory=sequence(),
    )
    return api, bus, outbox, clock


def unwrap(envelope: dict[str, object]) -> dict[str, Any]:
    assert "error" not in envelope, envelope
    data = envelope["data"]
    assert isinstance(data, dict)
    return data


def error_of(envelope: dict[str, object]) -> dict[str, Any]:
    assert "error" in envelope, envelope
    error = envelope["error"]
    assert isinstance(error, dict)
    return error


def source_payload(title: str = "Engagement") -> dict[str, object]:
    return {
        "title": title,
        "subtitle": "Final draft",
        "findings": [
            {"ref": "F-1", "title": "SQL injection", "severity": "high", "detail": "Login form"},
            {"ref": "F-2", "title": "Weak headers", "severity": "low"},
        ],
        "evidence": [{"ref": "E-1", "label": "Screenshot", "source": "shot.png"}],
        "appendix": ["Scope notes"],
        "metadata": [["client", "Acme"]],
    }


def build_layout(
    api: ReportApi, layout_id: str = "built.layout", title: str = "Engagement"
) -> dict[str, object]:
    envelope = api.handle_payload(
        "build",
        {
            "layout_id": layout_id,
            "theme": "client",
            "source": source_payload(title),
        },
    )
    return unwrap(envelope)


def test_action_parse_is_normalized_and_strict() -> None:
    assert Action.parse(" THEMES ") is Action.THEMES
    assert Action.parse("layouts") is Action.LAYOUTS
    with pytest.raises(Exception, match="unknown action"):
        Action.parse("explode")


def test_describe_envelope_has_actions_routes_and_capabilities() -> None:
    api, _, _, _ = fixture_api()
    envelope = api.handle_payload("describe")
    data = unwrap(envelope)
    meta = envelope["meta"]
    assert isinstance(meta, dict)
    assert data["service"] == "report-designer"
    assert data["routes"] == list(ROUTE_PREFIXES)
    assert set(data["formats"]) == {"html", "markdown"}
    assert "render" in data["actions"]
    assert meta["version"] == "v4"
    assert meta["request_id"] == "req-0001"
    assert api.actions() == tuple(Action.parse(action).value for action in data["actions"])


def test_api_rejects_unknown_action_and_bad_pagination() -> None:
    api, _, _, _ = fixture_api()
    unknown = error_of(api.handle_payload("not-an-action"))
    assert unknown["code"] == ErrorCode.INVALID_INPUT.value
    bad_page = error_of(api.handle_payload("describe", {"page": 0}))
    assert bad_page["code"] == ErrorCode.INVALID_INPUT.value
    assert "page must be between" in bad_page["message"]
    bad_type = error_of(api.handle_payload("describe", {"page_size": "50"}))
    assert "page_size must be an integer" in bad_type["message"]
    bad_sections = error_of(api.handle_payload("create", {"title": "x", "sections": 4}))
    assert "sections must be an array" in bad_sections["message"]
    bad_format = error_of(api.handle_payload("render", {"format": "pdf"}))
    assert "unknown export format" in bad_format["message"]


def test_themes_action_paginates_descriptors() -> None:
    api, _, _, _ = fixture_api()
    envelope = api.handle_payload("themes", {"page": 1, "page_size": 3})
    data = unwrap(envelope)
    meta = envelope["meta"]
    assert isinstance(meta, dict)
    assert data["total"] == len(ThemeResolver().names())
    assert len(data["items"]) == 3
    assert data["next_cursor"]
    assert meta["next_cursor"] == data["next_cursor"]
    assert meta["etag"] == data["etag"]
    second = unwrap(api.handle_payload("themes", {"page": 2, "page_size": 3}))
    assert second["page"] == 2
    assert second["items"][0]["name"] != data["items"][0]["name"]


def test_theme_detail_resolves_inheritance() -> None:
    api, _, _, _ = fixture_api()
    data = unwrap(api.handle_payload("theme", {"theme": "client"}))
    assert data["name"] == "client"
    assert data["lineage"] == ["base", "compact", "client"]
    assert data["colors"]["primary"] == "#1f5c4a"
    assert data["margins"]["top"] == 12
    missing = error_of(api.handle_payload("theme", {"theme": "ghost"}))
    assert missing["code"] == ErrorCode.NOT_FOUND.value


def test_build_and_layouts_actions() -> None:
    api, _, _, _ = fixture_api()
    first = build_layout(api)
    assert first["id"] == "built.layout"
    assert first["title"] == "Engagement"
    assert first["theme"] == "client"
    assert len(first["sections"]) == 5
    assert first["created_at"] == "2026-01-02T03:04:05.000Z"
    listing = unwrap(api.handle_payload("layouts"))
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == "built.layout"
    single = unwrap(api.handle_payload("layout", {"layout_id": "built.layout"}))
    assert single["title"] == "Engagement"
    missing = error_of(api.handle_payload("layout", {"layout_id": "absent"}))
    assert missing["code"] == ErrorCode.NOT_FOUND.value


def test_create_update_delete_layout_lifecycle() -> None:
    api, _, _, _ = fixture_api()
    created = unwrap(
        api.handle_payload(
            "create",
            {
                "title": "Client report",
                "theme": "modern",
                "sections": [{"kind": "cover", "title": "Cover"}],
            },
        )
    )
    layout_id = created["id"]
    assert layout_id == "req-0001"
    assert created["sections"][0]["kind"] == "cover"
    updated = unwrap(
        api.handle_payload(
            "update",
            {"layout_id": layout_id, "changes": {"title": "Renamed", "theme": "ink"}},
        )
    )
    assert updated["title"] == "Renamed"
    assert updated["theme"] == "ink"
    bad_field = error_of(
        api.handle_payload("update", {"layout_id": layout_id, "changes": {"unknown": 1}})
    )
    assert bad_field["code"] == ErrorCode.INVALID_INPUT.value
    assert "unsupported layout fields" in bad_field["message"]
    missing_title = error_of(api.handle_payload("create", {}))
    assert "title is required" in missing_title["message"]
    bad_section = error_of(
        api.handle_payload(
            "create",
            {"title": "x", "sections": [{"kind": "not-a-kind"}]},
        )
    )
    assert bad_section["code"] == ErrorCode.INVALID_INPUT.value
    deleted = unwrap(api.handle_payload("delete", {"layout_id": layout_id}))
    assert deleted["id"] == layout_id
    twice = error_of(api.handle_payload("delete", {"layout_id": layout_id}))
    assert twice["code"] == ErrorCode.NOT_FOUND.value


def test_layouts_filter_by_theme_and_pages_action() -> None:
    api, _, _, _ = fixture_api()
    build_layout(api, "one.layout", "First")
    build_layout(api, "two.layout", "Second")
    filtered = unwrap(api.handle_payload("layouts", {"theme": "client", "page_size": 1}))
    assert filtered["total"] == 2
    assert filtered["next_cursor"]
    pages = unwrap(api.handle_payload("pages", {"layout_id": "one.layout"}))
    assert pages["total"] >= 4
    assert [page["number"] for page in pages["items"]] == list(range(1, pages["total"] + 1))
    assert all(
        page["section"] in {"cover", "toc", "findings", "evidence", "appendix"}
        for page in pages["items"]
    )
    missing = error_of(api.handle_payload("pages", {"layout_id": "ghost"}))
    assert missing["code"] == ErrorCode.NOT_FOUND.value


def test_render_emits_deterministic_event_and_outbox_record() -> None:
    api, bus, outbox, clock = fixture_api()
    build_layout(api)
    envelope = api.handle_payload("render", {"layout_id": "built.layout", "format": "html"})
    data = unwrap(envelope)
    assert data["format"] == "html"
    assert data["extension"] == ".html"
    assert data["mime_type"] == "text/html"
    assert data["page_count"] > 0
    assert "<title>Engagement</title>" in data["text"]
    assert len(data["pages"]) == data["page_count"]
    events = bus.published
    assert len(events) == 1
    assert events[0].kind is EventKind.REPORT_RENDERED
    assert events[0].aggregate_id == "built.layout"
    assert events[0].payload["checksum"] == data["checksum"]
    assert events[0].occurred_at == clock.iso()
    records = outbox.records(EventKind.REPORT_RENDERED)
    assert len(records) == 1
    assert records[0].event_id == events[0].event_id
    assert records[0].payload["format"] == "html"


def test_export_action_supports_markdown_and_trigger_metadata() -> None:
    api, bus, _, _ = fixture_api()
    build_layout(api)
    data = unwrap(
        api.handle_payload(
            "export",
            {"layout_id": "built.layout", "format": "markdown", "trigger": "ui"},
        )
    )
    assert data["format"] == "markdown"
    assert data["extension"] == ".md"
    assert data["text"].startswith("# Engagement")
    assert bus.published[0].payload["trigger"] == "ui"
    assert len(api.recent_exports()) == 1


def test_manifest_requires_export_then_records_last_render() -> None:
    api, _, _, clock = fixture_api()
    conflict = error_of(api.handle_payload("manifest", {}))
    assert conflict["code"] == ErrorCode.CONFLICT.value
    build_layout(api)
    rendered = unwrap(api.handle_payload("render", {"layout_id": "built.layout"}))
    manifest = unwrap(api.handle_payload("manifest", {}))
    assert manifest["id"].startswith("req-")
    assert manifest["generated_at"] == clock.iso()
    assert manifest["version"] == 1
    assert [entry["layout_id"] for entry in manifest["entries"]] == ["built.layout"]
    assert [entry["format"] for entry in manifest["entries"]] == ["html"]
    assert manifest["entries"][0]["checksum"] == rendered["checksum"]
    assert manifest["digest"].startswith('W/"')
    explicit = unwrap(
        api.handle_payload(
            "manifest",
            {
                "manifest_id": "explicit.manifest",
                "manifests": [
                    {
                        "layout_id": "built.layout",
                        "format": "markdown",
                        "checksum": "abc123",
                        "page_count": 4,
                    }
                ],
            },
        )
    )
    assert explicit["id"] == "explicit.manifest"
    assert explicit["entries"][0]["format"] == "markdown"
    bad_entry = error_of(
        api.handle_payload("manifest", {"manifests": [{"format": "pdf", "page_count": -1}]})
    )
    assert bad_entry["code"] == ErrorCode.INVALID_INPUT.value


def test_stats_action_includes_store_and_theme_indexes() -> None:
    api, _, _, _ = fixture_api()
    build_layout(api)
    data = unwrap(api.handle_payload("stats"))
    assert data["layouts"] == 1
    assert data["themes"] == 1
    assert data["theme_index"] == {"client": 1}
    assert data["page_size"]["lines_per_page"] == 32


def test_capability_and_feature_gate_denials_are_enveloped() -> None:
    limited = CapabilitySet(frozenset({Capability.READ, Capability.WRITE}))
    api, _, _, _ = fixture_api(capabilities=limited)
    denied = error_of(api.handle_payload("render", {"layout_id": "x"}))
    assert denied["code"] == ErrorCode.FORBIDDEN.value
    assert "missing capability: export" in denied["message"]
    assert unwrap(api.handle_payload("themes"))["total"] > 0
    gate = FeatureGate(
        CapabilitySet(frozenset({Capability.READ})),
        {
            FeatureFlag.REPORT_DESIGNER: FeatureRequirement(
                FeatureFlag.REPORT_DESIGNER, frozenset({Capability.ADMIN})
            )
        },
    )
    gated, _, _, _ = fixture_api(gate=gate)
    gated_error = error_of(gated.handle_payload("describe"))
    assert gated_error["code"] == ErrorCode.FORBIDDEN.value
    assert "feature disabled" in gated_error["message"]


def test_error_translation_mapping() -> None:
    assert as_api_error(StoreError("unknown layout: x")).code is ErrorCode.NOT_FOUND
    assert as_api_error(StoreError("unsupported fields")).code is ErrorCode.INVALID_INPUT
    assert as_api_error(ThemeError("unknown theme: x")).code is ErrorCode.NOT_FOUND
    assert as_api_error(ThemeError("theme cycle detected")).code is ErrorCode.INVALID_INPUT
    assert as_api_error(PermissionError("no")).code is ErrorCode.FORBIDDEN
    assert as_api_error(ValueError("bad")).code is ErrorCode.INVALID_INPUT
    assert as_api_error(RuntimeError("boom")).code is ErrorCode.INTERNAL


def test_request_decoder_validates_untyped_payload() -> None:
    request = ReportRequest.from_payload("LAYOUTS", {"page": 2})
    with pytest.raises(Exception, match="page must be an integer"):
        ReportRequest.from_payload("layouts", {"page": "2"})
    with pytest.raises(Exception, match="manifests must be an array"):
        ReportRequest.from_payload("manifest", {"manifests": "x"})
    with pytest.raises(Exception, match="manifest entries must be objects"):
        ReportRequest.from_payload("manifest", {"manifests": [3]})
    assert request.action is Action.LAYOUTS


def test_route_registration_is_explicit_and_idempotent() -> None:
    api, _, _, _ = fixture_api()
    registry = RouteRegistry()
    routes = api.register(registry)
    assert tuple(route.prefix for route in routes) == tuple(f"/{item}" for item in ROUTE_PREFIXES)
    assert len(registry) == len(ROUTE_PREFIXES)
    assert registry.get("/api/v4/reports") is not None
    with pytest.raises(ValueError, match="route already registered"):
        api.register(registry)
    second = RouteRegistry()
    assert len(register(api, second)) == len(ROUTE_PREFIXES)
    registered = register_package(api)
    assert sorted(item.prefix for item in registered) == sorted(
        f"/{item}" for item in ROUTE_PREFIXES
    )


def test_section_round_trip_through_create_payload() -> None:
    api, _, _, _ = fixture_api()
    section = ReportSection(kind=SectionKind.FINDINGS, title="Findings", page_break_before=True)
    created = unwrap(
        api.handle_payload("create", {"title": "Manual", "sections": [section.to_dict()]})
    )
    assert created["sections"][0]["page_break_before"] is True
    assert created["sections"][0]["entries"] == []
