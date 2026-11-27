"""Graph workbench feature slice for RedScribe v4.

This package models link analysis over vault entities: typed nodes and edges,
deterministic layouts, composable filters, named snapshots, and read-only API
routes. It is discovered by ``redscribe.v4.register_all`` through its ``register``
hook and never requires edits to shared registries.
"""

from __future__ import annotations

from redscribe.v4.api_v4 import RouteRegistry

from .api import register as register_graph_routes

__all__ = ["register", "register_graph_routes"]


def register(api: RouteRegistry | object) -> None:
    """Register the graph workbench routes on a v4 registry."""
    register_graph_routes(api)
