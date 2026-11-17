"""Optional v2 API namespaces registered additively by feature branches."""

from __future__ import annotations

from redscribe.ui.web.v2.namespaces.engagements import (
    EngagementNamespace,
    configure,
    register,
    route_names,
)

__all__ = ["EngagementNamespace", "configure", "register", "route_names"]
