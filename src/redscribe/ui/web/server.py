"""Local HTTP server that exposes the vault API and static web assets.

The server binds to localhost only, accepts JSON POSTs on ``/api/*`` and GETs
for the SPA shell, static assets, and note/vault downloads. Every request is
gated on a per-session bearer token (injected into the served SPA and required
as ``X-RedScribe-Token`` on POSTs, or ``?token=`` on downloads) and on a
loopback ``Host`` header, so cross-origin pages and DNS-rebinding attacks are
refused. Responses are ``nosniff``-protected and the document ships a tight
content-security policy.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from redscribe.ui.web.api import ApiError

LOGGER = logging.getLogger(__name__)

MAX_BODY_BYTES = 8 * 1024 * 1024
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_STATIC_PATH_RE = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*[A-Za-z0-9][A-Za-z0-9._-]*$")
_TOKEN_PARAM = "token"
_HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost)(:\d+)?$", re.IGNORECASE)
_TOKEN_PLACEHOLDER = b"__REDSCRIBE_TOKEN__"
_CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; script-src 'self'; connect-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}

Dispatch = Callable[[str, dict[str, Any]], Any]


def _static_path(name: str) -> Path | None:
    """Resolve a static asset path without allowing directory traversal."""
    if _STATIC_PATH_RE.fullmatch(name) is None:
        return None
    root = _STATIC_DIR.resolve()
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def static_asset_exists(name: str) -> bool:
    """Return whether a whitelisted static asset is packaged."""
    candidate = _static_path(name)
    return candidate is not None and candidate.is_file()


def static_asset_bytes(name: str) -> bytes | None:
    """Return the bytes of a whitelisted static asset, if present."""
    candidate = _static_path(name)
    if candidate is None or not candidate.is_file():
        return None
    return candidate.read_bytes()


DEFAULT_STATIC_DIR = _STATIC_DIR


class ApiServer(ThreadingHTTPServer):
    """A threaded server bound to one dispatch function and one session token."""

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(
        self,
        address: tuple[str, int],
        dispatch: Dispatch,
        *,
        token: str | None = None,
        backup: Callable[[], bytes] | None = None,
    ) -> None:
        self.dispatch = dispatch
        self.token = token
        self.backup = backup
        super().__init__(address, _RequestHandler)

    @property
    def bound_port(self) -> int:
        return int(self.server_address[1])


class _RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "redscribe-local"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    # ------------------------------------------------------------------
    # Security guards
    # ------------------------------------------------------------------

    def _host_allowed(self) -> bool:
        host = self.headers.get("Host", "")
        return _HOST_RE.fullmatch(host.strip()) is not None

    @staticmethod
    def _query_token(path: str) -> str | None:
        query = urlsplit(path).query
        return parse_qs(query).get(_TOKEN_PARAM, [None])[0]

    def _token_valid(self, presented: str | None) -> bool:
        server = self.server
        expected = getattr(server, "token", None)
        if expected is None:
            return True  # token auth disabled (tests/embedding)
        if not presented:
            return False
        try:
            return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))
        except (UnicodeEncodeError, TypeError):
            return False

    def _require_host(self) -> bool:
        if self._host_allowed():
            return True
        self._send_json({"ok": False, "error": "Forbidden host"}, status=403)
        return False

    def _require_api_token(self) -> bool:
        presented = self.headers.get("X-RedScribe-Token") or self._query_token(self.path)
        if self._token_valid(presented):
            return True
        self._send_json({"ok": False, "error": "Forbidden"}, status=403)
        return False

    def _require_download_token(self, path: str) -> bool:
        if self._token_valid(self._query_token(path)):
            return True
        self._send_json({"ok": False, "error": "Forbidden"}, status=403)
        return False

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        if not self._require_host():
            return
        parsed = urlsplit(self.path)
        path = parsed.path
        if path.startswith("/download/") and not self._require_download_token(self.path):
            return
        if path in ("/", "/index.html"):
            self._serve_index()
            return
        if path.startswith("/assets/"):
            self._serve_static_file(path.removeprefix("/"))
            return
        if path.startswith("/static/"):
            self._serve_static_file(path.removesuffix("/").removeprefix("/static/"))
            return
        if path in ("/favicon.svg", "/manifest.webmanifest", "/robots.txt"):
            self._serve_static_file(path.removeprefix("/"))
            return
        if path.startswith("/download/note/"):
            self._serve_node_download(path)
            return
        if path == "/download/vault/html":
            self._serve_vault_download(path)
            return
        if path == "/download/vault/sqlite":
            self._serve_vault_sqlite()
            return
        if path.startswith("/api/"):
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        if Path(path).suffix:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        self._serve_index()

    def do_POST(self) -> None:
        if not self._require_host():
            return
        if not self._require_api_token():
            return
        parsed = urlsplit(self.path)
        method = parsed.path.removeprefix("/api/") if parsed.path.startswith("/api/") else ""
        if not method or "/" in method:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type != "application/json":
            self._send_json(
                {"ok": False, "error": "Content-Type must be application/json"},
                status=415,
            )
            return
        body, error = self._read_json_body()
        if error is not None:
            self._send_json({"ok": False, "error": error}, status=400)
            return
        try:
            payload = self._call_dispatch(method, body)
        except ApiError as exc:
            self._send_json({"ok": False, "error": exc.message}, status=exc.status)
            return
        except Exception:
            LOGGER.exception("API method %s failed", method)
            self._send_json({"ok": False, "error": "Internal server error"}, status=500)
            return
        self._send_json({"ok": True, "data": payload})

    # ------------------------------------------------------------------
    # Payload handling
    # ------------------------------------------------------------------

    def _call_dispatch(self, method: str, body: dict[str, Any]) -> Any:
        dispatch: Dispatch = self.server.dispatch  # type: ignore[attr-defined]
        return dispatch(method, body)

    def _read_json_body(self) -> tuple[dict[str, Any], str | None]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError:
            return {}, "Invalid Content-Length header"
        if length <= 0:
            return {}, None
        if length > MAX_BODY_BYTES:
            return {}, "Request body too large"
        try:
            raw = self.rfile.read(length)
            decoded = json.loads(raw.decode("utf-8")) if length else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}, "Invalid JSON body"
        if not isinstance(decoded, dict):
            return {}, "JSON body must be an object"
        return decoded, None

    # ------------------------------------------------------------------
    # Static assets and downloads
    # ------------------------------------------------------------------

    def _serve_static_file(self, name: str) -> None:
        asset = static_asset_bytes(name)
        if asset is None:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        content_type = _CONTENT_TYPES.get(Path(name).suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(asset)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", _CSP)
            self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(asset)

    def _serve_index(self) -> None:
        """Serve the SPA shell with the per-session token injected into the DOM."""
        asset = static_asset_bytes("index.html")
        if asset is None:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        server = self.server
        token = getattr(server, "token", None) or ""
        body = asset.replace(_TOKEN_PLACEHOLDER, token.encode("utf-8"))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", _CSP)
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _serve_node_download(self, path: str) -> None:
        match = re.fullmatch(r"/download/note/(\d+)/(md|html)", path)
        if match is None:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        method = "export_note_markdown" if match.group(2) == "md" else "export_note_html"
        try:
            payload = self._call_dispatch(method, {"id": int(match.group(1))})
        except ApiError as exc:
            self._send_json({"ok": False, "error": exc.message}, status=exc.status)
            return
        except Exception:
            LOGGER.exception("Download failed for %s", path)
            self._send_json({"ok": False, "error": "Internal server error"}, status=500)
            return
        self._send_download(payload)

    def _serve_vault_download(self, path: str) -> None:
        if not re.fullmatch(r"/download/vault/html", path):
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        try:
            payload = self._call_dispatch("export_vault_html", {})
        except Exception:
            LOGGER.exception("Vault report failed")
            self._send_json({"ok": False, "error": "Internal server error"}, status=500)
            return
        self._send_download(payload)

    def _serve_vault_sqlite(self) -> None:
        server = self.server
        backup = getattr(server, "backup", None)
        if backup is None:
            self._send_json({"ok": False, "error": "Backup unavailable"}, status=404)
            return
        try:
            body = backup()
        except Exception:
            LOGGER.exception("Vault backup failed")
            self._send_json({"ok": False, "error": "Backup failed"}, status=500)
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self._send_binary_download(body, f"redscribe-vault-{stamp}.db", "application/x-sqlite3")

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _send_download(self, payload: Any) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
            self._send_json({"ok": False, "error": "Export failed"}, status=500)
            return
        body = str(payload["content"]).encode("utf-8")
        filename = str(payload.get("filename") or "redscribe-export.txt")
        mime = str(payload.get("mime") or "text/plain")
        self._send_binary_download(body, filename, mime)

    def _send_binary_download(self, body: bytes, filename: str, mime: str) -> None:
        content_type = f"{mime}; charset=utf-8" if mime.startswith("text/") else mime
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", disposition)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib name
        LOGGER.debug("HTTP %s %s", self.address_string(), format % args)
