"""Auditable conflict decisions with a tamper-evident resolution ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v3.events.bus import EventBus
from redscribe.v3.events.redaction import RedactionPolicy
from redscribe.v3.events.types import DomainEvent, EventSeverity
from redscribe.v3.portability.canonical import digest_value
from redscribe.v3.portability.errors import ResolutionError
from redscribe.v3.portability.merge import (
    Conflict,
    MergeResult,
    ResolutionChoice,
    ResolutionStrategy,
    apply_resolution,
    require_choice,
    suggest_for,
)


@dataclass(frozen=True, slots=True)
class ResolutionEntry:
    """One immutable decision in the resolution audit trail."""

    sequence: int
    ref: str
    reason: str
    choice: str
    actor: str
    device: str
    decided_at: float
    note: str
    before_digest: str
    after_digest: str
    previous_hash: str
    entry_hash: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "sequence": self.sequence,
            "ref": self.ref,
            "reason": self.reason,
            "choice": self.choice,
            "actor": self.actor,
            "device": self.device,
            "decided_at": self.decided_at,
            "note": self.note,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "previous_hash": self.previous_hash,
            "entry_hash": self.entry_hash,
        }


def _entry_hash(payload: dict[str, Any]) -> str:
    """Hash the stable fields of a resolution entry."""
    return digest_value(
        {
            "sequence": payload["sequence"],
            "ref": payload["ref"],
            "reason": payload["reason"],
            "choice": payload["choice"],
            "actor": payload["actor"],
            "device": payload["device"],
            "decided_at": payload["decided_at"],
            "note": payload["note"],
            "before_digest": payload["before_digest"],
            "after_digest": payload["after_digest"],
            "previous_hash": payload["previous_hash"],
        }
    )


class ResolutionLedger:
    """Append-only, hash-chained audit trail of conflict decisions."""

    def __init__(self) -> None:
        self._entries: list[ResolutionEntry] = []

    def record(
        self,
        *,
        conflict: Conflict,
        choice: ResolutionChoice,
        actor: str,
        device: str,
        decided_at: float,
        note: str = "",
        before_digest: str,
        after_digest: str,
    ) -> ResolutionEntry:
        """Append one decision to the ledger."""
        previous = self._entries[-1].entry_hash if self._entries else "genesis"
        fields: dict[str, Any] = {
            "sequence": len(self._entries) + 1,
            "ref": conflict.ref,
            "reason": conflict.reason.value,
            "choice": choice.value,
            "actor": actor,
            "device": device,
            "decided_at": decided_at,
            "note": note,
            "before_digest": before_digest,
            "after_digest": after_digest,
            "previous_hash": previous,
        }
        entry = ResolutionEntry(**fields, entry_hash=_entry_hash(fields))
        self._entries.append(entry)
        return entry

    def all(self) -> tuple[ResolutionEntry, ...]:
        """Return all entries in sequence order."""
        return tuple(self._entries)

    def for_ref(self, ref: str) -> tuple[ResolutionEntry, ...]:
        """Return decisions affecting one entity reference."""
        return tuple(entry for entry in self._entries if entry.ref == ref)

    def verify_chain(self) -> bool:
        """Return whether the hash chain is intact from genesis."""
        previous = "genesis"
        for entry in self._entries:
            fields = entry.as_dict()
            if entry.previous_hash != previous or _entry_hash(fields) != entry.entry_hash:
                return False
            previous = entry.entry_hash
        return True

    def stats(self) -> dict[str, int]:
        """Return decision counts by choice."""
        stats: dict[str, int] = {}
        for entry in self._entries:
            stats[entry.choice] = stats.get(entry.choice, 0) + 1
        return dict(sorted(stats.items()))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "count": len(self._entries),
            "intact": self.verify_chain(),
            "stats": self.stats(),
            "entries": [entry.as_dict() for entry in self._entries],
        }


class ConflictResolver:
    """Applies conflict decisions and records why each one was made."""

    def __init__(
        self,
        ledger: ResolutionLedger | None = None,
        bus: EventBus | None = None,
        *,
        redaction: RedactionPolicy | None = None,
    ) -> None:
        self.ledger = ledger or ResolutionLedger()
        self.bus = bus or EventBus()
        self._redaction = redaction or RedactionPolicy()

    def resolve(
        self,
        result: MergeResult,
        conflict: Conflict,
        choice: ResolutionChoice,
        *,
        actor: str = "local",
        device: str = "local",
        decided_at: float = 0.0,
        note: str = "",
    ) -> tuple[MergeResult, ResolutionEntry]:
        """Apply one decision, audit it, and emit a redacted domain event."""
        require_choice(conflict, choice)
        before_digest = digest_value(conflict.as_dict())
        updated = apply_resolution(result, conflict, choice)
        after_digest = digest_value(
            {"ref": conflict.ref, "choice": choice.value, "clean": updated.clean}
        )
        entry = self.ledger.record(
            conflict=conflict,
            choice=choice,
            actor=actor,
            device=device,
            decided_at=decided_at,
            note=note,
            before_digest=before_digest,
            after_digest=after_digest,
        )
        self._emit(entry, conflict)
        return updated, entry

    def resolve_bulk(
        self,
        result: MergeResult,
        choices: dict[str, str],
        *,
        actor: str = "local",
        device: str = "local",
        decided_at: float = 0.0,
        default: ResolutionStrategy = ResolutionStrategy.MANUAL,
    ) -> tuple[MergeResult, tuple[ResolutionEntry, ...]]:
        """Apply decisions for every conflict, using a default for omissions."""
        current = result
        entries: list[ResolutionEntry] = []
        for conflict in result.conflicts:
            raw = choices.get(conflict.ref, "")
            try:
                choice = ResolutionChoice(raw) if raw else suggest_for(conflict, default)
            except ValueError as error:
                raise ResolutionError(
                    f"Unknown resolution choice for {conflict.ref}: {raw}"
                ) from error
            if choice is ResolutionChoice.MANUAL:
                raise ResolutionError(f"Conflict {conflict.ref} still requires a decision")
            current, entry = self.resolve(
                current,
                conflict,
                choice,
                actor=actor,
                device=device,
                decided_at=decided_at,
                note="bulk resolution",
            )
            entries.append(entry)
        return current, tuple(entries)

    def _emit(self, entry: ResolutionEntry, conflict: Conflict) -> None:
        """Publish a redacted resolution event to the shared event bus."""
        payload = self._redaction.apply(
            {
                "ref": conflict.ref,
                "reason": conflict.reason.value,
                "choice": entry.choice,
                "actor": entry.actor,
                "device": entry.device,
                "note": entry.note,
            }
        )
        self.bus.publish(
            DomainEvent(
                kind="portability.conflict.resolved",
                severity=EventSeverity.NOTICE,
                payload=payload,
                correlation_id=entry.ref,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of the ledger."""
        return self.ledger.as_dict()
