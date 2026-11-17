"""Session token lifecycle for the loopback web server.

The browser receives one session token injected into the served shell and
reuses it for every API call. This module keeps that contract intact while
adding bounded lifetime, rotation with a short overlap for in-flight requests,
and single-use tokens for download URLs.
"""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum

SESSION_PURPOSE = "session"
DOWNLOAD_PURPOSE = "download"
ANY_PURPOSE = "any"

DEFAULT_GRACE_SECONDS = 30.0
DEFAULT_ONE_TIME_TTL_SECONDS = 120.0
MAX_ONE_TIME_TOKENS = 64


class AuthOutcome(Enum):
    """Why a presented token was accepted or refused."""

    ACCEPTED = "accepted"
    INVALID = "invalid"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class TokenRecord:
    """An immutable token with an optional deadline and use budget."""

    value: str
    issued_at: float
    expires_at: float | None
    remaining_uses: int | None
    purpose: str = SESSION_PURPOSE

    def expired(self, now: float) -> bool:
        return self.expires_at is not None and now >= self.expires_at


@dataclass(frozen=True, slots=True)
class TokenStats:
    """A point-in-time summary used by audit and diagnostics."""

    enabled: bool
    session_active: bool
    retired: int
    one_time: int

    def as_dict(self) -> dict[str, bool | int]:
        return {
            "enabled": self.enabled,
            "session_active": self.session_active,
            "retired": self.retired,
            "one_time": self.one_time,
        }


class TokenManager:
    """Issue, validate, rotate and retire bearer tokens.

    A manager built with ``secret=None`` represents an embedded/test server
    with authentication disabled; every validation then returns
    :attr:`AuthOutcome.DISABLED`, which callers treat as an accepted request.
    """

    def __init__(
        self,
        secret: str | None,
        *,
        ttl_seconds: float | None = None,
        grace_seconds: float = DEFAULT_GRACE_SECONDS,
        one_time_ttl_seconds: float = DEFAULT_ONE_TIME_TTL_SECONDS,
        max_one_time: int = MAX_ONE_TIME_TOKENS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if secret is not None and not secret:
            raise ValueError("secret must be a non-empty string or None")
        for name, value in (
            ("ttl_seconds", ttl_seconds),
            ("grace_seconds", grace_seconds),
            ("one_time_ttl_seconds", one_time_ttl_seconds),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")
        if max_one_time < 1:
            raise ValueError("max_one_time must be at least 1")

        self._ttl_seconds = ttl_seconds
        self._grace_seconds = grace_seconds
        self._one_time_ttl_seconds = one_time_ttl_seconds
        self._max_one_time = max_one_time
        self._clock = clock
        self._lock = threading.Lock()
        now = clock()
        self._session: TokenRecord | None = (
            None
            if secret is None
            else TokenRecord(secret, now, self._deadline(now, ttl_seconds), None, SESSION_PURPOSE)
        )
        self._retired: dict[str, TokenRecord] = {}
        self._one_time: dict[str, TokenRecord] = {}

    @staticmethod
    def _deadline(now: float, ttl: float | None) -> float | None:
        return None if ttl is None else now + ttl

    @staticmethod
    def _matches(presented: str | None, expected: str) -> bool:
        if not isinstance(presented, str) or not presented:
            return False
        try:
            return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))
        except UnicodeEncodeError:
            return False

    @property
    def enabled(self) -> bool:
        return self._session is not None

    @property
    def current_token(self) -> str | None:
        record = self._session
        return None if record is None else record.value

    @property
    def ttl_seconds(self) -> float | None:
        return self._ttl_seconds

    def authenticate(self, presented: str | None, *, purpose: str = ANY_PURPOSE) -> AuthOutcome:
        """Validate a token, consuming a single-use record when one matches."""
        if self._session is None:
            return AuthOutcome.DISABLED
        if not isinstance(presented, str) or not presented:
            return AuthOutcome.INVALID

        now = self._clock()
        with self._lock:
            active = self._session
            if active is not None and self._matches(presented, active.value):
                return AuthOutcome.EXPIRED if active.expired(now) else AuthOutcome.ACCEPTED

            record = self._one_time.get(presented)
            if record is not None and self._matches(presented, record.value):
                if purpose not in (ANY_PURPOSE, record.purpose):
                    return AuthOutcome.INVALID
                if record.expired(now):
                    del self._one_time[presented]
                    return AuthOutcome.EXPIRED
                if record.remaining_uses is None or record.remaining_uses <= 0:
                    return AuthOutcome.CONSUMED
                remaining = record.remaining_uses - 1
                self._one_time[presented] = replace(record, remaining_uses=remaining)
                return AuthOutcome.ACCEPTED

            self._prune(now)
            retired = self._retired.get(presented)
            if retired is not None and self._matches(presented, retired.value):
                return AuthOutcome.ACCEPTED
            return AuthOutcome.INVALID

    def rotate(self, *, grace_seconds: float | None = None) -> str:
        """Replace the session token, keeping the previous one briefly valid."""
        if self._session is None:
            raise RuntimeError("token authentication is disabled")
        grace = self._grace_seconds if grace_seconds is None else grace_seconds
        if grace <= 0:
            raise ValueError("grace_seconds must be positive")

        with self._lock:
            now = self._clock()
            self._prune(now)
            previous = self._session
            self._retired[previous.value] = replace(previous, expires_at=now + grace)
            value = secrets.token_urlsafe(32)
            self._session = TokenRecord(
                value,
                now,
                self._deadline(now, self._ttl_seconds),
                None,
                SESSION_PURPOSE,
            )
            return value

    def issue_one_time(
        self,
        *,
        purpose: str = DOWNLOAD_PURPOSE,
        ttl_seconds: float | None = None,
        uses: int = 1,
    ) -> str:
        """Mint a short-lived token that is consumed after ``uses`` checks."""
        if uses < 1:
            raise ValueError("uses must be at least 1")
        lifetime = self._one_time_ttl_seconds if ttl_seconds is None else ttl_seconds
        if lifetime <= 0:
            raise ValueError("ttl_seconds must be positive")

        with self._lock:
            now = self._clock()
            self._prune(now)
            value = secrets.token_urlsafe(24)
            self._one_time[value] = TokenRecord(value, now, now + lifetime, uses, purpose)
            while len(self._one_time) > self._max_one_time:
                del self._one_time[next(iter(self._one_time))]
            return value

    def invalidate(self) -> None:
        """Drop all retired and single-use tokens; the session token survives."""
        with self._lock:
            self._retired.clear()
            self._one_time.clear()

    def stats(self) -> TokenStats:
        now = self._clock()
        with self._lock:
            self._prune(now)
            return TokenStats(
                enabled=self._session is not None,
                session_active=self._session is not None and not self._session.expired(now),
                retired=len(self._retired),
                one_time=len(self._one_time),
            )

    def _prune(self, now: float) -> None:
        for value, record in tuple(self._retired.items()):
            if record.expired(now):
                del self._retired[value]
        for value, record in tuple(self._one_time.items()):
            if record.expired(now):
                del self._one_time[value]
