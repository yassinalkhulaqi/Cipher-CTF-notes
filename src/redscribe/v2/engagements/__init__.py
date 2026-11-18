"""Engagement-core domain package.

This package implements engagements, scope, targets, assets, services,
credentials, findings, lifecycle workflows, coverage, and rollups as pure,
storage-agnostic Python modules.
"""

from __future__ import annotations

from redscribe.v2.engagements.errors import EngagementError, EngagementErrorCode
from redscribe.v2.engagements.repositories import EngagementStore
from redscribe.v2.engagements.services import EngagementService

__all__ = ["EngagementError", "EngagementErrorCode", "EngagementService", "EngagementStore"]
