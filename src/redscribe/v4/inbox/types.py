"""Immutable capture records and validation for the v4 capture inbox.

The inbox accepts text from many places — manual notes, links, snippets, flag
tokens, and clipboard pastes — but stores all of them as one validated record.
Every value crossing into the domain is normalized here: whitespace is folded,
tags are canonicalized, identifiers and timestamps are checked, and a stable
content hash is derived from the normalized text so duplicate captures can be
detected without comparing raw blobs.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any

from redscribe.v4.contracts import is_entity_id, new_entity_id
from redscribe.v4.events import utc_now

MAX_RAW_LENGTH = 20000
MAX_TAG_LENGTH = 48
MAX_TAGS = 12
TAG_PATTERN = re.compile(r"^[a-z][a-z0-9_./-]{0,47}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FLAG_PATTERN = re.compile(r"\bflag\{[^{}\n]{1,200}\}", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
WHITESPACE_PATTERN = re.compile(r"\s+")


class CaptureSource(str, Enum):
    """Where a capture originated.

    CLIPBOARD is never inferred from text: it is an explicit assertion made by
    the caller because pasted text is indistinguishable from typed text.
    """

    MANUAL = "manual"
    LINK = "link"
    SNIPPET = "snippet"
    FLAG = "flag"
    CLIPBOARD = "clipboard"

    @classmethod
    def parse(cls, value: str) -> CaptureSource:
        """Parse a source value with a stable error message."""
        normalized = value.strip().casefold()
        for source in cls:
            if source.value == normalized:
                return source
        raise ValueError(f"Unknown capture source: {value}")

    @property
    def label(self) -> str:
        """A human-readable label for chips and filters."""
        return self.value.replace("_", " ").title()

    @property
    def auto_detected(self) -> bool:
        """Whether the parser may infer this source from raw text."""
        return self is not CaptureSource.CLIPBOARD


class TriageState(str, Enum):
    """The four positions a capture can occupy in the triage funnel."""

    UNTRIAGED = "untriaged"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ARCHIVED = "archived"

    @classmethod
    def parse(cls, value: str) -> TriageState:
        """Parse a state value with a stable error message."""
        normalized = value.strip().casefold()
        for state in cls:
            if state.value == normalized:
                return state
        raise ValueError(f"Unknown triage state: {value}")

    @property
    def label(self) -> str:
        """A human-readable label for filters and badges."""
        return self.value.title()

    @property
    def is_terminal(self) -> bool:
        """Whether the state marks the end of the first triage pass."""
        return self in (TriageState.ACCEPTED, TriageState.REJECTED, TriageState.ARCHIVED)


def normalize_raw(raw: str) -> str:
    """Fold whitespace and reject empty or oversized capture text."""
    if not isinstance(raw, str):
        raise TypeError("raw must be a string")
    if len(raw) > MAX_RAW_LENGTH:
        raise ValueError(f"raw exceeds {MAX_RAW_LENGTH} characters")
    normalized = WHITESPACE_PATTERN.sub(" ", raw).strip()
    if not normalized:
        raise ValueError("raw must not be blank")
    return normalized


def compute_content_hash(raw: str) -> str:
    """Return the stable SHA-256 dedupe key for capture text."""
    return hashlib.sha256(normalize_raw(raw).casefold().encode("utf-8")).hexdigest()


def normalize_tag(tag: str) -> str:
    """Canonicalize one tag into lowercase slug form."""
    if not isinstance(tag, str):
        raise TypeError("tag must be a string")
    candidate = tag.strip().casefold().replace(" ", "-")
    if not candidate or not TAG_PATTERN.match(candidate):
        raise ValueError(f"Invalid tag: {tag}")
    if len(candidate) > MAX_TAG_LENGTH:
        raise ValueError(f"Tag exceeds {MAX_TAG_LENGTH} characters: {tag}")
    return candidate


def normalize_tags(tags: Iterable[str]) -> tuple[str, ...]:
    """Canonicalize, deduplicate, and sort a collection of tags."""
    if isinstance(tags, (str, bytes)):
        raise TypeError("tags must be an iterable of strings, not a single string")
    result: set[str] = set()
    for tag in tags:
        result.add(normalize_tag(tag))
    if len(result) > MAX_TAGS:
        raise ValueError(f"at most {MAX_TAGS} tags are allowed")
    return tuple(sorted(result))


def validate_confidence(value: float) -> float:
    """Validate a confidence score and return it as a float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("confidence must be a number")
    confidence = float(value)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")
    return confidence


def validate_timestamp(value: str) -> str:
    """Validate an ISO-8601 timestamp and preserve its original form."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("created_at must be a non-empty ISO-8601 string")
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"Invalid created_at timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError("created_at must include a timezone")
    return value.strip()


@dataclass(frozen=True, slots=True)
class CaptureDraft:
    """The parser's structured interpretation of raw capture text."""

    raw: str
    source: CaptureSource
    tags: tuple[str, ...]
    confidence: float
    urls: tuple[str, ...]
    flags: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", normalize_raw(self.raw))
        if not isinstance(self.source, CaptureSource):
            raise TypeError("source must be a CaptureSource")
        object.__setattr__(self, "tags", normalize_tags(self.tags))
        object.__setattr__(self, "confidence", validate_confidence(self.confidence))
        object.__setattr__(self, "urls", tuple(str(url) for url in self.urls))
        object.__setattr__(self, "flags", tuple(str(flag) for flag in self.flags))

    @property
    def summary(self) -> str:
        """A one-line description used for accessibility labels."""
        details = [self.source.label]
        if self.flags:
            details.append(f"{len(self.flags)} flag(s)")
        if self.urls:
            details.append(f"{len(self.urls)} link(s)")
        return ", ".join(details)

    def to_item(
        self,
        item_id: str | None = None,
        created_at: str | None = None,
        state: TriageState = TriageState.UNTRIAGED,
    ) -> CaptureItem:
        """Materialize a draft as a persisted capture item."""
        return CaptureItem.create(
            raw=self.raw,
            source=self.source,
            tags=self.tags,
            confidence=self.confidence,
            created_at=created_at,
            item_id=item_id,
            state=state,
        )


@dataclass(frozen=True, slots=True)
class CaptureItem:
    """One immutable, validated capture in the universal inbox."""

    id: str
    raw: str
    source: CaptureSource
    state: TriageState
    tags: tuple[str, ...]
    confidence: float
    created_at: str
    content_hash: str

    def __post_init__(self) -> None:
        if not is_entity_id(self.id):
            raise ValueError(f"Invalid capture id: {self.id}")
        object.__setattr__(self, "raw", normalize_raw(self.raw))
        if not isinstance(self.source, CaptureSource):
            raise TypeError("source must be a CaptureSource")
        if not isinstance(self.state, TriageState):
            raise TypeError("state must be a TriageState")
        object.__setattr__(self, "tags", normalize_tags(self.tags))
        object.__setattr__(self, "confidence", validate_confidence(self.confidence))
        object.__setattr__(self, "created_at", validate_timestamp(self.created_at))
        if not isinstance(self.content_hash, str) or not HASH_PATTERN.match(self.content_hash):
            raise ValueError("content_hash must be 64 lowercase hex characters")
        if self.content_hash != compute_content_hash(self.raw):
            raise ValueError("content_hash does not match raw content")

    @property
    def is_triaged(self) -> bool:
        """Whether the capture has left the untriaged queue."""
        return self.state is not TriageState.UNTRIAGED

    @property
    def tag_line(self) -> str:
        """A compact, stable representation of the tag list."""
        return " ".join(f"#{tag}" for tag in self.tags)

    def has_tag(self, tag: str) -> bool:
        """Return whether the item carries a canonicalized tag."""
        return normalize_tag(tag) in self.tags

    def with_state(self, state: TriageState) -> CaptureItem:
        """Return a copy of the item in a new state."""
        if not isinstance(state, TriageState):
            raise TypeError("state must be a TriageState")
        return replace(self, state=state)

    def with_tags(self, tags: Iterable[str]) -> CaptureItem:
        """Return a copy of the item with a replacement tag set."""
        return replace(self, tags=normalize_tags(tags))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "id": self.id,
            "raw": self.raw,
            "source": self.source.value,
            "state": self.state.value,
            "tags": list(self.tags),
            "confidence": self.confidence,
            "created_at": self.created_at,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CaptureItem:
        """Deserialize and revalidate a capture dictionary."""
        raw = str(data.get("raw", ""))
        item_id = str(data.get("id", ""))
        return cls(
            id=item_id,
            raw=raw,
            source=CaptureSource.parse(str(data.get("source", ""))),
            state=TriageState.parse(str(data.get("state", TriageState.UNTRIAGED.value))),
            tags=normalize_tags(data.get("tags", ())),
            confidence=validate_confidence(float(data.get("confidence", 0.0))),
            created_at=str(data.get("created_at") or utc_now()),
            content_hash=str(data.get("content_hash", compute_content_hash(raw))),
        )

    @classmethod
    def create(
        cls,
        raw: str,
        source: CaptureSource = CaptureSource.MANUAL,
        tags: Iterable[str] = (),
        confidence: float = 0.5,
        created_at: str | None = None,
        item_id: str | None = None,
        state: TriageState = TriageState.UNTRIAGED,
    ) -> CaptureItem:
        """Build a validated item, deriving its id, hash, and timestamp."""
        if created_at is None:
            created_at = utc_now()
        return cls(
            id=item_id or new_entity_id(),
            raw=raw,
            source=source,
            state=state,
            tags=normalize_tags(tags),
            confidence=validate_confidence(confidence),
            created_at=validate_timestamp(created_at),
            content_hash=compute_content_hash(raw),
        )


__all__ = [
    "FLAG_PATTERN",
    "HASH_PATTERN",
    "MAX_RAW_LENGTH",
    "MAX_TAGS",
    "MAX_TAG_LENGTH",
    "TAG_PATTERN",
    "URL_PATTERN",
    "CaptureDraft",
    "CaptureItem",
    "CaptureSource",
    "TriageState",
    "compute_content_hash",
    "normalize_raw",
    "normalize_tag",
    "normalize_tags",
    "validate_confidence",
    "validate_timestamp",
]
