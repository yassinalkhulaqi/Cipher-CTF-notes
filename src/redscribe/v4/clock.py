"""A small injectable clock so v4 features can be tested deterministically."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


class Clock:
    """Returns UTC timestamps and supports a frozen mode for tests."""

    def __init__(self, frozen_at: datetime | None = None) -> None:
        self._frozen_at = frozen_at

    def now(self) -> datetime:
        if self._frozen_at is not None:
            return self._frozen_at
        return datetime.now(timezone.utc)

    def iso(self) -> str:
        return self.now().isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def advance(self, delta: timedelta) -> None:
        if self._frozen_at is None:
            self._frozen_at = self.now()
        self._frozen_at = self._frozen_at + delta

    def freeze(self, at: datetime) -> None:
        self._frozen_at = at

    def unfreeze(self) -> None:
        self._frozen_at = None

    @property
    def is_frozen(self) -> bool:
        return self._frozen_at is not None


SYSTEM_CLOCK = Clock()
