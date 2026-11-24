"""Capability flags gated by optional extras and local configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

CAP_COMMANDS: Final[str] = "commands"
CAP_FINDINGS: Final[str] = "findings"
CAP_EVIDENCE_LAB: Final[str] = "evidence_lab"
CAP_GRAPH: Final[str] = "graph"
CAP_SEARCH_V2: Final[str] = "search_v2"
CAP_AUTOMATION: Final[str] = "automation"
CAP_REPORTS: Final[str] = "reports"
CAP_ACTIVITY: Final[str] = "activity"
CAP_PORTABILITY: Final[str] = "portability"
CAP_ENCRYPTION: Final[str] = "encryption"
CAP_PERFORMANCE: Final[str] = "performance"
CAP_I18N: Final[str] = "i18n"
CAP_EXTENSIONS: Final[str] = "extensions"
CAP_RELEASE: Final[str] = "release"

ALL_CAPABILITIES: tuple[str, ...] = (
    CAP_COMMANDS,
    CAP_FINDINGS,
    CAP_EVIDENCE_LAB,
    CAP_GRAPH,
    CAP_SEARCH_V2,
    CAP_AUTOMATION,
    CAP_REPORTS,
    CAP_ACTIVITY,
    CAP_PORTABILITY,
    CAP_ENCRYPTION,
    CAP_PERFORMANCE,
    CAP_I18N,
    CAP_EXTENSIONS,
    CAP_RELEASE,
)


class CapabilityError(RuntimeError):
    """Raised when a disabled capability is used."""


@dataclass(slots=True)
class Capabilities:
    """Set of enabled capabilities with strict checks."""

    enabled: frozenset[str] = field(default_factory=lambda: frozenset(ALL_CAPABILITIES))

    def has(self, capability: str) -> bool:
        """Return whether a capability is enabled."""
        return capability in self.enabled

    def require(self, capability: str) -> None:
        """Raise when a capability is disabled."""
        if not self.has(capability):
            raise CapabilityError(f"Capability is disabled: {capability}")

    def add(self, capability: str) -> Capabilities:
        """Return a new set with one capability enabled."""
        return Capabilities(enabled=self.enabled | {capability})

    def remove(self, capability: str) -> Capabilities:
        """Return a new set with one capability disabled."""
        return Capabilities(enabled=self.enabled - {capability})

    def missing(self) -> tuple[str, ...]:
        """Return disabled capabilities in stable order."""
        return tuple(sorted(set(ALL_CAPABILITIES) - self.enabled))

    def as_dict(self) -> dict[str, bool]:
        """Return a JSON-safe representation."""
        return {name: self.has(name) for name in ALL_CAPABILITIES}


default_capabilities = Capabilities()
