"""Additive namespace registration for API v2."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.routes import ApiV2

INSTALLED_FLAG = "_v2_namespaces_installed"


def _modules() -> list[Any]:
    modules: list[Any] = []
    for info in pkgutil.iter_modules(__path__):
        modules.append(importlib.import_module(f"{__name__}.{info.name}"))
    return modules


def register_all(api: ApiV2) -> ApiV2:
    """Register every optional namespace present in this checkout."""
    target: Any = api
    for module in _modules():
        register = getattr(module, "register", None)
        if callable(register):
            register(target)
    return api


def install_namespaces() -> None:
    """Ensure all API v2 instances receive optional namespace routes."""
    if getattr(ApiV2, INSTALLED_FLAG, False):
        return
    original_init = ApiV2.__init__

    def patched_init(self: ApiV2, vault: Vault) -> None:
        original_init(self, vault)
        register_all(self)

    init_name = "__init__"
    setattr(ApiV2, init_name, patched_init)
    setattr(ApiV2, INSTALLED_FLAG, True)


def installed() -> bool:
    """Return whether namespace installation has been applied."""
    return bool(getattr(ApiV2, INSTALLED_FLAG, False))


def __getattr__(name: str) -> Any:
    for module in _modules():
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(name)


__all__ = [
    "INSTALLED_FLAG",
    "ApiV2",
    "install_namespaces",
    "installed",
    "register_all",
]
