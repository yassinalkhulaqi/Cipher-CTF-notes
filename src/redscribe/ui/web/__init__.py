"""Web-based frontend for RedScribe (pywebview window or browser)."""

from __future__ import annotations

from redscribe.ui.web.api import Api, ApiError
from redscribe.ui.web.launcher import run as run_web_ui
from redscribe.ui.web.server import ApiServer

__all__ = ["Api", "ApiError", "ApiServer", "run_web_ui"]
