"""Backward-compatible imports for the canonical SQLite vault.

New code should import from :mod:`redscribe.storage.db`.
"""

from __future__ import annotations

from redscribe.storage.db import SCHEMA_VERSION, Vault

__all__ = ["SCHEMA_VERSION", "Vault"]
