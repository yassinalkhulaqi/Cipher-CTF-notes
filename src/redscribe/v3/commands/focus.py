"""Focus-session state machine with data-only snapshots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.clock import Clock, SystemClock

FocusListener = Callable[[str, "FocusSession"], None]


class FocusError(RuntimeError):
    """Raised for illegal focus-session transitions."""


class FocusStatus(str, Enum):
    """Lifecycle of a focus session."""

    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"

    @classmethod
    def parse(cls, value: str) -> FocusStatus:
        """Parse a status string with a stable error message."""
        for status in cls:
            if status.value == value.strip().casefold():
                return status
        raise FocusError(f"Unknown focus status: {value}")


@dataclass(frozen=True, slots=True)
class FocusSession:
    """An immutable snapshot of a focus session."""

    id: str
    label: str
    started_at: float
    status: FocusStatus = FocusStatus.ACTIVE
    target: str = ""
    restore_pane: str = ""
    interruptions: int = 0
    ended_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.id or len(self.id) > 80:
            raise FocusError("Focus session id must be 1-80 characters")
        if not self.label.strip():
            raise FocusError("Focus session label cannot be blank")

    @property
    def elapsed(self) -> float:
        """Elapsed active time at snapshot creation."""
        if self.started_at <= 0:
            return 0.0
        end = self.ended_at or self.started_at
        return max(0.0, end - self.started_at)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.id,
            "label": self.label,
            "started_at": self.started_at,
            "status": self.status.value,
            "target": self.target,
            "restore_pane": self.restore_pane,
            "interruptions": self.interruptions,
            "ended_at": self.ended_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FocusSession:
        """Rebuild a session from persisted data."""
        return cls(
            id=str(payload.get("id", "")),
            label=str(payload.get("label", "")),
            started_at=float(payload.get("started_at", 0.0)),
            status=FocusStatus.parse(str(payload.get("status", "active"))),
            target=str(payload.get("target", "")),
            restore_pane=str(payload.get("restore_pane", "")),
            interruptions=int(payload.get("interruptions", 0)),
            ended_at=float(payload.get("ended_at", 0.0)),
        )


@dataclass(slots=True)
class FocusSessionManager:
    """Owns focus sessions without ever touching the UI directly."""

    clock: Clock = field(default_factory=SystemClock)
    _current: FocusSession | None = None
    _history: list[FocusSession] = field(default_factory=list)
    _listeners: list[FocusListener] = field(default_factory=list)
    _counter: int = 0

    def subscribe(self, callback: FocusListener) -> None:
        """Register a session-change listener."""
        self._listeners.append(callback)

    def _emit(self, action: str, session: FocusSession) -> None:
        """Notify listeners of a transition."""
        for callback in tuple(self._listeners):
            callback(action, session)

    def _replace(self, **changes: Any) -> FocusSession:
        """Replace the current session with an updated immutable copy."""
        if self._current is None:
            raise FocusError("No active focus session")
        payload = self._current.as_dict()
        payload.update(
            {
                key: value.value if isinstance(value, FocusStatus) else value
                for key, value in changes.items()
            }
        )
        updated = FocusSession(
            id=str(payload["id"]),
            label=str(payload["label"]),
            started_at=float(payload["started_at"]),
            status=FocusStatus.parse(str(payload["status"])),
            target=str(payload["target"]),
            restore_pane=str(payload["restore_pane"]),
            interruptions=int(payload["interruptions"]),
            ended_at=float(payload["ended_at"]),
        )
        self._current = updated
        return updated

    def start(
        self,
        label: str,
        *,
        target: str = "",
        restore_pane: str = "",
    ) -> FocusSession:
        """Start a new session, ending any previous one."""
        if self._current is not None and self._current.status is not FocusStatus.ENDED:
            raise FocusError("A focus session is already running")
        self._counter += 1
        session = FocusSession(
            id=f"focus_{self._counter}",
            label=label,
            started_at=self.clock.now_timestamp(),
            target=target,
            restore_pane=restore_pane,
        )
        self._current = session
        self._emit("started", session)
        return session

    def pause(self) -> FocusSession:
        """Pause the active session."""
        if self._current is None or self._current.status is not FocusStatus.ACTIVE:
            raise FocusError("Only an active session can be paused")
        session = self._replace(status=FocusStatus.PAUSED)
        self._emit("paused", session)
        return session

    def resume(self) -> FocusSession:
        """Resume a paused session."""
        if self._current is None or self._current.status is not FocusStatus.PAUSED:
            raise FocusError("Only a paused session can be resumed")
        session = self._replace(status=FocusStatus.ACTIVE)
        self._emit("resumed", session)
        return session

    def interrupt(self, reason: str = "notification") -> FocusSession:
        """Record an interruption without ending the session."""
        if self._current is None or self._current.status is FocusStatus.ENDED:
            raise FocusError("No active focus session to interrupt")
        session = self._replace(interruptions=self._current.interruptions + 1)
        self._emit(f"interrupted:{reason}", session)
        return session

    def end(self) -> FocusSession:
        """End the session and archive it."""
        if self._current is None or self._current.status is FocusStatus.ENDED:
            raise FocusError("No active focus session to end")
        session = self._replace(status=FocusStatus.ENDED, ended_at=self.clock.now_timestamp())
        self._history.append(session)
        self._emit("ended", session)
        return session

    def current(self) -> FocusSession | None:
        """Return the current session snapshot."""
        return self._current

    def history(self) -> tuple[FocusSession, ...]:
        """Return archived sessions in end order."""
        return tuple(self._history)

    def restore_target(self) -> str:
        """Return the pane that should regain focus after the session."""
        if self._current is None:
            return ""
        return self._current.restore_pane

    def status(self) -> dict[str, Any]:
        """Return a UI-friendly status payload."""
        session = self._current
        return {
            "active": session is not None and session.status is not FocusStatus.ENDED,
            "paused": session is not None and session.status is FocusStatus.PAUSED,
            "session": session.as_dict() if session is not None else None,
            "completed": len(self._history),
        }

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable manager snapshot."""
        return {
            "counter": self._counter,
            "current": self._current.as_dict() if self._current is not None else None,
            "history": [session.as_dict() for session in self._history],
        }

    def load(self, snapshot: dict[str, Any]) -> None:
        """Restore a manager snapshot."""
        current = snapshot.get("current")
        history = snapshot.get("history", ())
        if not isinstance(history, list):
            raise FocusError("Focus history must be a list")
        self._counter = int(snapshot.get("counter", 0))
        self._current = FocusSession.from_dict(current) if isinstance(current, dict) else None
        self._history = [FocusSession.from_dict(item) for item in history if isinstance(item, dict)]
