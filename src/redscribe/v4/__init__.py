"""RedScribe v4 feature packages.

This package uses dynamic namespace discovery so that feature branches can add
new submodules without editing a static import list. Every v4 feature ships a
self-contained package under ``redscribe.v4.<slug>``; a module that exposes a
``register(api)`` callable is picked up automatically by :func:`register_all`.

The discovery helpers are deliberately dependency-free and deterministic:
iteration order is sorted, registration is idempotent, and failures are
isolated so one broken feature cannot disable the others.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from types import ModuleType
from typing import Any

__all__ = [
    "REGISTERED_MODULES",
    "discover_modules",
    "install_namespaces",
    "register_all",
    "reset_registration",
]

_REGISTER_CALLABLE = "register"
_INSTALLED = False
REGISTERED_MODULES: dict[str, ModuleType] = {}


def discover_modules() -> dict[str, ModuleType]:
    """Import and return every v4 submodule, keyed by its short name.

    Modules whose import raises are skipped so that a single incomplete
    feature cannot break discovery for the rest of the program.
    """
    discovered: dict[str, ModuleType] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda item: item.name):
        if info.name.startswith("_"):
            continue
        try:
            discovered[info.name] = importlib.import_module(f"{__name__}.{info.name}")
        except Exception:
            continue
    return discovered


def install_namespaces() -> dict[str, ModuleType]:
    """Populate the module namespace once and return the cached mapping.

    Idempotent: repeated calls return the same mapping without re-importing.
    """
    global _INSTALLED, REGISTERED_MODULES
    if not _INSTALLED:
        REGISTERED_MODULES = discover_modules()
        _INSTALLED = True
    return REGISTERED_MODULES


def reset_registration() -> None:
    """Clear cached modules (used by tests that install temporary features)."""
    global _INSTALLED, REGISTERED_MODULES
    _INSTALLED = False
    REGISTERED_MODULES = {}


def register_all(api: Any) -> list[str]:
    """Call ``register(api)`` on every discovered module that exposes it.

    Returns the sorted list of module names that registered successfully.
    Registration is additive and idempotent per module name.
    """
    registered: list[str] = []
    for name, module in sorted(install_namespaces().items()):
        hook: Callable[[Any], None] | None = getattr(module, _REGISTER_CALLABLE, None)
        if hook is None or not callable(hook):
            continue
        if name in registered:
            continue
        hook(api)
        registered.append(name)
    return registered
