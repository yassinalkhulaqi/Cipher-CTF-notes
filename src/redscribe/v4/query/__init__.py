"""Structured query language for the v4 platform.

The package provides a safe expression parser, an in-memory evaluator, faceted
navigation, clustering, and named/saved query persistence. Public imports are
re-exported here so feature branches can depend on one stable module path.
"""

from __future__ import annotations

from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.query.api import QueryApi, register_routes
from redscribe.v4.query.service import (
    ClusteringEngine,
    FacetEngine,
    QueryLexer,
    QueryParser,
    SavedQueryService,
    SearchEvaluator,
)
from redscribe.v4.query.storage import QueryStore, QueryStoreView
from redscribe.v4.query.types import (
    BooleanOp,
    FacetDefinition,
    FacetValue,
    FieldName,
    Operator,
    ParsedQuery,
    QueryToken,
    ResultCluster,
    SavedQuery,
)

__all__ = [
    "BooleanOp",
    "ClusteringEngine",
    "FacetDefinition",
    "FacetEngine",
    "FacetValue",
    "FieldName",
    "Operator",
    "ParsedQuery",
    "QueryApi",
    "QueryLexer",
    "QueryParser",
    "QueryStore",
    "QueryStoreView",
    "QueryToken",
    "ResultCluster",
    "SavedQuery",
    "SavedQueryService",
    "SearchEvaluator",
    "register",
    "register_routes",
]


def register(api: object | None = None) -> RouteRegistry:
    """Register the query routes on a v4 registry during namespace discovery."""
    if isinstance(api, RouteRegistry):
        return register_routes(api)
    return register_routes()
