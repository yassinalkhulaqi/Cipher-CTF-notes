"""Web-based frontend for RedScribe (pywebview window or browser)."""

from __future__ import annotations

from redscribe.ui.web.api import Api, ApiError
from redscribe.ui.web.auth import (
    ANY_PURPOSE,
    DOWNLOAD_PURPOSE,
    SESSION_PURPOSE,
    AuthOutcome,
    TokenManager,
)
from redscribe.ui.web.launcher import run as run_web_ui
from redscribe.ui.web.security import AuditEvent, AuditLog, AuthRateLimiter, RateLimitDecision
from redscribe.ui.web.server import ApiServer

__all__ = [
    "ANY_PURPOSE",
    "DOWNLOAD_PURPOSE",
    "SESSION_PURPOSE",
    "Api",
    "ApiError",
    "ApiServer",
    "AuditEvent",
    "AuditLog",
    "AuthOutcome",
    "AuthRateLimiter",
    "RateLimitDecision",
    "TokenManager",
    "run_web_ui",
]
