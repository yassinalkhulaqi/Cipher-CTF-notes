from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from redscribe.storage import db as db_module
from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api
from redscribe.ui.web.server import ApiServer
from redscribe.ui.web.v2.contracts import (
    API_VERSION,
    Page,
    V2Error,
    V2ErrorCode,
    decode_cursor,
    encode_cursor,
    envelope,
    error_envelope,
    paginate,
)
from redscribe.ui.web.v2.router import V2Router
from redscribe.ui.web.v2.routes import ApiV2


def _request(
    port: int,
    method: str,
    path: str,
    *,
    body: dict[str, object] | bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    request_headers = dict(headers or {})
    if method == "POST" and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = "application/json"
    payload: bytes | None
    if isinstance(body, dict):
        payload = json.dumps(body).encode("utf-8")
    elif isinstance(body, bytes):
        payload = body
    else:
        payload = None
    connection.request(method, path, body=payload, headers=request_headers)
    response = connection.getresponse()
    status = response.status
    response_headers = dict(response.getheaders())
    data = response.read()
    connection.close()
    return status, response_headers, data


@contextmanager
def _running(server: ApiServer) -> Iterator[int]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.bound_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def v2_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[int, Vault, Api]]:
    real_connect = db_module.sqlite3.connect

    def connect(*args: Any, **kwargs: Any) -> Any:
        kwargs["check_same_thread"] = False
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(db_module.sqlite3, "connect", connect)
    vault = Vault(tmp_path / "v2-server.db")
    api = Api(vault)
    try:
        with _running(ApiServer(("127.0.0.1", 0), api.handle)) as port:
            yield port, vault, api
    finally:
        vault.close()


def _seed_notes(vault: Vault, count: int = 5) -> list[int]:
    ids: list[int] = []
    for index in range(count):
        node = vault.create_node(
            f"Note {index}",
            content=f"body {index}",
            tags="web, demo" if index % 2 == 0 else "misc",
            target="example.com" if index % 2 == 0 else "other.tld",
        )
        ids.append(node.id)
    return ids


def test_cursor_roundtrip_is_opaque() -> None:
    cursor = encode_cursor({"offset": 3})
    assert cursor.isascii()
    assert "=" not in cursor
    assert decode_cursor(cursor) == {"offset": 3}


def test_paginate_reports_stable_metadata() -> None:
    items = list(range(7))
    page_items, page = paginate(items, cursor=None, limit=3)
    assert page_items == [0, 1, 2]
    assert isinstance(page, Page)
    assert page.cursor is not None
    assert page.next is not None
    assert page.total == 7
    assert page.has_more is True
    next_items, next_page = paginate(items, cursor=page.next, limit=3)
    assert next_items == [3, 4, 5]
    assert next_page.has_more is True
    last_items, last_page = paginate(items, cursor=next_page.next, limit=3)
    assert last_items == [6]
    assert last_page.has_more is False
    assert last_page.next is None


def test_envelope_and_error_contract() -> None:
    success = envelope([1, 2], request_id="req-1", page=Page(total=2))
    assert success["ok"] is True
    assert success["data"] == [1, 2]
    assert success["meta"]["request_id"] == "req-1"
    assert success["meta"]["api_version"] == API_VERSION
    assert success["meta"]["page"]["total"] == 2
    failure = error_envelope(
        V2Error(422, V2ErrorCode.INVALID_CHOICE, "Bad choice", details={"field": "kind"}),
        request_id="req-2",
    )
    assert failure["ok"] is False
    assert failure["error"]["code"] == "invalid_choice"
    assert failure["error"]["message"] == "Bad choice"
    assert failure["error"]["details"] == {"field": "kind"}
    assert failure["error"]["request_id"] == "req-2"
    assert failure["error"]["retryable"] is False


def test_registry_exposes_additive_system_and_note_routes(vault: Vault) -> None:
    routes = ApiV2(vault).routes
    assert {
        "system.health",
        "system.capabilities",
        "system.api_schema",
        "system.events",
        "api.version",
        "notes.list",
        "notes.get",
        "notes.create",
    } <= set(routes)
    assert routes["notes.create"].mutating is True
    assert routes["notes.get"].required == ("id",)


def test_router_system_routes(vault: Vault) -> None:
    router = V2Router(vault)
    health = router.dispatch("system.health", {}, request_id="req-health")
    assert health["ok"] is True
    assert health["meta"]["request_id"] == "req-health"
    data = health["data"]
    assert data["ok"] is True
    assert data["schema_version"] == vault.schema_version
    assert data["note_count"] == 0
    assert "uptime" not in data

    capabilities = router.dispatch("system.capabilities", {}, request_id="req-cap")
    assert capabilities["data"]["api_version"] == API_VERSION
    assert "system" in capabilities["data"]["namespaces"]
    assert capabilities["data"]["limits"]["max_body_bytes"] > 0

    schema = router.dispatch("system.api_schema", {}, request_id="req-schema")
    names = {route["name"] for route in schema["data"]["routes"]}
    assert "notes.get" in names
    get_route = next(route for route in schema["data"]["routes"] if route["name"] == "notes.get")
    assert get_route["required"] == ["id"]
    assert get_route["mutating"] is False

    version = router.dispatch("api.version", {}, request_id="req-version")
    assert version["data"]["api_version"] == API_VERSION
    assert version["data"]["v1_compatible"] is True


def test_router_notes_list_pagination_and_filters(vault: Vault) -> None:
    ids = _seed_notes(vault)
    router = V2Router(vault)
    first = router.dispatch("notes.list", {"limit": 2}, request_id="req-list")
    assert first["ok"] is True
    assert [item["id"] for item in first["data"]] == ids[:2]
    page = first["meta"]["page"]
    assert page["total"] == 5
    assert page["has_more"] is True
    assert page["next"]

    second = router.dispatch(
        "notes.list",
        {"limit": 2, "cursor": page["next"]},
        request_id="req-list-2",
    )
    assert [item["id"] for item in second["data"]] == ids[2:4]

    filtered = router.dispatch(
        "notes.list",
        {"tag": "web", "status": "todo"},
        request_id="req-list-3",
    )
    assert [item["id"] for item in filtered["data"]] == [ids[0], ids[2], ids[4]]
    queried = router.dispatch(
        "notes.list",
        {"query": "body 3"},
        request_id="req-list-4",
    )
    assert [item["id"] for item in queried["data"]] == [ids[3]]


def test_router_notes_get_and_not_found(vault: Vault) -> None:
    ids = _seed_notes(vault, count=1)
    router = V2Router(vault)
    response = router.dispatch("notes.get", {"id": ids[0]}, request_id="req-get")
    assert response["ok"] is True
    assert response["data"]["id"] == ids[0]
    assert response["data"]["content"] == "body 0"
    assert response["meta"]["etag"].startswith("sha256:")

    missing = router.dispatch("notes.get", {"id": 9999}, request_id="req-missing")
    assert missing["ok"] is False
    assert missing["error"]["code"] == "not_found"
    assert missing["error"]["request_id"] == "req-missing"


@pytest.mark.parametrize(
    ("method", "body", "code"),
    [
        ("missing.route", {}, "unknown_route"),
        ("notes.get", {}, "invalid_type"),
        ("notes.get", {"id": "x"}, "invalid_type"),
        ("notes.get", {"id": True}, "invalid_type"),
        ("notes.list", {"limit": 0}, "invalid_request"),
        ("notes.list", {"kind": "nope"}, "invalid_choice"),
        ("notes.list", {"cursor": "not-a-cursor"}, "invalid_cursor"),
    ],
)
def test_router_reports_stable_validation_errors(
    vault: Vault,
    method: str,
    body: dict[str, Any],
    code: str,
) -> None:
    response = V2Router(vault).dispatch(method, body, request_id="req-bad")
    assert response["ok"] is False
    assert response["error"]["code"] == code
    assert response["error"]["request_id"] == "req-bad"


def test_router_idempotent_create_replays_and_conflicts(vault: Vault) -> None:
    router = V2Router(vault)
    body = {"title": "Idempotent", "content": "once"}
    first = router.dispatch("notes.create", body, request_id="req-1", idempotency_key="key-1")
    assert first["ok"] is True
    second = router.dispatch("notes.create", body, request_id="req-2", idempotency_key="key-1")
    assert second["ok"] is True
    assert second["data"]["id"] == first["data"]["id"]
    assert dict(second) == dict(first)
    assert len(vault.live_nodes()) == 1

    conflict = router.dispatch(
        "notes.create",
        {"title": "Different"},
        request_id="req-3",
        idempotency_key="key-1",
    )
    assert conflict["ok"] is False
    assert conflict["error"]["code"] == "idempotency_conflict"
    assert len(vault.live_nodes()) == 1


def test_api_v2_compatibility_dispatch_without_changing_v1(vault: Vault) -> None:
    api = Api(vault)
    versioned = api.handle("v2:system.health", {})
    assert versioned["ok"] is True
    assert versioned["meta"]["api_version"] == API_VERSION
    legacy = api.handle("boot", {})
    assert "meta" not in legacy
    assert legacy["version"]


def test_http_v2_envelope_headers_and_no_double_wrap(v2_server: tuple[int, Vault, Api]) -> None:
    port, _, _ = v2_server
    status, headers, raw = _request(
        port,
        "POST",
        "/api/v2/system/health",
        body={},
        headers={"X-Request-ID": "client-request-1"},
    )
    assert status == 200
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["meta"]["request_id"] == "client-request-1"
    assert headers["X-Request-ID"] == "client-request-1"
    assert headers["Cache-Control"] == "no-store"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert set(payload) == {"ok", "data", "meta"}


def test_http_v2_schema_and_capabilities(v2_server: tuple[int, Vault, Api]) -> None:
    port, _, _ = v2_server
    status, _, raw = _request(port, "POST", "/api/v2/system/api_schema", body={})
    assert status == 200
    schema = json.loads(raw)
    assert "system.health" in schema["data"]["route_names"]
    assert schema["data"]["routes"]

    status, _, raw = _request(port, "POST", "/api/v2/system/capabilities", body={})
    assert status == 200
    capabilities = json.loads(raw)
    assert capabilities["data"]["api_version"] == API_VERSION
    assert "pagination" in capabilities["data"]["features"]


def test_http_v2_notes_pagination(v2_server: tuple[int, Vault, Api]) -> None:
    port, vault, _ = v2_server
    ids = _seed_notes(vault)
    status, _, raw = _request(port, "POST", "/api/v2/notes/list", body={"limit": 3})
    assert status == 200
    first = json.loads(raw)
    assert [item["id"] for item in first["data"]] == ids[:3]
    next_cursor = first["meta"]["page"]["next"]
    assert next_cursor

    status, _, raw = _request(
        port,
        "POST",
        "/api/v2/notes/list",
        body={"limit": 3, "cursor": next_cursor},
    )
    assert status == 200
    second = json.loads(raw)
    assert [item["id"] for item in second["data"]] == ids[3:]


def test_http_v2_notes_get_not_found(v2_server: tuple[int, Vault, Api]) -> None:
    port, _, _ = v2_server
    status, headers, raw = _request(
        port,
        "POST",
        "/api/v2/notes/get",
        body={"id": 9999},
        headers={"X-Request-ID": "missing-note"},
    )
    assert status == 404
    payload = json.loads(raw)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"
    assert payload["error"]["request_id"] == "missing-note"
    assert headers["X-Request-ID"] == "missing-note"


def test_http_v2_unknown_routes_and_bad_bodies(v2_server: tuple[int, Vault, Api]) -> None:
    port, _, _ = v2_server
    status, _, raw = _request(port, "POST", "/api/v2/system/nope", body={})
    assert status == 404
    assert json.loads(raw)["error"]["code"] == "unknown_route"

    status, _, raw = _request(port, "POST", "/api/v2/system/health/extra", body={})
    assert status == 404
    assert json.loads(raw)["error"]["code"] == "unknown_route"

    status, _, raw = _request(
        port,
        "POST",
        "/api/v2/system/health",
        body=b"{}",
        headers={"Content-Type": "text/plain"},
    )
    assert status == 415
    assert json.loads(raw)["error"]["code"] == "unsupported_media_type"

    status, _, raw = _request(port, "POST", "/api/v2/system/health", body=b"{oops")
    assert status == 400
    assert json.loads(raw)["error"]["code"] == "invalid_json"

    status, _, raw = _request(port, "POST", "/api/v2/system/health", body=b"[]")
    assert status == 400
    assert json.loads(raw)["error"]["code"] == "invalid_json"

    status, _, raw = _request(port, "POST", "/api/v2/notes/get", body={})
    assert status == 400
    assert json.loads(raw)["error"]["code"] == "invalid_type"


def test_http_v2_request_id_is_sanitized_and_capped(v2_server: tuple[int, Vault, Api]) -> None:
    port, _, _ = v2_server
    status, headers, raw = _request(
        port,
        "POST",
        "/api/v2/system/health",
        body={},
        headers={"X-Request-ID": "bad id!"},
    )
    assert status == 200
    assert headers["X-Request-ID"].startswith("req_")
    assert json.loads(raw)["meta"]["request_id"] == headers["X-Request-ID"]

    long_id = "a" * 300
    status, headers, raw = _request(
        port,
        "POST",
        "/api/v2/system/health",
        body={},
        headers={"X-Request-ID": long_id},
    )
    assert status == 200
    assert headers["X-Request-ID"] == "a" * 128
    assert json.loads(raw)["meta"]["request_id"] == "a" * 128


def test_http_v2_idempotent_replay(v2_server: tuple[int, Vault, Api]) -> None:
    port, vault, _ = v2_server
    body = {"title": "HTTP idempotent", "content": "payload"}
    headers = {"Idempotency-Key": "http-key-1"}
    status, _, first_raw = _request(
        port,
        "POST",
        "/api/v2/notes/create",
        body=body,
        headers=headers,
    )
    assert status == 200
    status, _, second_raw = _request(
        port,
        "POST",
        "/api/v2/notes/create",
        body=body,
        headers=headers,
    )
    assert status == 200
    assert second_raw == first_raw
    assert len(vault.live_nodes()) == 1

    status, _, conflict_raw = _request(
        port,
        "POST",
        "/api/v2/notes/create",
        body={"title": "different"},
        headers=headers,
    )
    assert status == 409
    assert json.loads(conflict_raw)["error"]["code"] == "idempotency_conflict"
    assert len(vault.live_nodes()) == 1


def test_http_v1_compatibility_is_unchanged(v2_server: tuple[int, Vault, Api]) -> None:
    port, _, _ = v2_server
    status, headers, raw = _request(port, "POST", "/api/boot", body={})
    assert status == 200
    assert headers["X-Content-Type-Options"] == "nosniff"
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert "data" in payload
    assert "meta" not in payload
    assert payload["data"]["version"]
