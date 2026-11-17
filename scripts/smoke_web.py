"""Smoke-test the packaged RedScribe web server over HTTP."""

from __future__ import annotations

import re
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api, WebOverrides
from redscribe.ui.web.security import AuthRateLimiter
from redscribe.ui.web.server import ApiServer


def _request(
    port: int,
    method: str,
    path: str,
    *,
    token: str | None = None,
    host: str | None = None,
    extra_headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        headers = dict(extra_headers or {})
        payload = body
        if method == "POST":
            headers.setdefault("Content-Type", "application/json")
            payload = b"{}" if payload is None else payload
        if token is not None:
            headers["X-RedScribe-Token"] = token
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
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def main() -> None:
    with (
        tempfile.TemporaryDirectory(prefix="redscribe-smoke-") as directory,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="redscribe-smoke") as executor,
    ):
        vault = executor.submit(Vault, Path(directory) / "vault.db").result()
        api = Api(vault, WebOverrides())

        def dispatch(method: str, body: dict[str, Any]) -> Any:
            return executor.submit(api.handle, method, body).result()

        token = "smoke-token"
        server = ApiServer(
            ("127.0.0.1", 0),
            dispatch,
            token=token,
            rate_limiter=AuthRateLimiter(limit=2, lockout_seconds=60),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            thread.start()
            port = server.bound_port

            status, headers, body = _request(port, "GET", "/")
            assert status == 200, status
            assert f'data-redscribe-token="{token}"'.encode() in body, body[:200]
            assert b"__REDSCRIBE_TOKEN__" not in body
            assert headers["X-Content-Type-Options"] == "nosniff"
            assert headers["X-Frame-Options"] == "DENY"
            assert "Content-Security-Policy" in headers
            nonce = re.search(rb'<script nonce="([^"]+)"', body)
            assert nonce is not None, body[:200]
            assert f"'nonce-{nonce.group(1).decode('ascii')}'" in headers["Content-Security-Policy"]

            status, headers, body = _request(port, "GET", "/assets/app.js")
            assert status == 200, status
            assert body
            assert headers["Cache-Control"] == "no-cache"
            assert headers["X-Content-Type-Options"] == "nosniff"

            status, _, body = _request(port, "POST", "/api/boot", token=token)
            assert status == 200, status
            assert b'"ok": true' in body, body

            status, _, body = _request(port, "POST", f"/api/boot?token={token}")
            assert status == 200, status
            assert b'"ok": true' in body, body

            status, _, _ = _request(port, "GET", "/", host="evil.example")
            assert status == 403, status

            status, _, _ = _request(port, "POST", "/api/boot")
            assert status == 403, status

            one_time = server.issue_download_token()
            status, headers, body = _request(
                port,
                "GET",
                f"/download/vault/html?token={one_time}",
            )
            assert status == 200, status
            assert body
            assert headers["Content-Type"].startswith("text/html")
            assert headers["Content-Disposition"].startswith("attachment;")
            status, _, _ = _request(port, "GET", f"/download/vault/html?token={one_time}")
            assert status == 403, status

            rotated = server.rotate_token(grace_seconds=5)
            status, _, body = _request(port, "GET", "/")
            assert status == 200, status
            assert f'data-redscribe-token="{rotated}"'.encode() in body, body[:200]
            status, _, _ = _request(port, "POST", "/api/boot", token=token)
            assert status == 200, status
            status, _, _ = _request(port, "POST", "/api/boot", token=rotated)
            assert status == 200, status

            for _ in range(2):
                status, _, _ = _request(port, "POST", "/api/boot", token="bad-token")
                assert status == 403, status
            status, headers, body = _request(port, "POST", "/api/boot", token=token)
            assert status == 429, status
            assert headers["Retry-After"].isdigit()
            assert b"Too many failed attempts" in body, body
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            executor.submit(vault.close).result()


if __name__ == "__main__":
    main()
