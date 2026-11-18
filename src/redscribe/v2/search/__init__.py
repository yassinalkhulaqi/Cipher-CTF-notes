"""Incremental search, ranking, saved queries, and command parsing."""

from __future__ import annotations

from redscribe.v2.search.commands import (
    CommandCatalog,
    CommandPlan,
    CommandSuggestion,
    ParsedCommand,
    SuggestionResult,
)
from redscribe.v2.search.filters import apply_filters, facet_values
from redscribe.v2.search.index import InvertedIndex
from redscribe.v2.search.models import (
    DEFAULT_FIELD_BOOSTS,
    FacetCount,
    FilterClause,
    IndexedDocument,
    IndexStats,
    IndexUpdate,
    ParsedQuery,
    QueryTerm,
    ResultGroup,
    SavedQuery,
    ScoreBreakdown,
    SearchHit,
    SearchResult,
    Snippet,
)
from redscribe.v2.search.query import QueryParser, describe_query, query_fingerprint
from redscribe.v2.search.ranking import RankingConfig, RankingEngine
from redscribe.v2.search.saved import SavedQueryStore
from redscribe.v2.search.service import SearchService, create_search_service
from redscribe.v2.search.snippets import build_snippet
from redscribe.v2.search.synonyms import SynonymSet

__all__ = [
    "DEFAULT_FIELD_BOOSTS",
    "CommandCatalog",
    "CommandPlan",
    "CommandSuggestion",
    "FacetCount",
    "FilterClause",
    "IndexStats",
    "IndexUpdate",
    "IndexedDocument",
    "InvertedIndex",
    "ParsedCommand",
    "ParsedQuery",
    "QueryParser",
    "QueryTerm",
    "RankingConfig",
    "RankingEngine",
    "ResultGroup",
    "SavedQuery",
    "SavedQueryStore",
    "ScoreBreakdown",
    "SearchHit",
    "SearchResult",
    "SearchService",
    "Snippet",
    "SuggestionResult",
    "SynonymSet",
    "apply_filters",
    "build_snippet",
    "create_search_service",
    "describe_query",
    "facet_values",
    "query_fingerprint",
]
