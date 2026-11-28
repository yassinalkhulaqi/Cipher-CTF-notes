"""A minimal, additive API v4 route registry.

Feature branches register their own route prefixes through :func:`register_routes`;
they never edit this file. The registry keeps routes sorted and validates route
shapes so the shell can render an API explorer deterministically.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

ROUTE_PATTERN = re.compile(r"^/[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*$")


@dataclass(frozen=True, slots=True)
class Route:
    """A single registered API route."""

    prefix: str
    name: str
    handler: Callable[..., object] | None = None

    def __post_init__(self) -> None:
        if not ROUTE_PATTERN.match(self.prefix):
            raise ValueError(f"Invalid route prefix: {self.prefix}")
        if not self.name:
            raise ValueError("route name must not be empty")

    @property
    def full_path(self) -> str:
        return f"/api/v4/{self.prefix.lstrip('/')}"

    def to_dict(self) -> dict[str, str]:
        return {"prefix": self.prefix, "name": self.name, "path": self.full_path}


class RouteRegistry:
    """An append-only registry of v4 routes."""

    def __init__(self) -> None:
        self._routes: dict[str, Route] = {}

    def register(
        self, prefix: str, name: str, handler: Callable[..., object] | None = None
    ) -> Route:
        normalized = prefix if prefix.startswith("/") else f"/{prefix}"
        route = Route(prefix=normalized, name=name, handler=handler)
        if route.full_path in self._routes:
            raise ValueError(f"route already registered: {route.full_path}")
        self._routes[route.full_path] = route
        return route

    def get(self, full_path: str) -> Route | None:
        return self._routes.get(full_path)

    def all(self) -> list[Route]:
        return sorted(self._routes.values(), key=lambda item: item.full_path)

    def serialize(self) -> list[dict[str, str]]:
        return [route.to_dict() for route in self.all()]

    def __len__(self) -> int:
        return len(self._routes)


_GLOBAL = RouteRegistry()


def register_routes(prefix: str, name: str, handler: Callable[..., object] | None = None) -> Route:
    """Register a route on the process-wide registry."""
    return _GLOBAL.register(prefix, name, handler)


def global_registry() -> RouteRegistry:
    return _GLOBAL
