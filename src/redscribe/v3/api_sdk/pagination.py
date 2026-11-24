"""Cursor-driven page iteration built on the B00 opaque cursor helpers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any

from redscribe.v3.api.pagination import decode_cursor
from redscribe.v3.api_sdk.models import PageResult, SdkRequest, SdkResponse

if TYPE_CHECKING:
    from redscribe.v3.api_sdk.client import SdkClient


def cursor_of(response: SdkResponse) -> str:
    """Read and validate a next-page cursor from response data."""
    data = response.data
    if not isinstance(data, Mapping):
        return ""
    cursor = data.get("next_cursor", "")
    if not isinstance(cursor, str) or not cursor:
        return ""
    decode_cursor(cursor)
    return cursor


def items_of(response: SdkResponse) -> tuple[Any, ...]:
    """Read list items from a page response."""
    data = response.data
    if isinstance(data, (list, tuple)):
        return tuple(data)
    if isinstance(data, Mapping):
        raw = data.get("items", ())
        if isinstance(raw, (list, tuple)):
            return tuple(raw)
    return ()


def next_page_request(
    response: SdkResponse,
    request: SdkRequest,
    *,
    options: Mapping[str, Any] | None = None,
) -> SdkRequest | None:
    """Build the next request, or return None when the list is exhausted."""
    cursor = cursor_of(response)
    if cursor:
        decoded = decode_cursor(cursor)
        return request.with_page(decoded.offset, decoded.size, cursor=cursor)
    page = response.page
    if page is not None and page.has_next:
        return request.with_page(page.page * page.page_size, page.page_size)
    return None


def to_page(response: SdkResponse) -> PageResult[Any]:
    """Convert one response into a typed page."""
    return PageResult(
        items=items_of(response),
        page=response.page,
        next_cursor=cursor_of(response),
        etag=response.etag,
        request_id=response.request_id,
    )


def iter_pages(
    client: SdkClient,
    request: SdkRequest,
    *,
    max_pages: int = 50,
    options: Mapping[str, Any] | None = None,
) -> Iterator[PageResult[Any]]:
    """Yield pages until the cursor ends or the page budget is consumed."""
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    shared = dict(options or {})
    current = request
    for _ in range(max_pages):
        response = client.call(
            current.namespace,
            current.action,
            current.body,
            **shared,
        )
        yield to_page(response)
        following = next_page_request(response, current, options=shared)
        if following is None:
            return
        current = following


def collect_pages(
    client: SdkClient,
    request: SdkRequest,
    *,
    max_pages: int = 50,
    options: Mapping[str, Any] | None = None,
) -> PageResult[Any]:
    """Flatten multiple pages into one result."""
    merged: list[Any] = []
    last: PageResult[Any] = PageResult(())
    for page in iter_pages(client, request, max_pages=max_pages, options=options):
        merged.extend(page.items)
        last = page
    return PageResult(
        items=tuple(merged),
        page=last.page,
        next_cursor=last.next_cursor,
        etag=last.etag,
        request_id=last.request_id,
    )
