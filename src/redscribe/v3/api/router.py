"""Additive V3 route registry with dynamic namespace discovery."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from redscribe.v3.api.errors import V3Error, V3ErrorCode

Handler = Callable[[dict[str, Any], Mapping[str, str]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class RouteSpec:
    """One registered V3 route."""

    namespace: str
    action: str
    handler: Handler
    methods: tuple[str, ...] = ("POST",)
    public: bool = False

    @property
    def path(self) -> str:
        """Canonical route path."""
        return f"/api/v3/{self.namespace}/{self.action}"

    @property
    def key(self) -> tuple[str, str]:
        """Registry key."""
        return (self.namespace, self.action)


class NamespaceModule(Protocol):
    """Optional protocol implemented by discovered namespace modules."""

    def register(self, router: V3Router) -> None:
        """Register routes on the supplied router."""
        ...


@dataclass(slots=True)
class V3Router:
    """Route registry that never requires editing a central dispatch table."""

    _routes: dict[tuple[str, str], RouteSpec] = field(default_factory=dict)
    _installed: set[str] = field(default_factory=set)

    def add(
        self,
        namespace: str,
        action: str,
        handler: Handler,
        *,
        methods: tuple[str, ...] = ("POST",),
        public: bool = False,
    ) -> RouteSpec:
        """Register a route, rejecting duplicate namespace/action pairs."""
        key = (namespace, action)
        if key in self._routes:
            raise V3Error(
                V3ErrorCode.CONFLICT,
                f"Route already registered: /api/v3/{namespace}/{action}",
            )
        spec = RouteSpec(namespace, action, handler, methods, public)
        self._routes[key] = spec
        return spec

    def get(self, namespace: str, action: str) -> RouteSpec | None:
        """Look up a route."""
        return self._routes.get((namespace, action))

    def dispatch(
        self,
        namespace: str,
        action: str,
        body: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        *,
        method: str = "POST",
    ) -> dict[str, Any]:
        """Dispatch a request to a registered handler."""
        spec = self.get(namespace, action)
        if spec is None:
            raise V3Error(V3ErrorCode.UNKNOWN_ROUTE, f"Unknown route: {namespace}/{action}")
        if method not in spec.methods:
            raise V3Error(
                V3ErrorCode.UNKNOWN_ROUTE,
                f"Method {method} is not allowed for {spec.path}",
            )
        return spec.handler(dict(body or {}), dict(headers or {}))

    def routes(self) -> tuple[RouteSpec, ...]:
        """Return all routes in stable order."""
        return tuple(self._routes[key] for key in sorted(self._routes))

    def namespaces(self) -> tuple[str, ...]:
        """Return registered namespace names."""
        return tuple(sorted({namespace for namespace, _ in self._routes}))

    def manifest(self) -> dict[str, Any]:
        """Return a route manifest for docs and the frontend API client."""
        return {
            "version": "3.0",
            "namespaces": list(self.namespaces()),
            "routes": [
                {
                    "path": route.path,
                    "methods": list(route.methods),
                    "public": route.public,
                }
                for route in self.routes()
            ],
        }

    def install_namespaces(self, package: str | None = None) -> int:
        """Discover and install namespace modules with ``register(router)``.

        Discovery is idempotent per package, so calling this from multiple
        branches or services never registers a route twice.
        """
        target = package or "redscribe.v3.namespaces"
        if target in self._installed:
            return 0
        module = importlib.import_module(target)
        paths = getattr(module, "__path__", None)
        if paths is None:
            return 0
        installed = 0
        for info in pkgutil.iter_modules(paths):
            if info.name.startswith("_"):
                continue
            submodule = importlib.import_module(f"{target}.{info.name}")
            register = getattr(submodule, "register", None)
            if callable(register):
                register(self)
                installed += 1
        self._installed.add(target)
        return installed

    def size(self) -> int:
        """Return the number of registered routes."""
        return len(self._routes)


_default_router = V3Router()
installed_flag = False


def default_router() -> V3Router:
    """Return the shared router, installing namespaces on first use."""
    global installed_flag
    if not installed_flag:
        _default_router.install_namespaces()
        installed_flag = True
    return _default_router


def register_system_routes(router: V3Router) -> None:
    """Register the always-present system namespace."""

    def manifest(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {"manifest": router.manifest(), "echo": body.get("echo", "")}

    def health(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {"status": "ok", "version": "3.0", "routes": router.size()}

    router.add("system", "manifest", manifest, public=True)
    router.add("system", "health", health, public=True)
