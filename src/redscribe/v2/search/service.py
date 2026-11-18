"""High-level orchestration of indexing, ranking, and command search."""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from typing import Any

from redscribe.domain.models import Node
from redscribe.storage.db import Vault
from redscribe.v2.search.commands.catalog import CommandCatalog
from redscribe.v2.search.commands.grammar import command_grammar
from redscribe.v2.search.commands.models import ParsedCommand
from redscribe.v2.search.commands.suggestions import (
    complete_command,
    suggest_commands,
)
from redscribe.v2.search.filters import apply_filters, facet_values
from redscribe.v2.search.index import InvertedIndex
from redscribe.v2.search.models import (
    DEFAULT_FIELD_BOOSTS,
    MAX_SEARCH_LIMIT,
    SNIPPET_WIDTH,
    FacetCount,
    FilterClause,
    IndexedDocument,
    IndexedField,
    IndexUpdate,
    ParsedQuery,
    SearchResult,
    SortKey,
)
from redscribe.v2.search.query import QueryParser, describe_query
from redscribe.v2.search.ranking import RankingConfig, RankingEngine, group_hits
from redscribe.v2.search.saved import SavedQueryStore
from redscribe.v2.search.snippets import build_document_snippet
from redscribe.v2.search.synonyms import SynonymSet
from redscribe.v2.search.tokenizer import tokenize


class SearchService:
    """Wire the vault to the incremental index and ranking services."""

    def __init__(
        self,
        vault: Vault,
        *,
        synonyms: SynonymSet | None = None,
        ranker: RankingEngine | None = None,
    ) -> None:
        self._vault = vault
        self._synonyms = synonyms if synonyms is not None else SynonymSet()
        self._index = InvertedIndex()
        self._ranker = ranker if ranker is not None else RankingEngine(RankingConfig())
        self._parser = QueryParser(self._synonyms)
        self._saved = SavedQueryStore(vault)
        self._commands = CommandCatalog.default()
        self._synced = False

    @property
    def index(self) -> InvertedIndex:
        return self._index

    @property
    def saved(self) -> SavedQueryStore:
        return self._saved

    @property
    def commands(self) -> CommandCatalog:
        return self._commands

    @property
    def ranker(self) -> RankingEngine:
        return self._ranker

    def _build_document(self, node: Node) -> IndexedDocument:
        path = self._vault.path_of(node.id, include_self=False)
        values: dict[str, str] = {
            "title": node.title,
            "content": node.content,
            "tags": ", ".join(node.tag_list),
            "target": node.target,
            "flag": node.flag,
            "path": path,
        }
        fields = tuple(
            IndexedField(
                name=name,
                text=text,
                tokens=tokenize(text, field=name),
                boost=DEFAULT_FIELD_BOOSTS[name],
            )
            for name, text in values.items()
        )
        metadata: dict[str, Any] = {
            "id": node.id,
            "node_id": node.id,
            "title": node.title,
            "kind": node.kind,
            "status": node.status,
            "difficulty": node.difficulty,
            "tags": tuple(node.tag_list),
            "tag": tuple(node.tag_list),
            "target": node.target,
            "flag": node.flag,
            "path": path,
            "pinned": node.pinned,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
            "content_length": len(node.content),
            "group": path.split(" / ", 1)[0] if path else "vault root",
        }
        return IndexedDocument(doc_id=node.id, fields=fields, metadata=metadata)

    def documents(self) -> list[IndexedDocument]:
        """Build fresh snapshots for all live notes."""
        return [self._build_document(node) for node in self._vault.live_nodes() if node.is_note]

    def sync(self, *, force: bool = False) -> IndexUpdate:
        """Bring the index up to date with the vault."""
        if force:
            update = self._index.rebuild(self.documents())
        else:
            update = self._index.sync(self.documents())
        self._synced = True
        return update

    def reindex(self) -> IndexUpdate:
        """Rebuild the full index and return its update summary."""
        return self.sync(force=True)

    def parse(
        self,
        text: str,
        *,
        sort: str | None = None,
        group_by: str = "",
        filters: Sequence[FilterClause] = (),
    ) -> ParsedQuery:
        """Parse a query and append any filters supplied out of band."""
        parsed = self._parser.parse(text, sort=sort, group_by=group_by)
        if not filters:
            return parsed
        from dataclasses import replace

        return replace(parsed, filters=(*parsed.filters, *filters))

    def search(
        self,
        text: str,
        *,
        limit: int = 20,
        sort: str | None = None,
        group_by: str = "",
        filters: Sequence[FilterClause] = (),
        facet_field: str = "",
        width: int = SNIPPET_WIDTH,
    ) -> SearchResult:
        """Run a full search and return ranked hits with metadata."""
        started = time.perf_counter()
        query = self.parse(text, sort=sort, group_by=group_by, filters=filters)
        self.sync()
        documents = apply_filters(self._index.documents(), query.filters)
        capped_limit = max(0, min(limit, MAX_SEARCH_LIMIT))
        sort_key = query.sort if sort is not None else SortKey.RELEVANCE
        hits = self._ranker.rank(
            query,
            documents,
            self._index,
            limit=capped_limit,
            group_by=group_by,
            sort=sort_key,
            width=width,
        )
        facets: tuple[FacetCount, ...] = ()
        if facet_field:
            facets = facet_values(documents, facet_field)
        suggestions = self._term_suggestions(query)
        return SearchResult(
            query=query,
            hits=tuple(hits),
            total=len(hits),
            facets=facets,
            suggestions=suggestions,
            generation=self._index.generation,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )

    def _term_suggestions(self, query: ParsedQuery, *, limit: int = 6) -> tuple[str, ...]:
        positives = [term for term in query.positive if not term.synonym and not term.phrase]
        if not positives:
            return ()
        term = positives[-1].value
        return self._index.prefix_terms(term, limit=limit)

    def suggest(self, text: str, *, limit: int = 8) -> tuple[str, ...]:
        """Suggest indexed terms and saved query names for a prefix."""
        prefix = text.strip().casefold()
        if not prefix:
            return ()
        results: list[str] = []
        for term in self._index.prefix_terms(prefix, limit=limit):
            if term not in results:
                results.append(term)
        for item in self._saved.list(limit=MAX_SEARCH_LIMIT):
            if prefix in item.name.casefold() and item.name not in results:
                results.append(item.name)
            if prefix in item.query.casefold() and item.query not in results:
                results.append(item.query)
        return tuple(results[: max(0, limit)])

    def facets(self, field: str, *, limit: int = 20) -> tuple[FacetCount, ...]:
        """Return facet counts for one metadata field."""
        self.sync()
        return facet_values(self._index.documents(), field, limit=limit)

    def snippet(self, node_id: int, query: str, *, width: int = SNIPPET_WIDTH) -> dict[str, Any]:
        """Build a highlighted snippet for a single document."""
        self.sync()
        parsed = self._parser.parse(query)
        document = self._index.document(node_id)
        if document is None:
            return {}
        return build_document_snippet(document, parsed, width=width).as_dict()

    def status(self) -> dict[str, Any]:
        """Return index and service status for diagnostics."""
        update = self.sync()
        stats = self._index.stats().as_dict()
        return {
            **stats,
            "synced": self._synced,
            "last_update": update.as_dict(),
            "saved_queries": len(self._saved.list(limit=MAX_SEARCH_LIMIT)),
            "commands": len(self._commands.all()),
            "synonyms": self._synonyms.size,
        }

    def term_dictionary(self, *, prefix: str = "", limit: int = 50) -> tuple[str, ...]:
        """Return indexed vocabulary terms for completion and diagnostics."""
        if prefix:
            return self._index.prefix_terms(prefix, limit=limit)
        return self._index.vocabulary()[: max(0, limit)]

    def parse_command(self, text: str) -> ParsedCommand:
        """Parse a command using the built-in catalog."""
        return self._commands.parse(text)

    def command_suggestions(self, text: str, *, limit: int = 8) -> tuple[Any, ...]:
        """Return ranked command suggestions including saved queries."""
        return suggest_commands(
            text,
            self._commands,
            saved=self._saved.list(limit=MAX_SEARCH_LIMIT),
            limit=limit,
        )

    def command_completion(
        self,
        text: str,
        *,
        cursor: int | None = None,
        limit: int = 8,
    ) -> Any:
        """Complete a command at the given cursor position."""
        vocabulary = self._index.vocabulary()
        return complete_command(
            text,
            self._commands,
            cursor=cursor,
            saved=self._saved.list(limit=MAX_SEARCH_LIMIT),
            vocabulary=vocabulary,
            limit=limit,
        )

    def command_help(self) -> dict[str, Any]:
        """Return the grammar and command catalog for help surfaces."""
        return {
            "grammar": command_grammar(),
            "commands": self._commands.as_dict(),
        }

    def run_command(
        self,
        text: str,
        *,
        limit: int = 20,
        group_by: str = "",
    ) -> dict[str, Any]:
        """Parse a command and return a preview of the action it would take."""
        parsed = self.parse_command(text)
        if parsed.node is None:
            return {"ok": False, "issues": [issue.as_dict() for issue in parsed.issues]}
        plan = self._commands.plan(parsed.node)
        result: dict[str, Any] = {
            "ok": not parsed.issues,
            "issues": [issue.as_dict() for issue in parsed.issues],
            "plan": plan.as_dict(),
        }
        if plan.action == "search":
            query = plan.query or parsed.node.text
            result["result"] = self.search(
                query,
                limit=limit,
                group_by=group_by or plan.metadata.get("group", ""),
                sort=str(plan.metadata.get("sort", "relevance")),
            ).as_dict()
        elif plan.action.startswith("saved_"):
            action = plan.action.removeprefix("saved_")
            if action == "run" and plan.query:
                named = next(
                    (
                        item
                        for item in self._saved.list()
                        if item.name.casefold() == plan.query.casefold()
                    ),
                    None,
                )
                if named is not None:
                    result["result"] = self.search(
                        named.query, limit=limit, group_by=group_by
                    ).as_dict()
        return result

    def describe(self, text: str) -> dict[str, Any]:
        """Return a normalized query description without running it."""
        return describe_query(self.parse(text))

    def grouped(self, text: str, group_by: str, *, limit: int = MAX_SEARCH_LIMIT) -> list[Any]:
        """Return search hits grouped by a metadata field."""
        result = self.search(text, limit=limit, group_by=group_by)
        return list(group_hits(result.hits, group_by))


def create_search_service(vault: Vault) -> SearchService:
    """Create a service with default configuration."""
    return SearchService(vault)


def document_summaries(documents: Iterable[IndexedDocument]) -> tuple[dict[str, Any], ...]:
    """Return compact document summaries for diagnostics."""
    return tuple(
        {
            "id": document.doc_id,
            "title": document.title,
            "path": document.path,
            "fields": [field.name for field in document.fields],
        }
        for document in documents
    )
