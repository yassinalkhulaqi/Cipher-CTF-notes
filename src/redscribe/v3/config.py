"""Local configuration model for V3 services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.capabilities import ALL_CAPABILITIES, Capabilities

DEFAULT_PAGE_SIZE = 50
DEFAULT_MAX_RESULTS = 2000


@dataclass(frozen=True, slots=True)
class V3Config:
    """Configuration shared by all V3 feature services."""

    api_version: str = "3.0"
    schema_version: int = 5
    page_size: int = DEFAULT_PAGE_SIZE
    max_results: int = DEFAULT_MAX_RESULTS
    rate_limit: int = 120
    rate_window_seconds: float = 60.0
    redact_activity: bool = True
    emit_events: bool = True
    offline_only: bool = True
    allow_extensions: bool = False
    enabled_capabilities: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.page_size < 1 or self.page_size > 200:
            raise ValueError("page_size must be between 1 and 200")
        if self.max_results < 1:
            raise ValueError("max_results must be positive")
        if self.rate_limit < 1 or self.rate_window_seconds <= 0:
            raise ValueError("rate limits must be positive")
        for capability in self.enabled_capabilities:
            if capability not in ALL_CAPABILITIES:
                raise ValueError(f"Unknown capability: {capability}")

    def capabilities(self) -> Capabilities:
        """Build the capability set from configuration."""
        if not self.enabled_capabilities:
            return Capabilities()
        return Capabilities(enabled=frozenset(self.enabled_capabilities))

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "api_version": self.api_version,
            "schema_version": self.schema_version,
            "page_size": self.page_size,
            "max_results": self.max_results,
            "rate_limit": self.rate_limit,
            "rate_window_seconds": self.rate_window_seconds,
            "redact_activity": self.redact_activity,
            "emit_events": self.emit_events,
            "offline_only": self.offline_only,
            "allow_extensions": self.allow_extensions,
            "enabled_capabilities": list(self.enabled_capabilities),
        }


default_config = V3Config()
