"""Smoke-test the packaged RedScribe web server over HTTP."""

from __future__ import annotations

import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api, WebOverrides
from redscribe.ui.web.server import ApiServer


def _request(
    port: int,
    method: str,
    path: str,
    *,
    token: str | None = None,
) -> tuple[int, bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        headers = {"Host": "127.0.0.1"}
        body = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            body = b"{}"
        if token is not None:
            headers["X-RedScribe-Token"] = token
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, response.read()
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

        server = ApiServer(("127.0.0.1", 0), dispatch, token="smoke-token")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            thread.start()
            port = server.bound_port

            status, body = _request(port, "GET", "/")
            assert status == 200, status
            assert b'data-redscribe-token="smoke-token"' in body, body[:200]

            status, body = _request(port, "POST", "/api/boot", token="smoke-token")
            assert status == 200, status
            assert b'"ok": true' in body, body

            status, _ = _request(port, "POST", "/api/boot")
            assert status == 403, status
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            executor.submit(vault.close).result()


if __name__ == "__main__":
    main()
