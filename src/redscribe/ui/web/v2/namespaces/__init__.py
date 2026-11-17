"""Optional v2 API namespaces that extend the platform kernel registry."""

from __future__ import annotations

from redscribe.ui.web.v2.namespaces.search import register as register_search
from redscribe.ui.web.v2.routes import ApiV2

__all__ = ["ApiV2", "register_search"]
