from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection

import pytest

from redscribe.ui.web.server import ApiServer, static_asset_bytes, static_asset_exists

_BACKUP = b"SQLite format 3\x00backup"


def _request(
    port: int,
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
    token: str | None = None,
    host: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    headers: dict[str, str] = {}
    if method == "POST":
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["X-RedScribe-Token"] = token
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    if host is not None:
        connection.putrequest(method, path, skip_host=True)
        connection.putheader("Host", host)
        for key, value in headers.items():
            connection.putheader(key, value)
        if payload is not None:
            connection.putheader("Content-Length", str(len(payload)))
        connection.endheaders()
        if payload is not None:
            connection.send(payload)
    else:
        connection.request(method, path, body=payload, headers=headers)
    response = connection.getresponse()
    status = response.status
    response_headers = dict(response.getheaders())
    data = response.read()
    connection.close()
    return status, response_headers, data


@pytest.fixture
def web_server() -> Iterator[tuple[int, str]]:
    def dispatch(method: str, body: dict[str, object]) -> object:
        if method == "boot":
            return {"version": "test"}
        if method == "export_note_markdown":
            return {"content": "# note", "filename": "note.md", "mime": "text/markdown"}
        raise AssertionError(f"Unexpected API method: {method}")

    server = ApiServer(
        ("127.0.0.1", 0),
        dispatch,
        token="s3cr3t",
        backup=lambda: _BACKUP,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.bound_port, "s3cr3t"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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
    assert static_asset_bytes("../server.py") is None


def test_index_injects_token_and_sets_security_headers(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, headers, body = _request(port, "GET", "/")
    assert status == 200
    assert f'data-redscribe-token="{token}"'.encode() in body
    assert b"__REDSCRIBE_TOKEN__" not in body
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in headers


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


def test_foreign_host_is_rejected(web_server: tuple[int, str]) -> None:
    port, _ = web_server
    status, _, _ = _request(port, "GET", "/", host="evil.example")
    assert status == 403


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


def test_sqlite_download_streams_backup(web_server: tuple[int, str]) -> None:
    port, token = web_server
    status, headers, body = _request(port, "GET", f"/download/vault/sqlite?token={token}")
    assert status == 200
    assert body == _BACKUP
    assert headers["Content-Type"] == "application/x-sqlite3"
