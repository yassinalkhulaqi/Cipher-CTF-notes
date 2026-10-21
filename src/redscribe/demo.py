"""Backward-compatible imports for the canonical demo seeder.

New code should import from :mod:`redscribe.services.demo`.
"""

from __future__ import annotations

from redscribe.services.demo import seed_demo

__all__ = ["seed_demo"]
