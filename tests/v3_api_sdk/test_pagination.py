"""Pagination helpers built on B00 signed opaque cursors."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from redscribe.v3.api.envelope import PageMeta, success
from redscribe.v3.api.errors import V3Error
from redscribe.v3.api.pagination import PageRequest, encode_cursor, paginate
from redscribe.v3.api.router import V3Router
from redscribe.v3.api_sdk.client import SdkClient
from redscribe.v3.api_sdk.models import SdkRequest, SdkResponse
from redscribe.v3.api_sdk.pagination import (
    collect_pages,
    cursor_of,
    items_of,
    iter_pages,
    next_page_request,
    to_page,
)
from redscribe.v3.api_sdk.transport import InProcessTransport


def _register_list_route(router: V3Router, count: int = 10) -> None:
    def list_items(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        request = PageRequest.parse(
            offset=body.get("offset"),
            size=body.get("size"),
            cursor=str(body.get("cursor", "")),
        )
        values = tuple({"n": index} for index in range(count))
        window, meta, cursor = paginate(values, request)
        return success(
            {"items": list(window), "next_cursor": cursor},
            page=meta,
            request_id=headers.get("X-Request-ID", ""),
        ).as_dict()

    router.add("demo", "list", list_items)


def _client() -> SdkClient:
    router = V3Router()
    _register_list_route(router)
    return SdkClient(transport=InProcessTransport(router=router))


def test_client_list_collects_all_pages() -> None:
    client = _client()
    result = client.list("demo", "list", {}, size=3, max_pages=10)
    assert [item["n"] for item in result.items] == list(range(10))
    assert result.page is not None
    assert result.page.total == 10
    assert result.request_id.startswith("req_")


def test_client_pages_iterates_signed_cursors() -> None:
    client = _client()
    pages = list(client.pages("demo", "list", size=4, max_pages=10))
    assert len(pages) == 3
    assert [len(page.items) for page in pages] == [4, 4, 2]
    assert pages[0].next_cursor
    assert pages[-1].next_cursor == ""


def test_iter_pages_respects_page_budget() -> None:
    client = _client()
    request = SdkRequest("demo", "list").with_page(0, 2)
    pages = list(iter_pages(client, request, max_pages=1))
    assert len(pages) == 1
    with pytest.raises(ValueError):
        list(iter_pages(client, request, max_pages=0))


def test_collect_pages_combines_items() -> None:
    client = _client()
    request = SdkRequest("demo", "list").with_page(0, 5)
    merged = collect_pages(client, request)
    assert len(merged.items) == 10
    assert merged.page is not None
    assert merged.page.total == 10


def test_cursor_of_rejects_tampered_cursor() -> None:
    request = SdkRequest("demo", "list").with_page(0, 2, cursor="not-a-cursor")
    with pytest.raises(V3Error) as excinfo:
        cursor_of(SdkResponse("demo", "list", data={"next_cursor": "not-a-cursor"}))
    assert excinfo.value.code.value == "invalid_cursor"
    with pytest.raises(V3Error):
        next_page_request(SdkResponse("demo", "list", data={"next_cursor": "bad"}), request)


def test_next_page_request_uses_cursor_offset_and_size() -> None:
    cursor = encode_cursor(8, 2)
    response = SdkResponse("demo", "list", data={"next_cursor": cursor})
    request = SdkRequest("demo", "list").with_page(6, 2)
    following = next_page_request(response, request)
    assert following is not None
    assert following.body["cursor"] == cursor
    assert "offset" not in following.body


def test_next_page_request_falls_back_to_page_meta() -> None:
    page = PageMeta.for_window(0, 5, 10)
    response = SdkResponse("demo", "list", page=page)
    request = SdkRequest("demo", "list").with_page(0, 5)
    following = next_page_request(response, request)
    assert following is not None
    assert following.body["offset"] == 5
    assert following.body["size"] == 5
    assert (
        next_page_request(SdkResponse("demo", "list", page=PageMeta.for_window(5, 5, 10)), request)
        is None
    )


def test_items_of_supports_multiple_shapes() -> None:
    assert items_of(SdkResponse("a", "b", data=[1, 2])) == (1, 2)
    assert items_of(SdkResponse("a", "b", data={"items": (3, 4)})) == (3, 4)
    assert items_of(SdkResponse("a", "b", data={"items": "bad"})) == ()
    assert items_of(SdkResponse("a", "b", data=None)) == ()


def test_to_page_converts_response_fields() -> None:
    cursor = encode_cursor(2, 2)
    response = SdkResponse(
        "demo",
        "list",
        data={"items": [1, 2], "next_cursor": cursor},
        etag='"tag"',
        request_id="req_1",
        page=PageMeta.for_window(0, 2, 10),
    )
    page = to_page(response)
    assert page.items == (1, 2)
    assert page.next_cursor == cursor
    assert page.etag == '"tag"'
    assert page.as_dict()["request_id"] == "req_1"
