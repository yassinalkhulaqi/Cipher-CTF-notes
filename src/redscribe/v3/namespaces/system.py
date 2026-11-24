"""System namespace routes for the V3 API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from redscribe.v3.api.router import V3Router
from redscribe.v3.capabilities import ALL_CAPABILITIES, Capabilities
from redscribe.v3.config import default_config
from redscribe.v3.migrations.v5 import SCHEMA_VERSION, migration_checksum


def register(router: V3Router) -> None:
    """Register system capability and health routes."""

    def capabilities(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        enabled = default_config.capabilities()
        return {
            "capabilities": enabled.as_dict(),
            "all": list(ALL_CAPABILITIES),
            "missing": list(enabled.missing()),
        }

    def info(body: dict[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
        return {
            "api_version": default_config.api_version,
            "schema_version": SCHEMA_VERSION,
            "migration_checksum": migration_checksum(),
            "offline_only": default_config.offline_only,
            "capabilities": Capabilities().as_dict(),
        }

    router.add("system", "capabilities", capabilities, public=True)
    router.add("system", "info", info, public=True)
