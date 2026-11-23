"""Tests for V3 envelopes, errors, pagination, and idempotency."""

from __future__ import annotations

import pytest

from redscribe.v3.api.envelope import (
    API_VERSION,
    ErrorDetail,
    PageMeta,
    ResponseMeta,
    failure,
    is_envelope,
    success,
    unwrap,
)
from redscribe.v3.api.errors import V3Error, V3ErrorCode, all_codes, status_for
from redscribe.v3.api.idempotency import (
    IdempotencyGuard,
    MemoryIdempotencyStore,
    compute_etag,
    etag_matches,
    version_etag,
)
from redscribe.v3.api.pagination import (
    MAX_PAGE_SIZE,
    PageRequest,
    decode_cursor,
    encode_cursor,
    filter_hash,
    paginate,
)
from redscribe.v3.api.request_id import (
    RateLimiter,
    new_request_id,
    normalize_request_id,
    optional_str,
    optional_tags,
    require_bool,
    require_choice,
    require_str,
)


def test_success_envelope() -> None:
    response = success({"id": "a"}, request_id="req_1", etag='"abc"')
    payload = response.as_dict()
    assert payload["data"] == {"id": "a"}
    assert payload["meta"]["request_id"] == "req_1"
    assert payload["meta"]["api_version"] == API_VERSION
    assert payload["meta"]["etag"] == '"abc"'
    assert is_envelope(payload)
    assert unwrap(payload) == {"id": "a"}


def test_envelope_with_dataclass_and_list() -> None:
    detail = ErrorDetail(code="x", message="y", field_name="z")
    wrapped = success(detail).as_dict()
    assert wrapped["data"]["code"] == "x"
    listed = success([detail]).as_dict()
    assert listed["data"][0]["message"] == "y"


def test_envelope_rejects_non_envelope() -> None:
    assert not is_envelope({"data": 1})
    with pytest.raises(ValueError):
        unwrap({"data": 1})


def test_error_envelope_and_v3_error() -> None:
    error = V3Error.missing("title")
    payload = error.envelope("req_2").as_dict()
    assert payload["error"]["code"] == "missing_field"
    assert payload["error"]["field"] == "title"
    assert error.status == 400
    assert V3Error.not_found("finding").code is V3ErrorCode.NOT_FOUND
    assert V3Error.invalid("x", "bad").field == "x"
    built = failure("custom", "oops", status=503, retryable=True)
    assert built.error.retryable is True
    assert built.status == 503


def test_error_code_status_table() -> None:
    assert status_for(V3ErrorCode.NOT_FOUND) == 404
    assert status_for(V3ErrorCode.CONFLICT) == 409
    assert status_for(V3ErrorCode.RATE_LIMITED) == 429
    assert status_for(V3ErrorCode.INTERNAL) == 500
    assert "unknown_route" in all_codes()
    assert all_codes() == tuple(sorted(all_codes()))


def test_page_meta() -> None:
    page = PageMeta.for_window(offset=20, size=10, total=50)
    assert page.page == 3
    assert page.has_next is True
    assert page.has_previous is True
    assert page.as_dict()["total"] == 50
    with pytest.raises(ValueError):
        PageMeta(page=0)
    with pytest.raises(ValueError):
        PageMeta(total=-1)


def test_response_meta_warnings() -> None:
    meta = ResponseMeta(request_id="r", etag='"e"', warnings=("slow",)).as_dict()
    assert meta["warnings"] == ["slow"]
    assert ResponseMeta().as_dict()["api_version"] == API_VERSION


def test_page_request_parse() -> None:
    assert PageRequest.parse().size == 50
    parsed = PageRequest.parse(offset="10", size="25")
    assert parsed.offset == 10
    assert parsed.size == 25
    with pytest.raises(V3Error):
        PageRequest.parse(offset="-1")
    with pytest.raises(V3Error):
        PageRequest.parse(size=str(MAX_PAGE_SIZE + 1))
    with pytest.raises(V3Error):
        PageRequest.parse(size="abc")


def test_cursor_roundtrip_and_tamper() -> None:
    cursor = encode_cursor(40, 20, filter_hash="abc")
    decoded = decode_cursor(cursor)
    assert decoded.offset == 40
    assert decoded.size == 20
    assert decoded.filter_hash == "abc"
    with pytest.raises(V3Error):
        decode_cursor("not-a-cursor")
    tampered = cursor[:-2] + "xx"
    with pytest.raises(V3Error):
        decode_cursor(tampered)
    parsed = PageRequest.parse(cursor=cursor)
    assert parsed.offset == 40


def test_paginate() -> None:
    items = tuple(range(10))
    window, meta, next_cursor = paginate(items, PageRequest(offset=0, size=4))
    assert window == (0, 1, 2, 3)
    assert meta.has_next is True
    assert next_cursor
    last_window, last_meta, last_cursor = paginate(items, PageRequest(offset=8, size=4))
    assert last_window == (8, 9)
    assert last_meta.has_next is False
    assert last_cursor == ""
    assert filter_hash("a", ("note",)) == filter_hash("a", ("note",))
    assert filter_hash("a") != filter_hash("b")


def test_idempotency_guard() -> None:
    guard = IdempotencyGuard(MemoryIdempotencyStore())
    calls: list[int] = []

    def operation() -> dict[str, int]:
        calls.append(1)
        return {"ok": 1}

    first, cached = guard.execute("key-1", {"a": 1}, operation)
    second, cached_again = guard.execute("key-1", {"a": 1}, operation)
    assert first == second
    assert cached is False
    assert cached_again is True
    assert len(calls) == 1
    with pytest.raises(V3Error):
        guard.execute("key-1", {"a": 2}, operation)
    with pytest.raises(V3Error):
        guard.execute("", {}, operation)


def test_etag_helpers() -> None:
    etag = compute_etag({"a": 1})
    assert etag.startswith('"')
    assert etag_matches(etag, etag)
    assert etag_matches("*", etag)
    assert etag_matches(f"W/{etag}", etag)
    assert not etag_matches('"other"', etag)
    assert version_etag(1, 10.0) == version_etag(1, 10.0)
    assert version_etag(1, 10.0) != version_etag(2, 10.0)


def test_request_id_helpers() -> None:
    assert new_request_id().startswith("req_")
    assert normalize_request_id(None).startswith("req_")
    assert normalize_request_id("req_abc") == "req_abc"
    with pytest.raises(V3Error):
        normalize_request_id("bad id!")


def test_validation_helpers() -> None:
    payload = {"title": "  Hello   World ", "kind": "note", "flag": True, "tags": [" A ", "b"]}
    assert require_str(payload, "title") == "Hello World"
    assert require_choice(payload, "kind", ("note", "finding")) == "note"
    assert require_bool(payload, "flag") is True
    assert optional_tags(payload) == ("a", "b")
    assert optional_str(payload, "missing") == ""
    with pytest.raises(V3Error):
        require_str(payload, "missing")
    with pytest.raises(V3Error):
        require_choice(payload, "kind", ("finding",))
    with pytest.raises(V3Error):
        optional_tags({"tags": "not-a-list"})
    with pytest.raises(V3Error):
        require_bool({"flag": "yes"}, "flag")


def test_rate_limiter() -> None:
    limiter = RateLimiter(limit=2, window_seconds=10.0)
    assert limiter.allow("alice", 0.0) is True
    assert limiter.allow("alice", 1.0) is True
    assert limiter.allow("alice", 2.0) is False
    assert limiter.remaining("alice", 2.0) == 0
    with pytest.raises(V3Error):
        limiter.enforce("alice", 3.0)
    assert limiter.allow("alice", 11.0) is True
    limiter.reset("alice")
    assert limiter.remaining("alice", 11.0) == 2
    limiter.reset()
    with pytest.raises(ValueError):
        RateLimiter(limit=0)
