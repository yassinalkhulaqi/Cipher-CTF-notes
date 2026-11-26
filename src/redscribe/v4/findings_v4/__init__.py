"""Findings v4: CVSS v4 scoring, governed lifecycle and remediation.

This package adds first-class findings to the v4 platform. It ships a typed
metric/vector contract, a deterministic scorer, a lifecycle-governed service,
indexed in-memory storage, capability-checked API handlers and a React studio.
Registration is additive and tolerant so the platform's dynamic namespace
discovery can call :func:`register` with any host object.
"""

from __future__ import annotations

from typing import Any

from .api import FindingApi, FindingRequest, FindingResponse
from .service import CvssV4Calculator, CvssV4Score, FindingError, FindingService
from .storage import FindingStore
from .types import (
    CvssV4Vector,
    Finding,
    LifecycleState,
    RetestRecord,
    RetestVerdict,
    Severity,
)

__all__ = [
    "CvssV4Calculator",
    "CvssV4Score",
    "CvssV4Vector",
    "Finding",
    "FindingApi",
    "FindingError",
    "FindingRequest",
    "FindingResponse",
    "FindingService",
    "FindingStore",
    "LifecycleState",
    "RetestRecord",
    "RetestVerdict",
    "Severity",
    "register",
]


def register(api: Any) -> None:
    """Register the findings route on a host that exposes a route registry."""
    registry = getattr(api, "registry", api)
    register_fn = getattr(registry, "register", None)
    if callable(register_fn):
        register_fn("/findings", "findings-v4")
