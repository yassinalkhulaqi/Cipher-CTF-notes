"""Universal namespace discovery and registration for V3 features.

This module is intentionally free of static imports of feature modules. Each
branch adds a new module under ``redscribe.v3.namespaces`` that exposes
``register(router)``; discovery picks it up automatically. That keeps early
branches mergeable before later modules exist.
"""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import Any

from redscribe.v3.api.router import V3Router

_installed: set[int] = set()


def discover_modules(package: str = "redscribe.v3.namespaces") -> tuple[ModuleType, ...]:
    """Import every non-private submodule of a namespace package."""
    container = importlib.import_module(package)
    paths = getattr(container, "__path__", None)
    if paths is None:
        return ()
    modules: list[ModuleType] = []
    for info in pkgutil.iter_modules(paths):
        if info.name.startswith("_"):
            continue
        modules.append(importlib.import_module(f"{package}.{info.name}"))
    return tuple(modules)


def register_all(router: V3Router, package: str = "redscribe.v3.namespaces") -> int:
    """Register every discovered namespace module that exposes ``register``."""
    installed = 0
    for module in discover_modules(package):
        callback = getattr(module, "register", None)
        if callable(callback):
            callback(router)
            installed += 1
    return installed


def install_namespaces(router: V3Router, package: str = "redscribe.v3.namespaces") -> bool:
    """Install namespaces once per router instance."""
    identity = id(router)
    if identity in _installed:
        return False
    register_all(router, package)
    _installed.add(identity)
    return True


def namespace_names(package: str = "redscribe.v3.namespaces") -> tuple[str, ...]:
    """Return discovered namespace module names."""
    container = importlib.import_module(package)
    paths = getattr(container, "__path__", None)
    if paths is None:
        return ()
    return tuple(
        sorted(info.name for info in pkgutil.iter_modules(paths) if not info.name.startswith("_"))
    )


def has_namespace(name: str, package: str = "redscribe.v3.namespaces") -> bool:
    """Return whether a namespace module is discoverable."""
    return name in namespace_names(package)


def load_namespace(name: str, package: str = "redscribe.v3.namespaces") -> Any:
    """Load a namespace module by name."""
    if not has_namespace(name, package):
        raise ValueError(f"Unknown namespace: {name}")
    return importlib.import_module(f"{package}.{name}")


__all__ = [
    "discover_modules",
    "has_namespace",
    "install_namespaces",
    "load_namespace",
    "namespace_names",
    "register_all",
]
