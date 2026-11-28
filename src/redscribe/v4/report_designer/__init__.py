"""v4 report designer: layouts, theme inheritance, pagination and export.

Importing this package has no side effects. Call :func:`register` to attach the
report routes to a v4 route registry; the v4 namespace loader picks this hook up
automatically. All operations are data-only and deterministic.
"""

from __future__ import annotations

from redscribe.v4.api_v4 import Route, RouteRegistry, global_registry
from redscribe.v4.report_designer.api import ReportApi, build_api

__all__ = [
    "ReportApi",
    "register",
]


def register(api: object | None = None) -> tuple[Route, ...]:
    """Attach report routes to ``api`` when possible, else the global registry.

    Repeated calls are idempotent: the underlying registry rejects duplicate
    prefixes, and this hook returns the already-registered report routes.
    """
    target = api if isinstance(api, ReportApi) else build_api()
    registry = api if isinstance(api, RouteRegistry) else global_registry()
    try:
        return target.register(registry)
    except ValueError:
        return tuple(route for route in registry.all() if route.prefix.startswith("/reports"))
