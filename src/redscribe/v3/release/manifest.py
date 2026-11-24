"""Release manifest aggregation used by the namespace route and docs."""

from __future__ import annotations

from typing import Any

from redscribe.v3.api.router import V3Router
from redscribe.v3.release.content import EMPTY_STATE_SPECS, ONBOARDING_SPECS, POLISH_CHECKS
from redscribe.v3.release.gates import GATE_DEFINITIONS
from redscribe.v3.release.models import (
    FRONTEND_SURFACES,
    RELEASE_ACTIONS,
    RELEASE_NAMESPACE,
    RELEASE_VERSION,
    phase_values,
)
from redscribe.v3.release.scenarios import SCENARIO_DESCRIPTIONS


def release_manifest(router: V3Router | None = None) -> dict[str, Any]:
    """Return a compact, deterministic description of the release toolkit."""
    registered: tuple[str, ...] = ()
    if router is not None:
        registered = tuple(
            action
            for action in RELEASE_ACTIONS
            if router.get(RELEASE_NAMESPACE, action) is not None
        )
    return {
        "version": RELEASE_VERSION,
        "namespace": RELEASE_NAMESPACE,
        "actions": list(RELEASE_ACTIONS),
        "registered_actions": list(registered),
        "phases": list(phase_values()),
        "scenarios": list(SCENARIO_DESCRIPTIONS),
        "frontend_surfaces": list(FRONTEND_SURFACES),
        "onboarding_steps": len(ONBOARDING_SPECS),
        "empty_states": len(EMPTY_STATE_SPECS),
        "polish_checks": len(POLISH_CHECKS),
        "gates": [definition.gate_id for definition in GATE_DEFINITIONS],
        "offline_only": True,
        "executes_user_code": False,
    }


def readiness_summary(
    *,
    golden_ok: bool,
    smoke_ok: bool,
    gates_ok: bool,
    golden_count: int = 0,
    smoke_count: int = 0,
    gate_count: int = 0,
) -> dict[str, Any]:
    """Combine the three release signals into one readiness verdict."""
    checks = {
        "golden_paths": golden_ok,
        "smoke_suite": smoke_ok,
        "hardening_gates": gates_ok,
    }
    ok = all(checks.values())
    return {
        "ready": ok,
        "verdict": "ship" if ok else "hold",
        "checks": checks,
        "evidence": {
            "scenarios": golden_count,
            "smoke_checks": smoke_count,
            "gates": gate_count,
        },
    }
