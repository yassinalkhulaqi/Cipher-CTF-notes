"""v4 playbook automation: declarative DAGs, dry-run traces and schedules.

This package exposes immutable data contracts, a cycle-safe planner, a dry-run
executor that never executes external commands, and a v4 API surface. Importing
the package has no side effects: call :func:`register` to attach the routes.
"""

from __future__ import annotations

from redscribe.v4.api_v4 import Route, RouteRegistry, global_registry
from redscribe.v4.automation_v4.api import AutomationApi, build_api

__all__ = [
    "AutomationApi",
    "register",
]


def register(api: object | None = None) -> tuple[Route, ...]:
    """Kernel-compatible ``register(api)`` hook for the automation routes.

    The kernel passes an opaque application object; when it is one of our own
    APIs or route registries we reuse it, otherwise we build a fresh API and
    attach routes to the process-wide registry. Repeated calls are idempotent.
    """
    target = api if isinstance(api, AutomationApi) else build_api()
    registry = api if isinstance(api, RouteRegistry) else global_registry()
    try:
        return target.register(registry)
    except ValueError:
        return tuple(route for route in registry.all() if route.prefix.startswith("/automation"))
