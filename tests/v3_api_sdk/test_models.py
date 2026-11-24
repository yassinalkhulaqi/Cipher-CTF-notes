"""Typed request, response, and page value objects."""

from __future__ import annotations

from typing import Any

import pytest

from redscribe.v3.api.envelope import PageMeta
from redscribe.v3.api.errors import V3Error
from redscribe.v3.api_sdk.models import (
    PageResult,
    SdkRequest,
    SdkResponse,
    coerce_body,
    require_name,
)


def test_require_name_accepts_and_rejects_tokens() -> None:
    assert require_name("extensions", "namespace") == "extensions"
    assert require_name("list_manifests", "action") == "list_manifests"
    for value in ("Bad", "x", "with space", "dash-name", 7, None):
        with pytest.raises(V3Error):
            require_name(value, "namespace")


def test_request_fields_route_and_headers() -> None:
    request = SdkRequest(
        "extensions",
        "list",
        body={"offset": 0},
        headers={"X-Request-ID": "req_custom", "X-Capability": "extensions"},
        capability="extensions",
        etag='"abc"',
        idempotency_key="key-1",
    )
    assert request.route == "/api/v3/extensions/list"
    assert request.header("x-request-id") == "req_custom"
    assert request.header("X-Missing") == ""
    assert request.idempotency_key == "key-1"
    payload = request.as_dict()
    assert payload["body"] == {"offset": 0}
    assert payload["capability"] == "extensions"
    assert payload["etag"] == '"abc"'


def test_request_rejects_bad_tokens_on_construction() -> None:
    with pytest.raises(V3Error):
        SdkRequest("Bad Namespace", "list")
    with pytest.raises(V3Error):
        SdkRequest("extensions", "1bad")


def test_request_with_page_preserves_metadata() -> None:
    request = SdkRequest(
        "extensions",
        "list",
        body={"filter": "x", "cursor": "stale", "size": 5},
        headers={"X-Request-ID": "req_1"},
        capability="extensions",
        etag='"tag"',
        idempotency_key="key",
    )
    first = request.with_page(0, 10)
    assert first.body == {"filter": "x", "offset": 0, "size": 10}
    second = request.with_page(20, 10, cursor="cursor_123")
    assert second.body == {"filter": "x", "cursor": "cursor_123"}
    assert second.capability == "extensions"
    assert second.etag == '"tag"'
    assert second.idempotency_key == "key"
    assert second.headers == {"X-Request-ID": "req_1"}


def test_coerce_body_handles_none_and_rejects_scalars() -> None:
    assert coerce_body(None) == {}
    assert coerce_body({"a": 1}) == {"a": 1}
    with pytest.raises(V3Error):
        coerce_body([1, 2, 3])  # type: ignore[arg-type]


def test_response_flags_and_rendering() -> None:
    ok = SdkResponse("system", "info", data={"ok": True}, request_id="req_1")
    assert ok.ok
    assert not ok.not_modified
    assert ok.code == ""
    rendered = ok.as_dict()
    assert rendered["data"] == {"ok": True}
    assert rendered["status"] == 200

    stale = SdkResponse("system", "info", status=304, etag='"tag"')
    assert stale.ok
    assert stale.not_modified

    failed = SdkResponse(
        "system",
        "info",
        status=403,
        request_id="req_2",
        error=_error_detail(),
    )
    assert not failed.ok
    assert failed.code == "forbidden"
    assert failed.as_dict()["error"]["field"] == "capability"


def _error_detail() -> Any:
    from redscribe.v3.api.envelope import ErrorDetail

    return ErrorDetail(code="forbidden", message="Denied", field_name="capability")


def test_page_meta_and_page_result() -> None:
    meta = PageMeta.for_window(0, 10, 25)
    assert meta.page == 1
    assert meta.has_next
    assert not meta.has_previous
    result = PageResult(
        items=(1, 2, 3),
        page=meta,
        next_cursor="cursor",
        etag='"tag"',
        request_id="req_1",
    )
    rendered = result.as_dict()
    assert rendered["items"] == [1, 2, 3]
    assert rendered["page"]["total"] == 25
    assert rendered["next_cursor"] == "cursor"
    assert PageResult(()).as_dict()["page"] is None
