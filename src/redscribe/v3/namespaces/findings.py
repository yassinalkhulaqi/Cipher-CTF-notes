"""Findings namespace registration for the V3 API router."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from redscribe.v3.api.router import V3Router
from redscribe.v3.findings.routes import FindingRoutes

NAMESPACE = "findings"

_default_routes = FindingRoutes()


def default_routes() -> FindingRoutes:
    """Return the shared route handler bundle."""
    return _default_routes


def reset_default_routes() -> FindingRoutes:
    """Replace the shared handler bundle, mainly for isolated tests."""
    global _default_routes
    _default_routes = FindingRoutes()
    return _default_routes


def handlers() -> dict[str, Callable[[dict[str, Any], Mapping[str, str]], dict[str, Any]]]:
    """Return all findings namespace actions."""
    return _default_routes.handlers()


def register(router: V3Router) -> None:
    """Add every finding action to a V3 router."""
    for action, handler in handlers().items():
        router.add(NAMESPACE, action, handler)
