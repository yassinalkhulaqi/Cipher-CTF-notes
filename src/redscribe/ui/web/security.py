"""Transport hardening helpers shared by the local HTTP server.

This module owns the response header policy, the structured security audit
trail, the failed-authentication rate limiter, and the conservative validators
used for static asset paths and download metadata.
"""

from __future__ import annotations

import math
import re
import threading
import time
import unicodedata
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from urllib.parse import quote

EVENT_AUTH_FAILURE: Final = "auth_failure"
EVENT_AUTH_SUCCESS: Final = "auth_success"
EVENT_RATE_LIMITED: Final = "rate_limited"
EVENT_HOST_REJECTED: Final = "host_rejected"
EVENT_DOWNLOAD: Final = "download"
EVENT_STATIC_REJECTED: Final = "static_rejected"

_CACHE_NO_STORE: Final = "no-store"
_CACHE_STATIC: Final = "no-cache"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One immutable security-relevant observation."""

    kind: str
    outcome: str
    client: str
    path: str
    detail: str = ""
    at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, str]:
        return {
            "at": datetime.fromtimestamp(self.at, timezone.utc).isoformat(timespec="milliseconds"),
            "kind": self.kind,
            "outcome": self.outcome,
            "client": self.client,
            "path": self.path,
            "detail": self.detail,
        }


class AuditLog:
    """A bounded, thread-safe ring of recent audit events."""

    def __init__(
        self,
        *,
        capacity: int = 256,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._capacity = capacity
        self._clock = clock
        self._events: deque[AuditEvent] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def record(
        self,
        kind: str,
        outcome: str,
        *,
        client: str = "",
        path: str = "",
        detail: str = "",
    ) -> AuditEvent:
        event = AuditEvent(
            kind=kind,
            outcome=outcome,
            client=client,
            path=path,
            detail=detail,
            at=self._clock(),
        )
        with self._lock:
            self._events.append(event)
        return event

    def snapshot(self) -> tuple[AuditEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def as_dicts(self) -> list[dict[str, str]]:
        return [event.as_dict() for event in self.snapshot()]

    def count(self, *, kind: str | None = None, outcome: str | None = None) -> int:
        return sum(
            1
            for event in self.snapshot()
            if (kind is None or event.kind == kind)
            and (outcome is None or event.outcome == outcome)
        )

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """The outcome of a rate-limit check, including retry guidance."""

    allowed: bool
    failures: int
    limit: int
    retry_after: int = 0

    @property
    def blocked(self) -> bool:
        return not self.allowed


class AuthRateLimiter:
    """Per-client sliding-window limiter with a fixed lockout after a burst."""

    def __init__(
        self,
        *,
        limit: int = 8,
        window_seconds: float = 60.0,
        lockout_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds <= 0 or lockout_seconds <= 0:
            raise ValueError("window_seconds and lockout_seconds must be positive")
        self._limit = limit
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._failures: dict[str, deque[float]] = {}
        self._locked_until: dict[str, float] = {}

    @property
    def limit(self) -> int:
        return self._limit

    def check(self, key: str) -> RateLimitDecision:
        now = self._clock()
        with self._lock:
            self._prune(key, now)
            locked_until = self._locked_until.get(key, 0.0)
            if locked_until > now:
                return RateLimitDecision(
                    allowed=False,
                    failures=self._limit,
                    limit=self._limit,
                    retry_after=max(1, math.ceil(locked_until - now)),
                )
            if locked_until:
                del self._locked_until[key]
            failures = len(self._failures.get(key, ()))
            return RateLimitDecision(allowed=True, failures=failures, limit=self._limit)

    def record_failure(self, key: str) -> RateLimitDecision:
        now = self._clock()
        with self._lock:
            self._prune(key, now)
            bucket = self._failures.setdefault(key, deque())
            bucket.append(now)
            if len(bucket) >= self._limit:
                self._locked_until[key] = now + self._lockout
                bucket.clear()
                return RateLimitDecision(
                    allowed=False,
                    failures=self._limit,
                    limit=self._limit,
                    retry_after=math.ceil(self._lockout),
                )
            return RateLimitDecision(
                allowed=True,
                failures=len(bucket),
                limit=self._limit,
            )

    def record_success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._failures.clear()
                self._locked_until.clear()
                return
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)

    def snapshot(self) -> dict[str, int]:
        now = self._clock()
        with self._lock:
            result: dict[str, int] = {}
            for key in tuple(self._failures):
                self._prune(key, now)
                bucket = self._failures.get(key)
                if bucket:
                    result[key] = len(bucket)
            return result

    def _prune(self, key: str, now: float) -> None:
        bucket = self._failures.get(key)
        if bucket is None:
            return
        cutoff = now - self._window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if not bucket:
            del self._failures[key]


def content_security_policy(*, nonce: str | None = None) -> str:
    """Return the CSP for the SPA shell, optionally nonce-locking scripts."""
    script_sources = "'self'"
    if nonce:
        script_sources += f" 'nonce-{nonce}'"
    return (
        "default-src 'self'; "
        f"script-src {script_sources}; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "manifest-src 'self'; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'none'"
    )


def security_headers(
    *,
    nonce: str | None = None,
    html: bool = False,
    cache: str = _CACHE_NO_STORE,
) -> list[tuple[str, str]]:
    """Build the baseline hardening headers for every response class."""
    headers: list[tuple[str, str]] = [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Cross-Origin-Opener-Policy", "same-origin"),
        ("Cross-Origin-Resource-Policy", "same-origin"),
        (
            "Permissions-Policy",
            "accelerometer=(), camera=(), geolocation=(), microphone=(), payment=(), usb=()",
        ),
        ("Referrer-Policy", "no-referrer"),
        ("Cache-Control", cache),
    ]
    if html:
        headers.append(("Content-Security-Policy", content_security_policy(nonce=nonce)))
    return headers


_SCRIPT_OPEN_RE = re.compile(rb"<script(?=[\s>])")


def inject_script_nonce(body: bytes, nonce: str) -> bytes:
    """Attach ``nonce`` to every script tag in a served HTML document."""
    replacement = b'<script nonce="' + nonce.encode("ascii") + b'"'
    return _SCRIPT_OPEN_RE.sub(replacement, body)


_RESERVED_NAMES: Final = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{n}" for n in range(1, 10)),
        *(f"LPT{n}" for n in range(1, 10)),
    }
)
_SAFE_MIME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+/\-]*$")
_MAX_FILENAME_LENGTH: Final = 180


def safe_download_filename(
    name: object,
    *,
    default: str = "redscribe-export.txt",
    max_length: int = _MAX_FILENAME_LENGTH,
) -> str:
    """Normalize untrusted export metadata into a single safe filename."""
    if not isinstance(name, str):
        return default
    candidate = unicodedata.normalize("NFC", name).strip()
    if not candidate or len(candidate) > max_length:
        return default
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in candidate):
        return default
    if "/" in candidate or "\\" in candidate or "\x00" in candidate:
        return default
    if candidate.startswith(".") or candidate.rstrip(" .") != candidate:
        return default
    if Path(candidate).name != candidate or Path(candidate).is_absolute():
        return default
    if candidate.split(".")[0].upper() in _RESERVED_NAMES:
        return default
    if not all(char.isprintable() for char in candidate):
        return default
    return candidate


def safe_mime_type(value: object, *, default: str = "application/octet-stream") -> str:
    """Accept only simple MIME tokens that cannot inject response headers."""
    if not isinstance(value, str):
        return default
    candidate = value.strip()
    if not candidate or len(candidate) > 100 or _SAFE_MIME_RE.fullmatch(candidate) is None:
        return default
    return candidate


def content_disposition(filename: str) -> str:
    """Build a header with a portable ASCII fallback and an RFC 5987 name."""
    safe = safe_download_filename(filename)
    ascii_base = safe.encode("ascii", "ignore").decode("ascii")
    fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_base).strip("._") or "download"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(safe, safe='')}"


def safe_static_path(root: Path, name: str) -> Path | None:
    """Resolve a bundled asset path, refusing traversal, dotfiles and symlinks."""
    if not name or len(name) > 512 or "\x00" in name or "\\" in name:
        return None
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in name):
        return None
    parts = name.split("/")
    if any(not part or part.startswith(".") or len(part) > 200 for part in parts):
        return None
    try:
        base = root.resolve(strict=True)
    except OSError:
        return None

    current = base
    for part in parts:
        current = current / part
        if current.is_symlink():
            return None
    try:
        resolved = current.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_relative_to(base) or not resolved.is_file():
        return None
    return resolved
