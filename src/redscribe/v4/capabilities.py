"""Capability flags and feature gating for the v4 program.

Capabilities are data: a capability registry declares what a feature needs, and
a resolver decides what the current session grants. Nothing here executes code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from redscribe.v4.contracts import Capability, CapabilitySet


class FeatureFlag(str, Enum):
    """Named feature gates used by UI affordances and API routes."""

    INBOX = "inbox"
    CVSS_V4 = "cvss_v4"
    EVIDENCE_LAB = "evidence_lab"
    BLOCKS_PRO = "blocks_pro"
    QUERY_LANGUAGE = "query_language"
    AUTOMATION = "automation"
    REPORT_DESIGNER = "report_designer"
    GRAPH_WORKBENCH = "graph_workbench"
    SECURITY_VAULT = "security_vault"
    A11Y_I18N = "a11y_i18n"


@dataclass(frozen=True, slots=True)
class FeatureRequirement:
    """The capabilities a feature needs to be enabled."""

    flag: FeatureFlag
    required: frozenset[Capability] = field(default_factory=frozenset)
    min_version: str = "v4"

    def satisfied_by(self, granted: CapabilitySet, version: str = "v4") -> bool:
        if version != self.min_version:
            return False
        return all(granted.allows(capability) for capability in self.required)


DEFAULT_REQUIREMENTS: dict[FeatureFlag, FeatureRequirement] = {
    FeatureFlag.INBOX: FeatureRequirement(
        FeatureFlag.INBOX, frozenset({Capability.READ, Capability.WRITE})
    ),
    FeatureFlag.CVSS_V4: FeatureRequirement(
        FeatureFlag.CVSS_V4, frozenset({Capability.READ, Capability.WRITE})
    ),
    FeatureFlag.EVIDENCE_LAB: FeatureRequirement(
        FeatureFlag.EVIDENCE_LAB, frozenset({Capability.READ})
    ),
    FeatureFlag.BLOCKS_PRO: FeatureRequirement(
        FeatureFlag.BLOCKS_PRO, frozenset({Capability.READ, Capability.WRITE})
    ),
    FeatureFlag.QUERY_LANGUAGE: FeatureRequirement(
        FeatureFlag.QUERY_LANGUAGE, frozenset({Capability.READ})
    ),
    FeatureFlag.AUTOMATION: FeatureRequirement(
        FeatureFlag.AUTOMATION, frozenset({Capability.READ, Capability.AUTOMATE})
    ),
    FeatureFlag.REPORT_DESIGNER: FeatureRequirement(
        FeatureFlag.REPORT_DESIGNER, frozenset({Capability.READ, Capability.EXPORT})
    ),
    FeatureFlag.GRAPH_WORKBENCH: FeatureRequirement(
        FeatureFlag.GRAPH_WORKBENCH, frozenset({Capability.READ})
    ),
    FeatureFlag.SECURITY_VAULT: FeatureRequirement(
        FeatureFlag.SECURITY_VAULT, frozenset({Capability.ENCRYPT})
    ),
    FeatureFlag.A11Y_I18N: FeatureRequirement(FeatureFlag.A11Y_I18N, frozenset({Capability.READ})),
}


class FeatureGate:
    """Resolve whether a feature is available for a capability set."""

    def __init__(
        self,
        granted: CapabilitySet,
        requirements: dict[FeatureFlag, FeatureRequirement] | None = None,
        version: str = "v4",
    ) -> None:
        self.granted = granted
        self.requirements = dict(requirements or DEFAULT_REQUIREMENTS)
        self.version = version

    def is_enabled(self, flag: FeatureFlag) -> bool:
        requirement = self.requirements.get(flag)
        if requirement is None:
            return False
        return requirement.satisfied_by(self.granted, self.version)

    def enabled_flags(self) -> list[FeatureFlag]:
        return sorted(
            (flag for flag in self.requirements if self.is_enabled(flag)),
            key=lambda item: item.value,
        )

    def require(self, flag: FeatureFlag) -> None:
        if not self.is_enabled(flag):
            raise PermissionError(f"feature disabled: {flag.value}")

    def with_capability(self, capability: Capability) -> FeatureGate:
        granted = CapabilitySet(frozenset(set(self.granted.granted) | {capability}))
        return FeatureGate(granted, self.requirements, self.version)
