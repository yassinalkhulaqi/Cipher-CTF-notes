"""Typed client facade with history, pagination, and conditional requests."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from redscribe.v3.api_sdk.envelopes import render_envelope
from redscribe.v3.api_sdk.errors import SdkError
from redscribe.v3.api_sdk.history import CallLog
from redscribe.v3.api_sdk.models import PageResult, SdkRequest, SdkResponse
from redscribe.v3.api_sdk.pagination import iter_pages
from redscribe.v3.api_sdk.transport import InProcessTransport, Transport
from redscribe.v3.clock import Clock, SystemClock


class SdkClient:
    """Calls API v3 routes through a local transport and records history."""

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        history_limit: int = 200,
        clock: Clock | None = None,
    ) -> None:
        self.transport: Transport = transport or InProcessTransport()
        self.history = CallLog(limit=history_limit, clock=clock)
        self._clock: Clock = clock or SystemClock()

    def call(
        self,
        namespace: str,
        action: str,
        body: Mapping[str, Any] | None = None,
        *,
        capability: str = "",
        etag: str = "",
        idempotency_key: str = "",
        headers: Mapping[str, str] | None = None,
        allow_errors: bool = False,
    ) -> SdkResponse:
        """Execute a call, raising on error unless explicitly allowed."""
        request = SdkRequest(
            namespace=namespace,
            action=action,
            body=dict(body or {}),
            headers=dict(headers or {}),
            capability=capability,
            etag=etag,
            idempotency_key=idempotency_key,
        )
        started = self._clock.now_timestamp()
        response = self.transport.call(request)
        duration_ms = (self._clock.now_timestamp() - started) * 1000.0
        self.history.record(request, response, duration_ms)
        if not response.ok and not allow_errors:
            raise SdkError.from_response(response)
        return response

    def data(
        self,
        namespace: str,
        action: str,
        body: Mapping[str, Any] | None = None,
        **options: Any,
    ) -> Any:
        """Return just the data portion of a successful call."""
        return self.call(namespace, action, body, **options).data

    def envelope(
        self,
        namespace: str,
        action: str,
        body: Mapping[str, Any] | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        """Return the B00 envelope rendering of a call."""
        return render_envelope(self.call(namespace, action, body, **options))

    def list(
        self,
        namespace: str,
        action: str,
        body: Mapping[str, Any] | None = None,
        *,
        size: int = 50,
        max_pages: int = 1,
        **options: Any,
    ) -> PageResult[Any]:
        """Return one or more pages as a flattened typed result."""
        request = SdkRequest(namespace, action, dict(body or {})).with_page(0, size)
        collected: list[Any] = []
        last: PageResult[Any] = PageResult(())
        for page in iter_pages(self, request, max_pages=max_pages, options=options):
            collected.extend(page.items)
            last = page
        return PageResult(
            items=tuple(collected),
            page=last.page,
            next_cursor=last.next_cursor,
            etag=last.etag,
            request_id=last.request_id,
        )

    def pages(
        self,
        namespace: str,
        action: str,
        body: Mapping[str, Any] | None = None,
        *,
        size: int = 50,
        max_pages: int = 50,
    ) -> Iterator[PageResult[Any]]:
        """Iterate pages using signed opaque cursors from B00."""
        request = SdkRequest(namespace, action, dict(body or {})).with_page(0, size)
        yield from iter_pages(self, request, max_pages=max_pages)

    def call_history(self) -> tuple[Any, ...]:
        """Return sanitized history records."""
        return self.history.entries()
