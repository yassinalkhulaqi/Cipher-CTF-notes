"""End-to-end local encryption for the v4 security vault.

The package is split into data-only contracts (:mod:`types`), domain services
(:mod:`service`), secret-free metadata persistence (:mod:`storage`), and v4
envelope routes (:mod:`api`). ``register(api)`` wires the vault into dynamic v4
namespace discovery without editing any shared registry.
"""

from __future__ import annotations

from redscribe.v4.vault_security.api import default_endpoint, register

__all__ = ["default_endpoint", "register"]
