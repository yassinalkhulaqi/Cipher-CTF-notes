"""Optimistic revision tokens and conflict detection."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from redscribe.v2.blocks.constants import MAX_TOKEN_HISTORY
from redscribe.v2.blocks.diff import PatchError, content_hash, document_signature
from redscribe.v2.blocks.model import BlockDocument, utc_now

TOKEN_PREFIX = "rev1."


class RevisionConflictError(PatchError):
    """Raised when a token does not match the current document state."""

    def __init__(
        self,
        expected: int,
        actual: int,
        *,
        document_id: str = "",
        reason: str = "revision mismatch",
    ) -> None:
        super().__init__(f"{reason}: expected {expected}, found {actual}")
        self.expected = expected
        self.actual = actual
        self.document_id = document_id
        self.reason = reason

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": "revision_conflict",
            "message": str(self),
            "expected": self.expected,
            "actual": self.actual,
            "document_id": self.document_id,
            "reason": self.reason,
        }


def _signature_bytes(document: BlockDocument, secret: str) -> bytes:
    payload = {
        "document_id": document.id,
        "revision": document.revision,
        "signature": document_signature(document),
        "content_hash": content_hash(document),
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    if not secret:
        return hashlib.sha256(raw).digest()
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()


def compute_digest(document: BlockDocument, *, secret: str = "") -> str:
    """Return a hex digest binding identity, revision, and content."""
    return _signature_bytes(document, secret).hex()


@dataclass(frozen=True, slots=True)
class RevisionToken:
    """An opaque token proving knowledge of one document revision."""

    document_id: str
    revision: int
    digest: str
    issued_at: str
    nonce: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "revision": self.revision,
            "digest": self.digest,
            "issued_at": self.issued_at,
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RevisionToken:
        revision = value.get("revision", 0)
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ValueError("Token revision must be an integer")
        return cls(
            document_id=str(value.get("document_id", "")),
            revision=revision,
            digest=str(value.get("digest", "")),
            issued_at=str(value.get("issued_at", "")),
            nonce=str(value.get("nonce", "")),
        )


def issue_token(document: BlockDocument, *, secret: str = "") -> RevisionToken:
    """Mint a token for the current state of ``document``."""
    return RevisionToken(
        document_id=document.id,
        revision=document.revision,
        digest=compute_digest(document, secret=secret),
        issued_at=utc_now(),
        nonce=secrets.token_urlsafe(8),
    )


def encode_token(token: RevisionToken) -> str:
    """Encode a token as a compact opaque string."""
    raw = json.dumps(
        token.as_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return TOKEN_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_token(value: str) -> RevisionToken:
    """Decode a token string, raising ``ValueError`` when malformed."""
    if not isinstance(value, str) or not value.startswith(TOKEN_PREFIX):
        raise ValueError("Malformed revision token")
    payload = value[len(TOKEN_PREFIX) :]
    padding = "=" * ((4 - len(payload) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode((payload + padding).encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed revision token") from exc
    if not isinstance(decoded, Mapping):
        raise ValueError("Malformed revision token")
    return RevisionToken.from_dict(decoded)


def verify_token(
    document: BlockDocument,
    token: RevisionToken | str,
    *,
    secret: str = "",
) -> None:
    """Verify a token against a document or raise ``RevisionConflictError``."""
    parsed = decode_token(token) if isinstance(token, str) else token
    if parsed.document_id != document.id:
        raise RevisionConflictError(
            parsed.revision,
            document.revision,
            document_id=document.id,
            reason="document id mismatch",
        )
    if parsed.revision != document.revision:
        raise RevisionConflictError(
            parsed.revision,
            document.revision,
            document_id=document.id,
            reason="stale revision",
        )
    expected = compute_digest(document, secret=secret)
    if not hmac.compare_digest(parsed.digest, expected):
        raise RevisionConflictError(
            parsed.revision,
            document.revision,
            document_id=document.id,
            reason="content digest mismatch",
        )


def token_is_current(
    document: BlockDocument,
    token: RevisionToken | str,
    *,
    secret: str = "",
) -> bool:
    """Return whether a token matches a document without raising."""
    try:
        verify_token(document, token, secret=secret)
    except RevisionConflictError:
        return False
    return True


class RevisionManager:
    """Issue and verify tokens while retaining a short audit trail."""

    def __init__(self, *, secret: str = "", history_size: int = MAX_TOKEN_HISTORY) -> None:
        self._secret = secret
        self._history_size = max(1, history_size)
        self._history: list[RevisionToken] = []

    @property
    def history(self) -> tuple[RevisionToken, ...]:
        return tuple(self._history)

    def issue(self, document: BlockDocument) -> RevisionToken:
        """Mint and record a token."""
        token = issue_token(document, secret=self._secret)
        self._history.append(token)
        self._history = self._history[-self._history_size :]
        return token

    def verify(self, document: BlockDocument, token: RevisionToken | str) -> None:
        """Verify a token, raising ``RevisionConflictError`` on failure."""
        verify_token(document, token, secret=self._secret)

    def advance(
        self,
        document: BlockDocument,
        token: RevisionToken | str,
    ) -> BlockDocument:
        """Verify a token and return the next document revision."""
        self.verify(document, token)
        advanced = document.advanced()
        self.issue(advanced)
        return advanced

    def set_revision(self, document: BlockDocument, revision: int) -> BlockDocument:
        """Return a copy at an explicit revision and issue its token."""
        advanced = document.advanced(revision)
        self.issue(advanced)
        return advanced

    def clear(self) -> None:
        """Clear the retained token history."""
        self._history.clear()


def token_payload(token: RevisionToken) -> dict[str, Any]:
    """Return the encoded token's JSON payload."""
    return token.as_dict()


def reissue_token(
    token: RevisionToken,
    *,
    revision: int | None = None,
) -> RevisionToken:
    """Return a token copy with a refreshed nonce and optional revision."""
    return replace(
        token,
        revision=token.revision if revision is None else revision,
        nonce=secrets.token_urlsafe(8),
        issued_at=utc_now(),
    )


def token_revisions(tokens: Sequence[RevisionToken]) -> list[int]:
    """Return the revisions represented by a token sequence."""
    return [token.revision for token in tokens]
