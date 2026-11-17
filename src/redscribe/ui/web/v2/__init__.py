"""Versioned API v2 surface layered on top of the v1 dispatch API."""

from __future__ import annotations

from redscribe.ui.web.v2.contracts import (
    API_VERSION,
    Envelope,
    Page,
    V2Error,
    V2ErrorCode,
    envelope,
    error_envelope,
)
from redscribe.ui.web.v2.router import V2Router
from redscribe.ui.web.v2.routes import ApiV2

__all__ = [
    "API_VERSION",
    "ApiV2",
    "Envelope",
    "Page",
    "V2Error",
    "V2ErrorCode",
    "V2Router",
    "envelope",
    "error_envelope",
]
