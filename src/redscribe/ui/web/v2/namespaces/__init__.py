"""Additive namespace registration for API v2."""

from __future__ import annotations

from redscribe.storage.db import Vault
from redscribe.ui.web.v2.namespaces import evidence
from redscribe.ui.web.v2.routes import ApiV2

INSTALLED_FLAG = "_v2_namespaces_installed"


def register_all(api: ApiV2) -> ApiV2:
    """Register every optional namespace on an API v2 instance."""
    evidence.register(api)
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


__all__ = ["install_namespaces", "installed", "register_all"]
