from __future__ import annotations

from redscribe.v4.contracts import Capability, CapabilitySet
from redscribe.v4.diagnostics import Diagnostics, HealthStatus
from redscribe.v4.preferences import Preferences


def test_diagnostics_all_ok() -> None:
    report = Diagnostics(route_count=10).run()
    assert report.status is HealthStatus.OK
    assert len(report.checks) == 5
    assert report.to_dict()["status"] == "ok"


def test_diagnostics_degraded_schema() -> None:
    report = Diagnostics(schema_version=5, route_count=10).run()
    assert report.status is HealthStatus.DEGRADED
    assert report.checks[0].detail == "vault needs migration"


def test_diagnostics_blocked_schema() -> None:
    report = Diagnostics(schema_version=99, route_count=10).run()
    assert report.status is HealthStatus.BLOCKED


def test_diagnostics_capabilities() -> None:
    limited = CapabilitySet(frozenset({Capability.READ}))
    report = Diagnostics(capabilities=limited, route_count=10).run()
    assert report.checks[1].status is HealthStatus.DEGRADED
    empty = Diagnostics(capabilities=CapabilitySet(frozenset()), route_count=10).run()
    assert empty.status is HealthStatus.BLOCKED


def test_diagnostics_preferences_and_routes() -> None:
    prefs = Preferences(motion="off")
    limited = CapabilitySet(frozenset({Capability.READ}))
    report = Diagnostics(preferences=prefs, capabilities=limited, route_count=0).run()
    assert report.checks[2].status is HealthStatus.DEGRADED
    assert report.checks[3].status is HealthStatus.DEGRADED
    assert report.checks[4].status is HealthStatus.DEGRADED
