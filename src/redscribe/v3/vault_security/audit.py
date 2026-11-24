"""Redacted audit trail with structured export for the security vault."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.events.redaction import redact_payload, redact_text

MAX_DETAIL_DEPTH = 8
MAX_DETAIL_ITEMS = 40
TextRedactor = Callable[[str], str]


class AuditAction(str, Enum):
    """Security-relevant actions recorded in the vault audit trail."""

    SETUP = "vault.setup"
    UNLOCK = "vault.unlock"
    LOCK = "vault.lock"
    ROTATE = "vault.rotate"
    RECOVERY_ISSUE = "vault.recovery.issue"
    RECOVERY_REDEEM = "vault.recovery.redeem"
    POLICY_UPDATE = "vault.policy.update"
    AUDIT_EXPORT = "vault.audit.export"
    ACCESS_DENIED = "vault.access.denied"


class AuditOutcome(str, Enum):
    """Outcome classification for one audit entry."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """A sanitized, immutable audit record."""

    entry_id: str
    action: AuditAction
    outcome: AuditOutcome
    actor: str
    subject: str
    timestamp: float
    detail: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "entry_id": self.entry_id,
            "action": self.action.value,
            "outcome": self.outcome.value,
            "actor": redact_text(self.actor),
            "subject": self.subject,
            "timestamp": self.timestamp,
            "detail": dict(self.detail),
            "request_id": self.request_id,
        }


@dataclass(frozen=True, slots=True)
class AuditFilter:
    """Query criteria for the audit trail."""

    actions: tuple[AuditAction, ...] = ()
    outcomes: tuple[AuditOutcome, ...] = ()
    actor: str = ""
    subject: str = ""
    since: float = 0.0
    until: float = 0.0
    limit: int = 100
    offset: int = 0
    request_id: str = ""

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        if self.offset < 0:
            raise ValueError("offset cannot be negative")
        if self.until and self.since > self.until:
            raise ValueError("since cannot be later than until")

    def matches(self, entry: AuditEntry) -> bool:
        """Return whether an entry satisfies this filter."""
        if self.actions and entry.action not in self.actions:
            return False
        if self.outcomes and entry.outcome not in self.outcomes:
            return False
        if self.actor and self.actor.casefold() not in entry.actor.casefold():
            return False
        if self.subject and self.subject not in entry.subject:
            return False
        if self.since and entry.timestamp < self.since:
            return False
        if self.until and entry.timestamp > self.until:
            return False
        return not (self.request_id and self.request_id != entry.request_id)

    def apply(self, entries: Sequence[AuditEntry]) -> tuple[AuditEntry, ...]:
        """Filter and paginate an ordered entry sequence."""
        selected = [entry for entry in entries if self.matches(entry)]
        return tuple(selected[self.offset : self.offset + self.limit])

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "actions": [action.value for action in self.actions],
            "outcomes": [outcome.value for outcome in self.outcomes],
            "actor": self.actor,
            "subject": self.subject,
            "since": self.since,
            "until": self.until,
            "limit": self.limit,
            "offset": self.offset,
            "request_id": self.request_id,
        }


@dataclass(frozen=True, slots=True)
class AuditExport:
    """A fully redacted, serializable audit export."""

    format: str
    generated_at: float
    entries: tuple[AuditEntry, ...]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.format not in ("json", "jsonl"):
            raise ValueError("format must be 'json' or 'jsonl'")

    @property
    def count(self) -> int:
        """Number of entries in this export."""
        return len(self.entries)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "format": self.format,
            "generated_at": self.generated_at,
            "count": len(self.entries),
            "warnings": list(self.warnings),
            "entries": [entry.as_dict() for entry in self.entries],
        }

    def to_json(self) -> str:
        """Serialize the export as a single JSON document."""
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    def to_jsonl(self) -> str:
        """Serialize one JSON object per line for streaming consumers."""
        lines = [
            json.dumps(entry.as_dict(), sort_keys=True, separators=(",", ":"))
            for entry in self.entries
        ]
        return "\n".join(lines) + ("\n" if lines else "")

    def render(self) -> str:
        """Render the export in its declared format."""
        return self.to_jsonl() if self.format == "jsonl" else self.to_json()


class AuditTrail:
    """Append-only in-memory audit log with mandatory redaction."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        text_redactor: TextRedactor | None = None,
        max_entries: int = 5000,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._clock: Clock = clock or SystemClock()
        self._redactor = text_redactor or (lambda value: value)
        self._entries: list[AuditEntry] = []
        self._sequence = 0
        self._max_entries = max_entries

    @property
    def max_entries(self) -> int:
        """Maximum number of retained audit entries."""
        return self._max_entries

    def record(
        self,
        action: AuditAction,
        *,
        actor: str,
        subject: str,
        outcome: AuditOutcome = AuditOutcome.SUCCESS,
        detail: Mapping[str, Any] | None = None,
        request_id: str = "",
        timestamp: float | None = None,
    ) -> AuditEntry:
        """Append a sanitized audit entry."""
        if not actor or not subject:
            raise ValueError("actor and subject are required")
        self._sequence += 1
        entry = AuditEntry(
            entry_id=f"audit_{self._sequence:06d}",
            action=action,
            outcome=outcome,
            actor=actor[:120],
            subject=subject[:160],
            timestamp=self._clock.now_timestamp() if timestamp is None else timestamp,
            detail=self.sanitize(detail or {}),
            request_id=request_id[:128],
        )
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            del self._entries[0]
        return entry

    def sanitize(self, detail: Mapping[str, Any]) -> dict[str, Any]:
        """Apply key and text redaction to an arbitrary detail mapping."""
        cleaned = redact_payload(dict(detail))
        return {
            key: self._scrub_value(value, 0)
            for key, value in list(cleaned.items())[:MAX_DETAIL_ITEMS]
        }

    def _scrub_value(self, value: Any, depth: int) -> Any:
        if depth > MAX_DETAIL_DEPTH:
            return "[truncated]"
        if isinstance(value, str):
            return self._redactor(redact_text(value))
        if isinstance(value, Mapping):
            return {
                str(key): self._scrub_value(item, depth + 1)
                for key, item in list(value.items())[:MAX_DETAIL_ITEMS]
            }
        if isinstance(value, (list, tuple)):
            return [self._scrub_value(item, depth + 1) for item in list(value)[:MAX_DETAIL_ITEMS]]
        return value

    def entries(self) -> tuple[AuditEntry, ...]:
        """Return all retained entries in append order."""
        return tuple(self._entries)

    def query(self, criteria: AuditFilter | None = None) -> tuple[AuditEntry, ...]:
        """Return entries matching a filter."""
        return (criteria or AuditFilter()).apply(self._entries)

    def export(
        self,
        *,
        criteria: AuditFilter | None = None,
        fmt: str = "json",
        warnings: tuple[str, ...] = (),
    ) -> AuditExport:
        """Export redacted entries in JSON or JSONL form."""
        if fmt not in ("json", "jsonl"):
            raise ValueError("format must be 'json' or 'jsonl'")
        return AuditExport(
            format=fmt,
            generated_at=self._clock.now_timestamp(),
            entries=self.query(criteria),
            warnings=warnings,
        )

    def stats(self) -> dict[str, Any]:
        """Return aggregate counts by outcome and action."""
        return {
            "total": len(self._entries),
            "by_outcome": {
                outcome.value: sum(1 for entry in self._entries if entry.outcome is outcome)
                for outcome in AuditOutcome
            },
            "by_action": {
                action.value: sum(1 for entry in self._entries if entry.action is action)
                for action in AuditAction
            },
        }

    def clear(self) -> None:
        """Drop all retained entries."""
        self._entries.clear()


def parse_audit_filter(payload: Mapping[str, Any]) -> AuditFilter:
    """Build an audit filter from an API request mapping."""
    return AuditFilter(
        actions=tuple(AuditAction(str(value)) for value in payload.get("actions", ())),
        outcomes=tuple(AuditOutcome(str(value)) for value in payload.get("outcomes", ())),
        actor=str(payload.get("actor", "")),
        subject=str(payload.get("subject", "")),
        since=float(payload.get("since", 0.0)),
        until=float(payload.get("until", 0.0)),
        limit=int(payload.get("limit", 100)),
        offset=int(payload.get("offset", 0)),
        request_id=str(payload.get("request_id", "")),
    )
