"""Local HTTP server that exposes the vault API and static web assets.

The server binds to localhost only, accepts JSON POSTs on ``/api/*`` and GETs
for the SPA shell, static assets, and note/vault downloads. Requests are gated
on a loopback ``Host`` header, a per-session bearer token (injected into the
served SPA, sent as ``X-RedScribe-Token`` or as ``?token=`` on downloads), and
a per-client failed-authentication limiter. Every response carries the
hardened header set, and HTML documents receive a fresh CSP nonce.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from html import escape as html_escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from redscribe.ui.web.api import ApiError
from redscribe.ui.web.auth import (
    DOWNLOAD_PURPOSE,
    SESSION_PURPOSE,
    AuthOutcome,
    TokenManager,
)
from redscribe.ui.web.security import (
    EVENT_AUTH_FAILURE,
    EVENT_AUTH_SUCCESS,
    EVENT_DOWNLOAD,
    EVENT_HOST_REJECTED,
    EVENT_RATE_LIMITED,
    EVENT_STATIC_REJECTED,
    AuditLog,
    AuthRateLimiter,
    content_disposition,
    inject_script_nonce,
    safe_download_filename,
    safe_mime_type,
    safe_static_path,
    security_headers,
)
from redscribe.ui.web.v2.contracts import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    MAX_REQUEST_ID_LENGTH,
    V2Error,
    V2ErrorCode,
    error_envelope,
)

LOGGER = logging.getLogger(__name__)

MAX_BODY_BYTES = 8 * 1024 * 1024
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_TOKEN_PARAM = "token"
_HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost)(:\d{1,5})?$", re.IGNORECASE)
_TOKEN_PLACEHOLDER = b"__REDSCRIBE_TOKEN__"
_NOTE_DOWNLOAD_RE = re.compile(r"/download/note/(\d+)/(md|html)")
_V2_PREFIX = "/api/v2/"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
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
    return safe_static_path(_STATIC_DIR, name)


def static_asset_exists(name: str) -> bool:
    """Return whether a whitelisted static asset is packaged."""
    return _static_path(name) is not None


def static_asset_bytes(name: str) -> bytes | None:
    """Return the bytes of a whitelisted static asset, if present."""
    candidate = _static_path(name)
    if candidate is None:
        return None
    try:
        return candidate.read_bytes()
    except OSError:
        return None


def _new_nonce() -> str:
    return secrets.token_urlsafe(18)


DEFAULT_STATIC_DIR = _STATIC_DIR


class ApiServer(ThreadingHTTPServer):
    """A threaded server bound to one dispatch function and one token pool."""

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(
        self,
        address: tuple[str, int],
        dispatch: Dispatch,
        *,
        token: str | None = None,
        tokens: TokenManager | None = None,
        backup: Callable[[], bytes] | None = None,
        token_ttl: float | None = None,
        rate_limiter: AuthRateLimiter | None = None,
        audit_log: AuditLog | None = None,
    ) -> None:
        if token is not None and tokens is not None:
            raise ValueError("pass either token or tokens, not both")
        self.dispatch = dispatch
        self.tokens = tokens if tokens is not None else TokenManager(token, ttl_seconds=token_ttl)
        self.backup = backup
        self.rate_limiter = rate_limiter if rate_limiter is not None else AuthRateLimiter()
        self.audit = audit_log if audit_log is not None else AuditLog()
        super().__init__(address, _RequestHandler)

    @property
    def bound_port(self) -> int:
        return int(self.server_address[1])

    @property
    def token(self) -> str | None:
        return self.tokens.current_token

    def rotate_token(self, *, grace_seconds: float | None = None) -> str:
        return self.tokens.rotate(grace_seconds=grace_seconds)

    def issue_download_token(
        self,
        *,
        ttl_seconds: float | None = None,
        uses: int = 1,
    ) -> str:
        return self.tokens.issue_one_time(
            purpose=DOWNLOAD_PURPOSE,
            ttl_seconds=ttl_seconds,
            uses=uses,
        )


class _RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "redscribe-local"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    @property
    def app(self) -> ApiServer:
        return cast(ApiServer, self.server)

    def _client_key(self) -> str:
        address = self.client_address[0] if self.client_address else "unknown"
        return address or "unknown"

    def _request_path(self) -> str:
        return urlsplit(self.path).path

    def _audit(
        self,
        kind: str,
        outcome: str,
        *,
        path: str | None = None,
        detail: str = "",
    ) -> None:
        self.app.audit.record(
            kind,
            outcome,
            client=self._client_key(),
            path=self._request_path() if path is None else path,
            detail=detail,
        )

    def _host_allowed(self) -> bool:
        host = self.headers.get("Host", "").strip()
        if not host or len(host) > 255:
            return False
        if "@" in host or "\\" in host:
            return False
        return _HOST_RE.fullmatch(host) is not None

    def _require_host(self) -> bool:
        if self._host_allowed():
            return True
        self._audit(EVENT_HOST_REJECTED, "rejected")
        self._send_json({"ok": False, "error": "Forbidden host"}, status=403)
        return False

    @staticmethod
    def _query_token(path: str) -> str | None:
        return parse_qs(urlsplit(path).query, keep_blank_values=False).get(_TOKEN_PARAM, [None])[0]

    def _authenticate(self, purpose: str, *, allow_header: bool = True) -> bool:
        app = self.app
        key = self._client_key()
        decision = app.rate_limiter.check(key)
        if decision.blocked:
            self._audit(EVENT_RATE_LIMITED, "blocked", detail=f"retry_after={decision.retry_after}")
            self._send_json(
                {"ok": False, "error": "Too many failed attempts"},
                status=429,
                extra_headers={"Retry-After": str(decision.retry_after)},
            )
            return False

        presented = self.headers.get("X-RedScribe-Token") if allow_header else None
        if not presented:
            presented = self._query_token(self.path)
        outcome = app.tokens.authenticate(presented, purpose=purpose)
        if outcome in (AuthOutcome.ACCEPTED, AuthOutcome.DISABLED):
            app.rate_limiter.record_success(key)
            self._audit(EVENT_AUTH_SUCCESS, outcome.value)
            return True

        failure = app.rate_limiter.record_failure(key)
        self._audit(EVENT_AUTH_FAILURE, outcome.value, detail=f"failures={failure.failures}")
        extra: dict[str, str] | None = None
        if failure.blocked:
            extra = {"Retry-After": str(failure.retry_after)}
        self._send_json({"ok": False, "error": "Forbidden"}, status=403, extra_headers=extra)
        return False

    def do_GET(self) -> None:
        if not self._require_host():
            return
        path = urlsplit(self.path).path
        if path.startswith("/download/"):
            if self._authenticate(DOWNLOAD_PURPOSE, allow_header=False):
                self._route_download(path)
            return
        self._route_page(path)

    def do_POST(self) -> None:
        if not self._require_host():
            return
        if not self._authenticate(SESSION_PURPOSE):
            return
        parsed = urlsplit(self.path)
        if parsed.path.startswith(_V2_PREFIX):
            self._do_post_v2(parsed.path)
            return
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

    def _do_post_v2(self, path: str) -> None:
        request_id = self._request_id()
        try:
            segments = path.removeprefix(_V2_PREFIX).split("/")
            if len(segments) != 2 or any(not segment for segment in segments):
                raise V2Error(
                    404,
                    V2ErrorCode.UNKNOWN_ROUTE,
                    "Unknown API v2 route",
                )
            route = f"{segments[0]}.{segments[1]}"
            content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if content_type != "application/json":
                raise V2Error(
                    415,
                    V2ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                    "Content-Type must be application/json",
                )
            body, error = self._read_json_body()
            if error is not None:
                raise self._v2_body_error(error)
            payload = self._call_dispatch_v2(
                route,
                body,
                request_id=request_id,
                idempotency_key=self._idempotency_key(),
            )
        except V2Error as exc:
            self._send_v2_payload(error_envelope(exc, request_id=request_id), request_id)
            return
        except ApiError as exc:
            failure = V2Error(exc.status, V2ErrorCode.INVALID_REQUEST, exc.message)
            self._send_v2_payload(error_envelope(failure, request_id=request_id), request_id)
            return
        except Exception:
            LOGGER.exception("API v2 route %s failed", path)
            failure = V2Error(
                500,
                V2ErrorCode.INTERNAL,
                "Internal server error",
                retryable=True,
            )
            self._send_v2_payload(error_envelope(failure, request_id=request_id), request_id)
            return
        self._send_v2_payload(payload, request_id)

    @staticmethod
    def _v2_body_error(message: str) -> V2Error:
        if "too large" in message:
            return V2Error(413, V2ErrorCode.PAYLOAD_TOO_LARGE, message)
        if "Invalid JSON" in message or "must be an object" in message:
            return V2Error(400, V2ErrorCode.INVALID_JSON, message)
        return V2Error(400, V2ErrorCode.INVALID_REQUEST, message)

    def _call_dispatch_v2(
        self,
        route: str,
        body: dict[str, Any],
        *,
        request_id: str,
        idempotency_key: str | None,
    ) -> Any:
        target = getattr(self.app.dispatch, "handle_v2", None)
        if callable(target):
            return target(
                route,
                body,
                request_id=request_id,
                idempotency_key=idempotency_key,
            )
        enriched = dict(body)
        enriched["__v2_request_id"] = request_id
        enriched["__v2_idempotency_key"] = idempotency_key
        return self._call_dispatch(f"v2:{route}", enriched)

    def _request_id(self) -> str:
        raw = (self.headers.get("X-Request-ID") or "").strip()
        if raw:
            candidate = raw[:MAX_REQUEST_ID_LENGTH]
            if _REQUEST_ID_RE.fullmatch(candidate):
                return candidate
        return f"req_{secrets.token_urlsafe(16)}"

    def _idempotency_key(self) -> str | None:
        raw = (self.headers.get("Idempotency-Key") or "").strip()
        if not raw:
            return None
        candidate = raw[:MAX_IDEMPOTENCY_KEY_LENGTH]
        if _IDEMPOTENCY_KEY_RE.fullmatch(candidate):
            return candidate
        return None

    def _send_v2_payload(self, payload: Any, request_id: str) -> None:
        status = getattr(payload, "status", 200)
        etag = getattr(payload, "etag", None)
        extra_headers = getattr(payload, "headers", None)
        if etag is None and isinstance(payload, dict):
            meta = payload.get("meta")
            if isinstance(meta, dict):
                raw_etag = meta.get("etag")
                if isinstance(raw_etag, str):
                    etag = raw_etag
        if not isinstance(payload, dict):
            status = 500
            payload = error_envelope(
                V2Error(500, V2ErrorCode.INTERNAL, "Internal server error"),
                request_id=request_id,
            )
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for header, value in security_headers():
            self.send_header(header, value)
        self.send_header("X-Request-ID", request_id)
        if etag is not None:
            self.send_header("ETag", str(etag))
        if isinstance(extra_headers, dict):
            for header, value in extra_headers.items():
                self.send_header(str(header), str(value))
        self.end_headers()
        self.wfile.write(body)

    def _route_page(self, path: str) -> None:
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
        if path.startswith("/download/"):
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        if path.startswith("/api/"):
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        if Path(path).suffix:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        self._serve_index()

    def _route_download(self, path: str) -> None:
        if path.startswith("/download/note/"):
            self._serve_node_download(path)
            return
        if path == "/download/vault/html":
            self._serve_vault_download()
            return
        if path == "/download/vault/sqlite":
            self._serve_vault_sqlite()
            return
        self._send_json({"ok": False, "error": "Not found"}, status=404)

    def _call_dispatch(self, method: str, body: dict[str, Any]) -> Any:
        return self.app.dispatch(method, body)

    def _read_json_body(self) -> tuple[dict[str, Any], str | None]:
        raw_length = self.headers.get("Content-Length", "0")
        if not raw_length.isdigit():
            return {}, "Invalid Content-Length header"
        length = int(raw_length)
        if length <= 0:
            return {}, None
        if length > MAX_BODY_BYTES:
            return {}, "Request body too large"
        try:
            raw = self.rfile.read(length)
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}, "Invalid JSON body"
        if not isinstance(decoded, dict):
            return {}, "JSON body must be an object"
        return decoded, None

    def _serve_static_file(self, name: str) -> None:
        candidate = _static_path(name)
        if candidate is None:
            self._audit(EVENT_STATIC_REJECTED, "rejected", path=name)
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        asset = static_asset_bytes(name)
        if asset is None:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        content_type = _CONTENT_TYPES.get(candidate.suffix.lower(), "application/octet-stream")
        is_html = content_type.startswith("text/html")
        nonce = _new_nonce() if is_html else None
        if nonce is not None:
            asset = inject_script_nonce(asset, nonce)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(asset)))
        for header, value in security_headers(nonce=nonce, html=is_html, cache="no-cache"):
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(asset)

    def _serve_index(self) -> None:
        """Serve the SPA shell with a fresh token value and CSP nonce."""
        asset = static_asset_bytes("index.html")
        if asset is None:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        token = html_escape(self.app.tokens.current_token or "", quote=True)
        body = asset.replace(_TOKEN_PLACEHOLDER, token.encode("utf-8"))
        nonce = _new_nonce()
        body = inject_script_nonce(body, nonce)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for header, value in security_headers(nonce=nonce, html=True):
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(body)

    def _serve_node_download(self, path: str) -> None:
        match = _NOTE_DOWNLOAD_RE.fullmatch(path)
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
        self._send_download(payload, path=path)

    def _serve_vault_download(self) -> None:
        try:
            payload = self._call_dispatch("export_vault_html", {})
        except Exception:
            LOGGER.exception("Vault report failed")
            self._send_json({"ok": False, "error": "Internal server error"}, status=500)
            return
        self._send_download(payload, path="/download/vault/html")

    def _serve_vault_sqlite(self) -> None:
        backup = self.app.backup
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

    def _send_download(self, payload: Any, *, path: str) -> None:
        if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
            self._send_json({"ok": False, "error": "Export failed"}, status=500)
            return
        body = str(payload["content"]).encode("utf-8")
        filename = safe_download_filename(payload.get("filename"))
        mime = safe_mime_type(payload.get("mime"), default="text/plain")
        self._audit(EVENT_DOWNLOAD, "ok", path=path, detail=f"filename={filename}")
        self._send_binary_download(body, filename, mime)

    def _send_binary_download(self, body: bytes, filename: str, mime: str) -> None:
        safe_name = safe_download_filename(filename)
        safe_type = safe_mime_type(mime, default="application/octet-stream")
        content_type = f"{safe_type}; charset=utf-8" if safe_type.startswith("text/") else safe_type
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", content_disposition(safe_name))
        self.send_header("Content-Length", str(len(body)))
        for header, value in security_headers():
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self,
        payload: dict[str, Any],
        *,
        status: int = 200,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for header, value in security_headers():
            self.send_header(header, value)
        if extra_headers:
            for header, value in extra_headers.items():
                self.send_header(header, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        LOGGER.debug("HTTP %s %s", self.address_string(), fmt % args)
