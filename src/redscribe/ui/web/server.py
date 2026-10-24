"""Local HTTP server that exposes the vault API and static web assets.

The server binds to localhost only, accepts JSON POSTs on ``/api/*`` and GETs
for the SPA shell, static assets, and note/vault downloads. Cross-origin use
is refused: no CORS headers are emitted, responses are ``nosniff``-protected,
and the document ships a tight content-security policy.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from redscribe.ui.web.api import ApiError

LOGGER = logging.getLogger(__name__)

MAX_BODY_BYTES = 8 * 1024 * 1024
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_STATIC_PATH_RE = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*[A-Za-z0-9][A-Za-z0-9._-]*$")
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
    """A threaded server bound to one dispatch function."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], dispatch: Dispatch) -> None:
        self.dispatch = dispatch
        super().__init__(address, _RequestHandler)

    @property
    def bound_port(self) -> int:
        return int(self.server_address[1])


class _RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "RedScribe"

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._serve_static_file("index.html")
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
        if path.startswith("/download/vault/"):
            self._serve_vault_download(path)
            return
        if path.startswith("/api/"):
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        if Path(path).suffix:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        self._serve_static_file("index.html")

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        method = parsed.path.removeprefix("/api/") if parsed.path.startswith("/api/") else ""
        if not method or "/" in method:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
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
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "font-src 'self' data:; script-src 'self'; connect-src 'self'; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            )
            self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(asset)

    def _serve_node_download(self, path: str) -> None:
        match = re.fullmatch(r"/download/note/(\d+)/(md|html)", path)
        if match is None:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        method = f"export_note_{match.group(2)}"
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

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _send_download(self, payload: Any) -> None:
        if not isinstance(payload, dict) or isinstance(payload.get("content"), str) is False:
            self._send_json({"ok": False, "error": "Export failed"}, status=500)
            return
        body = str(payload["content"]).encode("utf-8")
        filename = str(payload.get("filename") or "redscribe-export.txt")
        mime = str(payload.get("mime") or "text/plain")
        disposition = f"attachment; filename*=UTF-8''{quote(filename)}"
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Disposition", disposition)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
