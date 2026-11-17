from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from redscribe.ui.web.api import ApiError
from redscribe.ui.web.auth import (
    ANY_PURPOSE,
    DOWNLOAD_PURPOSE,
    SESSION_PURPOSE,
    AuthOutcome,
    TokenManager,
)
from redscribe.ui.web.security import (
    EVENT_AUTH_FAILURE,
    EVENT_AUTH_SUCCESS,
    EVENT_HOST_REJECTED,
    EVENT_RATE_LIMITED,
    EVENT_STATIC_REJECTED,
    AuditLog,
    AuthRateLimiter,
    content_disposition,
    content_security_policy,
    safe_download_filename,
    safe_mime_type,
    safe_static_path,
)
from redscribe.ui.web.server import (
    ApiServer,
    static_asset_bytes,
    static_asset_exists,
)

_BACKUP = b"SQLite format 3\x00backup"
_TOKEN = "s3cr3t"


class _Clock:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@dataclass(slots=True)
class _Export:
    filename: str
    mime: str

    def payload(self) -> dict[str, str]:
        return {"content": "# note", "filename": self.filename, "mime": self.mime}


def _request(
    port: int,
    method: str,
    path: str,
    *,
    body: dict[str, object] | bytes | None = None,
    token: str | None = None,
    host: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    request_headers = dict(headers or {})
    if method == "POST" and "Content-Type" not in request_headers:
        request_headers["Content-Type"] = "application/json"
    if token is not None:
        request_headers["X-RedScribe-Token"] = token
    payload: bytes | None
    if isinstance(body, dict):
        payload = json.dumps(body).encode("utf-8")
    elif isinstance(body, bytes):
        payload = body
    else:
        payload = None

    if host is not None:
        connection.putrequest(method, path, skip_host=True)
        connection.putheader("Host", host)
        for key, value in request_headers.items():
            connection.putheader(key, value)
        if payload is not None:
            connection.putheader("Content-Length", str(len(payload)))
        connection.endheaders()
        if payload is not None:
            connection.send(payload)
    else:
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


def _dispatch(method: str, body: dict[str, Any]) -> object:
    if method == "boot":
        return {"version": "test"}
    if method in {"export_note_markdown", "export_note_html", "export_vault_html"}:
        return {"content": "# note", "filename": "note.md", "mime": "text/markdown"}
    raise ApiError("Not found", status=404)


@pytest.fixture
def web_server() -> Iterator[tuple[int, str]]:
    with _running(
        ApiServer(
            ("127.0.0.1", 0),
            _dispatch,
            token=_TOKEN,
            backup=lambda: _BACKUP,
        )
    ) as port:
        yield port, _TOKEN


@pytest.fixture
def no_auth_server() -> Iterator[int]:
    with _running(ApiServer(("127.0.0.1", 0), _dispatch)) as port:
        yield port


@pytest.fixture
def limited_server() -> Iterator[tuple[int, ApiServer]]:
    server = ApiServer(
        ("127.0.0.1", 0),
        _dispatch,
        token=_TOKEN,
        rate_limiter=AuthRateLimiter(limit=3, lockout_seconds=60),
    )
    with _running(server) as port:
        yield port, server


@pytest.fixture
def ttl_server() -> Iterator[tuple[int, ApiServer, _Clock]]:
    clock = _Clock()
    manager = TokenManager(_TOKEN, ttl_seconds=10, clock=clock)
    audit = AuditLog(clock=clock)
    server = ApiServer(("127.0.0.1", 0), _dispatch, tokens=manager, audit_log=audit)
    with _running(server) as port:
        yield port, server, clock


@pytest.fixture
def export_server() -> Iterator[int]:
    export = _Export("../../evil.txt", "text/plain\r\nX-Evil: 1")

    def dispatch(method: str, body: dict[str, Any]) -> object:
        if method == "export_note_markdown":
            return export.payload()
        raise ApiError("Not found", status=404)

    with _running(ApiServer(("127.0.0.1", 0), dispatch, token=_TOKEN)) as port:
        yield port


def test_nested_frontend_assets_are_packaged() -> None:
    assert static_asset_exists("index.html")
    assert static_asset_exists("assets/app.js")
    assert static_asset_exists("assets/app.css")
    assert static_asset_exists("favicon.svg")
    assert static_asset_exists("manifest.webmanifest")
    assert static_asset_bytes("assets/app.js")


def test_static_paths_cannot_escape_the_bundle() -> None:
    assert not static_asset_exists("../server.py")
    assert not static_asset_exists("assets/../../server.py")
    assert not static_asset_exists("/etc/passwd")
    assert not static_asset_exists("assets\\app.js")
    assert not static_asset_exists("assets/.")
    assert not static_asset_exists(".env")
    assert not static_asset_exists("assets/\x00app.js")
    assert static_asset_bytes("../server.py") is None


def test_static_path_refuses_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        (root / "linked.txt").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")
    assert safe_static_path(root, "linked.txt") is None
    assert safe_static_path(root, "missing.txt") is None


def test_index_injects_token_and_sets_security_headers(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, headers, body = _request(port, "GET", "/")
    assert status == 200
    assert f'data-redscribe-token="{token}"'.encode() in body
    assert b"__REDSCRIBE_TOKEN__" not in body
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert "camera=()" in headers["Permissions-Policy"]
    assert headers["Cache-Control"] == "no-store"
    assert "Content-Security-Policy" in headers


def test_csp_nonce_is_fresh_and_matches_script_tag(web_server: tuple[int, str]) -> None:
    port, _ = web_server
    _, first_headers, first_body = _request(port, "GET", "/")
    _, second_headers, second_body = _request(port, "GET", "/")
    first = re.search(rb'<script nonce="([^"]+)"', first_body)
    second = re.search(rb'<script nonce="([^"]+)"', second_body)
    assert first is not None
    assert second is not None
    first_nonce = first.group(1).decode("ascii")
    second_nonce = second.group(1).decode("ascii")
    assert first_nonce != second_nonce
    assert f"'nonce-{first_nonce}'" in first_headers["Content-Security-Policy"]
    assert f"'nonce-{second_nonce}'" in second_headers["Content-Security-Policy"]
    assert "object-src 'none'" in first_headers["Content-Security-Policy"]


def test_token_is_html_escaped_in_index() -> None:
    unsafe = 'a"b<c>'
    with _running(ApiServer(("127.0.0.1", 0), _dispatch, token=unsafe)) as port:
        _, _, body = _request(port, "GET", "/")
    assert b'data-redscribe-token="a&quot;b&lt;c&gt;"' in body
    assert b'data-redscribe-token="a"b<c>"' not in body


def test_api_requires_session_token(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, _, _ = _request(port, "POST", "/api/boot", body={})
    assert status == 403
    status, _, _ = _request(port, "POST", "/api/boot", body={}, token="wrong")
    assert status == 403
    status, _, body = _request(port, "POST", "/api/boot", body={}, token=token)
    assert status == 200
    assert b'"ok": true' in body


def test_api_accepts_beacon_token_in_query(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, _, body = _request(port, "POST", f"/api/boot?token={token}", body={})
    assert status == 200
    assert b'"ok": true' in body


def test_header_token_takes_precedence_over_query(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, _, _ = _request(port, "POST", "/api/boot?token=wrong", body={}, token=token)
    assert status == 200
    status, _, _ = _request(port, "POST", f"/api/boot?token={token}", body={}, token="wrong")
    assert status == 403


def test_missing_auth_is_disabled_when_no_token_configured(no_auth_server: int) -> None:
    status, _, body = _request(no_auth_server, "POST", "/api/boot", body={})
    assert status == 200
    assert b'"ok": true' in body
    _, _, index = _request(no_auth_server, "GET", "/")
    assert b'data-redscribe-token=""' in index
    assert b"__REDSCRIBE_TOKEN__" not in index


def test_foreign_host_is_rejected_and_audited(web_server: tuple[int, str]) -> None:
    port, _ = web_server
    status, _, _ = _request(port, "GET", "/", host="evil.example")
    assert status == 403
    status, _, _ = _request(port, "GET", "/", host="user@127.0.0.1")
    assert status == 403
    status, _, _ = _request(port, "GET", "/", host="127.0.0.1.evil.example")
    assert status == 403
    status, _, _ = _request(port, "GET", "/", host=f"localhost:{port}")
    assert status == 200


def test_host_rejection_creates_audit_record() -> None:
    server = ApiServer(("127.0.0.1", 0), _dispatch, token=_TOKEN)
    with _running(server) as port:
        _request(port, "GET", "/", host="evil.example")
    events = server.audit.as_dicts()
    assert len(events) == 1
    assert events[0]["kind"] == EVENT_HOST_REJECTED
    assert events[0]["outcome"] == "rejected"
    assert set(events[0]) == {"at", "kind", "outcome", "client", "path", "detail"}


def test_download_requires_token_and_is_nosniff(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, _, _ = _request(port, "GET", "/download/note/1/md")
    assert status == 403
    status, headers, body = _request(port, "GET", f"/download/note/1/md?token={token}")
    assert status == 200
    assert b"# note" in body
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Type"].startswith("text/markdown")
    assert headers["Content-Disposition"].startswith("attachment;")
    assert headers["X-Frame-Options"] == "DENY"


def test_download_does_not_accept_header_token(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, _, _ = _request(port, "GET", "/download/note/1/md", token=token)
    assert status == 403


def test_sqlite_download_streams_backup(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, headers, body = _request(port, "GET", f"/download/vault/sqlite?token={token}")
    assert status == 200
    assert body == _BACKUP
    assert headers["Content-Type"] == "application/x-sqlite3"
    assert "redscribe-vault-" in headers["Content-Disposition"]


def test_static_asset_served_with_cache_headers(web_server: tuple[int, str]) -> None:
    port, _ = web_server
    status, headers, body = _request(port, "GET", "/assets/app.css")
    assert status == 200
    assert body
    assert headers["Cache-Control"] == "no-cache"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" not in headers


def test_static_traversal_is_rejected_and_audited() -> None:
    server = ApiServer(("127.0.0.1", 0), _dispatch, token=_TOKEN)
    with _running(server) as port:
        status, _, _ = _request(port, "GET", "/assets/../../server.py?token=" + _TOKEN)
        assert status == 404
        status, _, _ = _request(port, "GET", "/static/%2e%2e/server.py?token=" + _TOKEN)
        assert status == 404
    assert server.audit.count(kind=EVENT_STATIC_REJECTED) == 2


def test_failed_auth_events_are_audited() -> None:
    server = ApiServer(("127.0.0.1", 0), _dispatch, token=_TOKEN)
    with _running(server) as port:
        _request(port, "POST", "/api/boot", body={}, token="wrong")
        _request(port, "POST", "/api/boot", body={}, token=_TOKEN)
    assert server.audit.count(kind=EVENT_AUTH_FAILURE, outcome="invalid") == 1
    assert server.audit.count(kind=EVENT_AUTH_SUCCESS, outcome="accepted") == 1


def test_rate_limiter_blocks_after_repeated_failures(limited_server: tuple[int, ApiServer]) -> None:
    port, server = limited_server
    for _ in range(3):
        status, headers, _ = _request(port, "POST", "/api/boot", body={}, token="wrong")
        assert status == 403
    assert "Retry-After" in headers
    status, headers, body = _request(port, "POST", "/api/boot", body={}, token=_TOKEN)
    assert status == 429
    assert headers["Retry-After"].isdigit()
    assert b"Too many failed attempts" in body
    assert server.audit.count(kind=EVENT_RATE_LIMITED, outcome="blocked") == 1


def test_rate_limiter_success_resets_failures() -> None:
    limiter = AuthRateLimiter(limit=2, window_seconds=60, lockout_seconds=60)
    assert limiter.record_failure("client").allowed
    assert limiter.check("client").failures == 1
    limiter.record_success("client")
    assert limiter.check("client").failures == 0
    assert limiter.record_failure("client").allowed
    assert limiter.record_failure("client").blocked
    assert limiter.check("client").blocked


def test_rate_limiter_window_and_lockout_use_clock() -> None:
    clock = _Clock()
    limiter = AuthRateLimiter(
        limit=2,
        window_seconds=10,
        lockout_seconds=20,
        clock=clock,
    )
    limiter.record_failure("client")
    clock.advance(11)
    assert limiter.snapshot() == {}
    assert limiter.record_failure("client").allowed
    assert limiter.record_failure("client").blocked
    clock.advance(21)
    assert limiter.check("client").allowed
    assert limiter.snapshot() == {}


def test_token_manager_rotation_keeps_old_token_briefly() -> None:
    clock = _Clock()
    manager = TokenManager(_TOKEN, clock=clock)
    assert manager.current_token == _TOKEN
    assert manager.authenticate(_TOKEN, purpose=SESSION_PURPOSE) is AuthOutcome.ACCEPTED

    rotated = manager.rotate(grace_seconds=5)
    assert rotated != _TOKEN
    assert manager.current_token == rotated
    assert manager.authenticate(_TOKEN, purpose=SESSION_PURPOSE) is AuthOutcome.ACCEPTED
    assert manager.authenticate(rotated, purpose=SESSION_PURPOSE) is AuthOutcome.ACCEPTED
    assert manager.stats().retired == 1

    clock.advance(6)
    assert manager.authenticate(_TOKEN, purpose=SESSION_PURPOSE) is AuthOutcome.INVALID
    assert manager.stats().retired == 0
    assert manager.authenticate(rotated, purpose=SESSION_PURPOSE) is AuthOutcome.ACCEPTED


def test_token_manager_ttl_expires_session() -> None:
    clock = _Clock()
    manager = TokenManager(_TOKEN, ttl_seconds=10, clock=clock)
    assert manager.ttl_seconds == 10
    assert manager.authenticate(_TOKEN) is AuthOutcome.ACCEPTED
    clock.advance(10)
    assert manager.authenticate(_TOKEN) is AuthOutcome.EXPIRED
    assert not manager.stats().session_active
    with pytest.raises(RuntimeError):
        TokenManager(None).rotate()


def test_one_time_token_is_single_use_and_purpose_scoped() -> None:
    manager = TokenManager(_TOKEN)
    download = manager.issue_one_time(purpose=DOWNLOAD_PURPOSE)
    assert manager.authenticate(download, purpose=DOWNLOAD_PURPOSE) is AuthOutcome.ACCEPTED
    assert manager.authenticate(download, purpose=DOWNLOAD_PURPOSE) is AuthOutcome.CONSUMED
    assert manager.authenticate(download, purpose=ANY_PURPOSE) is AuthOutcome.CONSUMED

    api_token = manager.issue_one_time(purpose="api")
    assert manager.authenticate(api_token, purpose=DOWNLOAD_PURPOSE) is AuthOutcome.INVALID
    assert manager.authenticate(api_token, purpose="api") is AuthOutcome.ACCEPTED
    assert manager.authenticate(api_token, purpose="api") is AuthOutcome.CONSUMED


def test_one_time_token_expires_and_pool_is_bounded() -> None:
    clock = _Clock()
    manager = TokenManager(_TOKEN, one_time_ttl_seconds=10, max_one_time=2, clock=clock)
    first = manager.issue_one_time()
    second = manager.issue_one_time()
    third = manager.issue_one_time()
    assert manager.authenticate(first) is AuthOutcome.INVALID
    assert manager.authenticate(second) is AuthOutcome.ACCEPTED
    assert manager.authenticate(third) is AuthOutcome.ACCEPTED
    assert manager.stats().one_time == 2
    clock.advance(10)
    assert manager.authenticate(second) is AuthOutcome.EXPIRED
    assert manager.stats().one_time == 0


def test_one_time_download_token_over_http() -> None:
    server = ApiServer(("127.0.0.1", 0), _dispatch, token=_TOKEN)
    with _running(server) as port:
        one_time = server.issue_download_token()
        status, _, body = _request(port, "GET", f"/download/note/1/md?token={one_time}")
        assert status == 200
        assert b"# note" in body
        status, _, _ = _request(port, "GET", f"/download/note/1/md?token={one_time}")
        assert status == 403
        assert server.audit.count(kind=EVENT_AUTH_FAILURE, outcome="consumed") == 1
        status, _, _ = _request(port, "POST", "/api/boot", body={}, token=one_time)
        assert status == 403


def test_rotation_over_http_updates_index_and_keeps_grace() -> None:
    clock = _Clock()
    manager = TokenManager(_TOKEN, clock=clock)
    server = ApiServer(("127.0.0.1", 0), _dispatch, tokens=manager)
    with _running(server) as port:
        rotated = server.rotate_token(grace_seconds=5)
        _, _, index = _request(port, "GET", "/")
        assert f'data-redscribe-token="{rotated}"'.encode() in index
        assert _request(port, "POST", "/api/boot", body={}, token=_TOKEN)[0] == 200
        assert _request(port, "POST", "/api/boot", body={}, token=rotated)[0] == 200
        clock.advance(6)
        assert _request(port, "POST", "/api/boot", body={}, token=_TOKEN)[0] == 403
        assert _request(port, "POST", "/api/boot", body={}, token=rotated)[0] == 200


def test_expired_session_token_is_rejected_over_http(
    ttl_server: tuple[int, ApiServer, _Clock],
) -> None:
    port, server, clock = ttl_server
    assert _request(port, "POST", "/api/boot", body={}, token=_TOKEN)[0] == 200
    clock.advance(11)
    status, _, _ = _request(port, "POST", "/api/boot", body={}, token=_TOKEN)
    assert status == 403
    assert server.audit.count(kind=EVENT_AUTH_FAILURE, outcome="expired") == 1
    assert _request(port, "GET", f"/download/note/1/md?token={_TOKEN}")[0] == 403


def test_low_value_tokens_are_rejected() -> None:
    manager = TokenManager(_TOKEN)
    for presented in (None, "", "wrong", 123, "s3cr3t\n"):
        assert manager.authenticate(presented) is AuthOutcome.INVALID
    disabled = TokenManager(None)
    assert disabled.authenticate("anything") is AuthOutcome.DISABLED
    assert not disabled.enabled
    with pytest.raises(ValueError):
        TokenManager("")
    with pytest.raises(ValueError):
        TokenManager(_TOKEN, ttl_seconds=0)


def test_filename_validation_rejects_unsafe_values() -> None:
    fallback = "redscribe-export.txt"
    for candidate in (
        "../../evil.txt",
        "..\\evil.txt",
        "/etc/passwd",
        ".hidden",
        "note\r\nX: 1.txt",
        "note\x00.txt",
        "CON",
        "aux.txt",
        "trailing. ",
        "x" * 500,
        None,
        42,
    ):
        assert safe_download_filename(candidate) == fallback
    assert safe_download_filename("café — note.md") == "café — note.md"


def test_mime_validation_rejects_header_injection() -> None:
    assert safe_mime_type("text/plain") == "text/plain"
    assert safe_mime_type("application/x-sqlite3") == "application/x-sqlite3"
    assert safe_mime_type("text/plain\r\nX: 1") == "application/octet-stream"
    assert safe_mime_type("text/html<script>") == "application/octet-stream"
    assert safe_mime_type(None) == "application/octet-stream"


def test_content_disposition_has_ascii_fallback_and_rfc5987_name() -> None:
    header = content_disposition("café — note.md")
    assert header.startswith("attachment; filename=")
    assert "filename*=UTF-8''" in header
    assert "\r" not in header
    assert "\n" not in header
    assert content_disposition("../../evil.txt").endswith("redscribe-export.txt")


def test_malicious_export_metadata_is_sanitized(export_server: int) -> None:
    status, headers, body = _request(
        export_server,
        "GET",
        f"/download/note/1/md?token={_TOKEN}",
    )
    assert status == 200
    assert body == b"# note"
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    assert "evil" not in headers["Content-Disposition"]
    assert "redscribe-export.txt" in headers["Content-Disposition"]
    assert "\r" not in str(headers)


def test_post_content_type_must_be_json(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, _, _ = _request(
        port,
        "POST",
        "/api/boot",
        body=b"{}",
        token=token,
        headers={"Content-Type": "text/plain"},
    )
    assert status == 415


def test_post_malformed_json_is_rejected(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, _, _ = _request(port, "POST", "/api/boot", body=b"{oops", token=token)
    assert status == 400
    status, _, _ = _request(port, "POST", "/api/boot", body=b"[]", token=token)
    assert status == 400


def test_unknown_api_and_download_routes_are_not_found(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, _, _ = _request(port, "POST", "/api/no_such_method", body={}, token=token)
    assert status == 404
    status, _, _ = _request(port, "GET", f"/download/unknown?token={token}")
    assert status == 404
    status, _, _ = _request(port, "GET", f"/download/note/abc/md?token={token}")
    assert status == 404
    status, _, _ = _request(port, "GET", "/unknown.js")
    assert status == 404


def test_csp_builder_includes_all_directives() -> None:
    policy = content_security_policy(nonce="abc123")
    for directive in (
        "default-src 'self'",
        "script-src 'self' 'nonce-abc123'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    ):
        assert directive in policy
    assert "upgrade-insecure-requests" not in policy


def test_audit_log_is_bounded() -> None:
    log = AuditLog(capacity=2, clock=_Clock())
    for index in range(5):
        log.record("kind", f"outcome-{index}")
    assert len(log.snapshot()) == 2
    assert log.as_dicts()[0]["outcome"] == "outcome-3"
    assert log.count(kind="kind") == 2
    log.clear()
    assert log.count() == 0


def test_server_rejects_conflicting_token_arguments() -> None:
    manager = TokenManager(_TOKEN)
    with pytest.raises(ValueError):
        ApiServer(("127.0.0.1", 0), _dispatch, token=_TOKEN, tokens=manager)
