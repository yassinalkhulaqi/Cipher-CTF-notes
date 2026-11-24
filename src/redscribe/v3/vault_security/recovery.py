"""Single-use vault recovery codes.

Only salted digests are retained. A code is returned to the caller exactly
once, at issue time, and redemption consumes it even when the subsequent
re-keying step fails.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from typing import Any

MAX_CODES_PER_BATCH = 16
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_GROUPS = 3
_GROUP_SIZE = 5
_SEPARATOR = "-"
_NON_ALNUM = re.compile(r"[^A-Z0-9]")


class RecoveryCodeError(Exception):
    """Raised when a recovery code cannot be redeemed."""


@dataclass(frozen=True, slots=True)
class RecoveryCodeRecord:
    """Persistent state for one issued recovery code."""

    code_id: str
    digest: str
    salt: str
    created_at: float
    expires_at: float = 0.0
    used_at: float = 0.0
    revoked: bool = False
    label: str = ""

    @property
    def is_used(self) -> bool:
        """Whether the code has already been redeemed."""
        return self.used_at > 0.0

    def is_expired(self, now: float) -> bool:
        """Whether the code is past its validity window."""
        return self.expires_at > 0.0 and now >= self.expires_at

    def is_active(self, now: float) -> bool:
        """Whether the code can still be redeemed at the given time."""
        return not self.is_used and not self.revoked and not self.is_expired(now)

    def state(self, now: float) -> str:
        """Return a non-sensitive lifecycle label."""
        if self.is_used:
            return "used"
        if self.revoked:
            return "revoked"
        if self.is_expired(now):
            return "expired"
        return "active"

    def as_dict(self, now: float) -> dict[str, Any]:
        """Return a JSON-safe representation without the code or digest."""
        return {
            "code_id": self.code_id,
            "state": self.state(now),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "used_at": self.used_at,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class RecoveryRedemption:
    """Result of a successful single-use redemption."""

    code_id: str
    redeemed_at: float
    remaining_active: int
    consumed: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "code_id": self.code_id,
            "redeemed_at": self.redeemed_at,
            "remaining_active": self.remaining_active,
            "consumed": self.consumed,
        }


def normalize_code(value: str) -> str:
    """Normalize a user-entered code for comparison."""
    if not isinstance(value, str):
        raise TypeError("Recovery code must be a string")
    return _NON_ALNUM.sub("", value.strip().upper())


def is_well_formed(value: str) -> bool:
    """Return whether a value has the shape of an issued recovery code."""
    normalized = normalize_code(value)
    return len(normalized) == _CODE_GROUPS * _GROUP_SIZE and all(
        char in _ALPHABET for char in normalized
    )


def _generate_code() -> str:
    groups = [
        "".join(secrets.choice(_ALPHABET) for _ in range(_GROUP_SIZE)) for _ in range(_CODE_GROUPS)
    ]
    return _SEPARATOR.join(groups)


def _digest(normalized: str, salt: bytes) -> str:
    return hmac.new(salt, normalized.encode("ascii"), hashlib.sha256).hexdigest()


class RecoveryCodeStore:
    """In-memory store enforcing single-use redemption of recovery codes."""

    def __init__(self) -> None:
        self._records: list[RecoveryCodeRecord] = []
        self._issued_count = 0

    @property
    def issued_count(self) -> int:
        """Total number of codes ever issued."""
        return self._issued_count

    def issue(
        self,
        count: int,
        *,
        created_at: float,
        label: str = "",
        valid_for_seconds: float = 0.0,
    ) -> tuple[str, ...]:
        """Issue a batch of codes, returning the plaintext values only once."""
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("count must be an integer")
        if not 1 <= count <= MAX_CODES_PER_BATCH:
            raise ValueError(f"count must be between 1 and {MAX_CODES_PER_BATCH}")
        if valid_for_seconds < 0:
            raise ValueError("valid_for_seconds cannot be negative")
        codes: list[str] = []
        for _ in range(count):
            code = _generate_code()
            normalized = normalize_code(code)
            salt = secrets.token_bytes(16)
            self._issued_count += 1
            self._records.append(
                RecoveryCodeRecord(
                    code_id=f"rc_{self._issued_count:04d}",
                    digest=_digest(normalized, salt),
                    salt=salt.hex(),
                    created_at=created_at,
                    expires_at=created_at + valid_for_seconds if valid_for_seconds else 0.0,
                    label=label,
                )
            )
            codes.append(code)
        return tuple(codes)

    def redeem(self, code: str, *, now: float) -> RecoveryRedemption:
        """Consume a code atomically and report how many remain active."""
        normalized = normalize_code(code)
        if not is_well_formed(normalized):
            raise RecoveryCodeError("Recovery code has an invalid format")
        record = self._find(normalized)
        if record is None:
            raise RecoveryCodeError("Recovery code is not recognized")
        if record.is_used:
            raise RecoveryCodeError("Recovery code has already been used")
        if record.revoked:
            raise RecoveryCodeError("Recovery code has been revoked")
        if record.is_expired(now):
            raise RecoveryCodeError("Recovery code has expired")
        object.__setattr__(record, "used_at", now)
        return RecoveryRedemption(
            code_id=record.code_id,
            redeemed_at=now,
            remaining_active=self.active_count(now),
        )

    def revoke(self, code_id: str) -> bool:
        """Revoke an unused code by identifier."""
        for record in self._records:
            if record.code_id == code_id and not record.is_used and not record.revoked:
                object.__setattr__(record, "revoked", True)
                return True
        return False

    def lookup(self, code: str) -> RecoveryCodeRecord | None:
        """Find a record by code without consuming it."""
        normalized = normalize_code(code)
        if not is_well_formed(normalized):
            return None
        return self._find(normalized)

    def active_count(self, now: float) -> int:
        """Count codes that can still be redeemed."""
        return sum(1 for record in self._records if record.is_active(now))

    def used_count(self) -> int:
        """Count codes that have been consumed."""
        return sum(1 for record in self._records if record.is_used)

    def records(self) -> tuple[RecoveryCodeRecord, ...]:
        """Return stored records for internal verification."""
        return tuple(self._records)

    def snapshot(self, *, now: float) -> dict[str, Any]:
        """Return a secret-free store summary for API and posture reporting."""
        return {
            "issued": self._issued_count,
            "active": self.active_count(now),
            "used": self.used_count(),
            "revoked": sum(1 for record in self._records if record.revoked),
            "expired": sum(1 for record in self._records if record.is_expired(now)),
            "codes": [record.as_dict(now) for record in self._records],
        }

    def clear(self) -> None:
        """Drop all issued code state."""
        self._records.clear()
        self._issued_count = 0

    def _find(self, normalized: str) -> RecoveryCodeRecord | None:
        for record in self._records:
            actual = _digest(normalized, bytes.fromhex(record.salt))
            if hmac.compare_digest(actual, record.digest):
                return record
        return None
