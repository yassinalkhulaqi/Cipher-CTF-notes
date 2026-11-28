"""Local diagnostics for the v4 kernel.

Diagnostics are read-only observations of local state. They never contact a
network and never execute user-supplied code.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from redscribe.v4.capabilities import FeatureFlag, FeatureGate
from redscribe.v4.contracts import Capability, CapabilitySet
from redscribe.v4.migrations_v4 import SCHEMA_VERSION
from redscribe.v4.preferences import Preferences


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The outcome of a single diagnostic check."""

    name: str
    status: HealthStatus
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status.value, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    """An ordered collection of checks with an overall status."""

    checks: tuple[CheckResult, ...]

    @property
    def status(self) -> HealthStatus:
        if any(check.status is HealthStatus.BLOCKED for check in self.checks):
            return HealthStatus.BLOCKED
        if any(check.status is HealthStatus.DEGRADED for check in self.checks):
            return HealthStatus.DEGRADED
        return HealthStatus.OK

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "checks": [check.to_dict() for check in self.checks],
        }


class Diagnostics:
    """Runs a fixed set of local checks against injected state."""

    def __init__(
        self,
        schema_version: int = SCHEMA_VERSION,
        capabilities: CapabilitySet | None = None,
        preferences: Preferences | None = None,
        route_count: int = 0,
    ) -> None:
        self.schema_version = schema_version
        self.capabilities = capabilities or CapabilitySet.full()
        self.preferences = preferences or Preferences()
        self.route_count = route_count

    def check_schema(self) -> CheckResult:
        if self.schema_version > SCHEMA_VERSION:
            return CheckResult("schema", HealthStatus.BLOCKED, "vault schema is newer than app")
        if self.schema_version < SCHEMA_VERSION:
            return CheckResult("schema", HealthStatus.DEGRADED, "vault needs migration")
        return CheckResult("schema", HealthStatus.OK, f"schema v{self.schema_version}")

    def check_capabilities(self) -> CheckResult:
        gate = FeatureGate(self.capabilities)
        enabled = gate.enabled_flags()
        if not enabled:
            return CheckResult("capabilities", HealthStatus.BLOCKED, "no features enabled")
        if len(enabled) < len(FeatureFlag):
            return CheckResult(
                "capabilities",
                HealthStatus.DEGRADED,
                f"{len(enabled)}/{len(FeatureFlag)} features enabled",
            )
        return CheckResult("capabilities", HealthStatus.OK, "all features enabled")

    def check_preferences(self) -> CheckResult:
        prefs = self.preferences
        if prefs.high_contrast and prefs.reduce_transparency:
            return CheckResult("preferences", HealthStatus.OK, "high-contrast, opaque")
        if prefs.motion == "off":
            return CheckResult("preferences", HealthStatus.DEGRADED, "motion disabled")
        return CheckResult("preferences", HealthStatus.OK, f"locale {prefs.locale}")

    def check_routes(self) -> CheckResult:
        if self.route_count == 0:
            return CheckResult("routes", HealthStatus.DEGRADED, "no v4 routes registered")
        return CheckResult("routes", HealthStatus.OK, f"{self.route_count} routes")

    def check_encryption(self) -> CheckResult:
        if self.capabilities.allows(Capability.ENCRYPT):
            return CheckResult("encryption", HealthStatus.OK, "encryption capability present")
        return CheckResult("encryption", HealthStatus.DEGRADED, "vault encryption unavailable")

    def run(self) -> DiagnosticReport:
        return DiagnosticReport(
            checks=(
                self.check_schema(),
                self.check_capabilities(),
                self.check_preferences(),
                self.check_routes(),
                self.check_encryption(),
            )
        )
