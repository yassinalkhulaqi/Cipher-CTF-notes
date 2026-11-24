"""Capability negotiation on top of the B00 capability and config contracts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from redscribe.v3.api_sdk.errors import CapabilityDeniedError, ReadOnlyViolationError
from redscribe.v3.capabilities import (
    ALL_CAPABILITIES,
    CAP_EXTENSIONS,
    Capabilities,
)
from redscribe.v3.config import V3Config, default_config


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    """Outcome of one capability check."""

    name: str
    granted: bool
    reason: str
    required_for: str = ""
    source: str = "negotiation"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "name": self.name,
            "granted": self.granted,
            "reason": self.reason,
            "required_for": self.required_for,
            "source": self.source,
        }


class CapabilityNegotiator:
    """Decides which optional features a local client may use."""

    def __init__(
        self,
        capabilities: Capabilities | None = None,
        config: V3Config | None = None,
    ) -> None:
        self.config: V3Config = config or default_config
        self.capabilities: Capabilities = (
            capabilities if capabilities is not None else self.config.capabilities()
        )

    def advertise(self) -> dict[str, bool]:
        """Return the capability map advertised to clients."""
        return self.capabilities.as_dict()

    def decide(self, name: str, *, required_for: str = "") -> CapabilityDecision:
        """Evaluate one capability without raising."""
        if name not in ALL_CAPABILITIES:
            return CapabilityDecision(
                name=name,
                granted=False,
                reason="unknown capability",
                required_for=required_for,
                source="catalog",
            )
        if self.capabilities.has(name):
            return CapabilityDecision(
                name=name,
                granted=True,
                reason="enabled by local configuration",
                required_for=required_for,
            )
        return CapabilityDecision(
            name=name,
            granted=False,
            reason="capability is disabled",
            required_for=required_for,
            source="local-config",
        )

    def negotiate(
        self,
        required: Iterable[str],
        *,
        required_for: str = "script",
    ) -> tuple[CapabilityDecision, ...]:
        """Evaluate a list of capabilities in stable order."""
        return tuple(self.decide(name, required_for=required_for) for name in sorted(set(required)))

    def require(self, name: str, *, required_for: str = "call") -> CapabilityDecision:
        """Raise when a capability is unavailable."""
        decision = self.decide(name, required_for=required_for)
        if not decision.granted:
            raise CapabilityDeniedError(
                f"Capability is unavailable: {name} ({decision.reason})",
                field="capability",
                context={"capability": name, "reason": decision.reason},
            )
        return decision

    def allow_write(self, *, opt_in: bool) -> CapabilityDecision:
        """Gate mutation with an explicit opt-in and configuration."""
        if not opt_in:
            raise ReadOnlyViolationError(
                "Writes require an explicit --allow-write opt-in",
                field="allow_write",
            )
        if not self.config.allow_extensions:
            raise CapabilityDeniedError(
                "Extension writes are disabled by local configuration",
                field="allow_extensions",
                context={"capability": CAP_EXTENSIONS},
            )
        return self.require(CAP_EXTENSIONS, required_for="write")

    def missing(self) -> tuple[str, ...]:
        """Return disabled capabilities in stable order."""
        return self.capabilities.missing()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe negotiation summary."""
        granted: list[str] = []
        denied: list[str] = []
        for name in ALL_CAPABILITIES:
            decision = self.decide(name)
            (granted if decision.granted else denied).append(name)
        return {
            "advertised": self.advertise(),
            "granted": granted,
            "denied": denied,
            "allow_extensions": self.config.allow_extensions,
            "offline_only": self.config.offline_only,
        }
