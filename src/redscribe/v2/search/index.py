"""An incremental inverted index over vault note snapshots."""

from __future__ import annotations

import fnmatch
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from redscribe.domain.fuzzy import edit_distance
from redscribe.v2.search.models import (
    IndexedDocument,
    IndexStats,
    IndexUpdate,
    Posting,
    TermStats,
    Token,
    utc_now,
)
from redscribe.v2.search.tokenizer import index_terms, tokenize

PostingMap = dict[str, dict[int, dict[str, Posting]]]


class InvertedIndex:
    """Maintain term postings incrementally as documents change."""

    def __init__(self, *, clock: Callable[[], str] = utc_now) -> None:
        self._clock = clock
        self._documents: dict[int, IndexedDocument] = {}
        self._fingerprints: dict[int, str] = {}
        self._postings: PostingMap = defaultdict(lambda: defaultdict(dict))
        self._generation = 0
        self._rebuilds = 0
        self._updated_at = clock()

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def updated_at(self) -> str:
        return self._updated_at

    def __len__(self) -> int:
        return len(self._documents)

    def __contains__(self, doc_id: object) -> bool:
        return doc_id in self._documents

    def add(self, document: IndexedDocument) -> None:
        """Insert or replace one document and bump the generation."""
        if document.doc_id in self._documents:
            self.remove(document.doc_id)
        self._insert(document)
        self._generation += 1
        self._updated_at = self._clock()

    def update(self, document: IndexedDocument) -> None:
        """Alias for :meth:`add` used by callers with update semantics."""
        self.add(document)

    def remove(self, doc_id: int) -> bool:
        """Remove one document from all postings lists."""
        document = self._documents.pop(doc_id, None)
        if document is None:
            return False
        self._fingerprints.pop(doc_id, None)
        for term in list(self._postings):
            by_document = self._postings[term]
            by_document.pop(doc_id, None)
            if not by_document:
                del self._postings[term]
        self._generation += 1
        self._updated_at = self._clock()
        return True

    def clear(self) -> None:
        """Drop every document and posting."""
        self._documents.clear()
        self._fingerprints.clear()
        self._postings.clear()
        self._generation += 1
        self._rebuilds += 1
        self._updated_at = self._clock()

    def rebuild(self, documents: Iterable[IndexedDocument]) -> IndexUpdate:
        """Replace the whole index with a new document snapshot."""
        previous = self._generation
        self.clear()
        for document in documents:
            self._insert(document)
        self._generation = previous + 1
        self._updated_at = self._clock()
        return IndexUpdate(
            added=len(self._documents),
            generation=self._generation,
        )

    def sync(self, documents: Iterable[IndexedDocument]) -> IndexUpdate:
        """Apply only inserts, removals, and changed document fingerprints."""
        incoming = list(documents)
        incoming_ids = {document.doc_id for document in incoming}
        update = IndexUpdate()
        for doc_id in list(self._documents):
            if doc_id not in incoming_ids:
                self.remove(doc_id)
                update.removed += 1
        for document in incoming:
            fingerprint = document.fingerprint()
            existing = self._fingerprints.get(document.doc_id)
            if existing == fingerprint:
                update.unchanged += 1
                continue
            if existing is None:
                update.added += 1
            else:
                update.updated += 1
            self.add(document)
        update.generation = self._generation
        return update

    def document(self, doc_id: int) -> IndexedDocument | None:
        return self._documents.get(doc_id)

    def documents(self) -> tuple[IndexedDocument, ...]:
        return tuple(self._documents[doc_id] for doc_id in sorted(self._documents))

    def document_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._documents))

    def postings(self, term: str, *, field: str = "") -> tuple[Posting, ...]:
        """Return postings for a term, optionally restricted to one field."""
        by_document = self._postings.get(term, {})
        result: list[Posting] = []
        for doc_id in sorted(by_document):
            for name, posting in sorted(by_document[doc_id].items()):
                if not field or name == field:
                    result.append(posting)
        return tuple(result)

    def posting(self, term: str, doc_id: int, *, field: str = "") -> Posting | None:
        by_document = self._postings.get(term, {})
        fields = by_document.get(doc_id, {})
        if field:
            return fields.get(field)
        for name in sorted(fields):
            return fields[name]
        return None

    def term_stats(self, term: str) -> TermStats:
        postings = self.postings(term)
        return TermStats(
            term=term,
            document_frequency=len({posting.doc_id for posting in postings}),
            total_frequency=sum(posting.frequency for posting in postings),
            fields=tuple(sorted({posting.field for posting in postings})),
        )

    def vocabulary(self, pattern: str = "") -> tuple[str, ...]:
        """Return indexed terms, optionally filtered by a glob pattern."""
        terms = [term for term in self._postings if fnmatch.fnmatchcase(term, pattern or "*")]
        return tuple(sorted(terms))

    def prefix_terms(self, prefix: str, *, limit: int = 20) -> tuple[str, ...]:
        """Return terms beginning with ``prefix`` in lexical order."""
        value = prefix.casefold().strip()
        if not value:
            return ()
        terms = [term for term in self._postings if term.startswith(value)]
        return tuple(sorted(terms)[: max(0, limit)])

    def fuzzy_terms(
        self,
        term: str,
        *,
        max_distance: int = 1,
        limit: int = 20,
    ) -> tuple[str, ...]:
        """Return vocabulary terms within a bounded edit distance."""
        results: list[tuple[int, str]] = []
        for candidate in self.vocabulary():
            if candidate == term:
                continue
            distance = edit_distance(term, candidate, max_distance=max_distance)
            if distance is not None:
                results.append((distance, candidate))
        results.sort(key=lambda item: (item[0], len(item[1]), item[1]))
        return tuple(candidate for _, candidate in results[: max(0, limit)])

    def matching_documents(
        self,
        terms: Sequence[str],
        *,
        require_all: bool = True,
        field: str = "",
    ) -> frozenset[int]:
        """Return document ids matching some or all of the supplied terms."""
        if not terms:
            return frozenset()
        sets = [self.documents_for_term(term, field=field) for term in terms]
        if require_all:
            result = sets[0]
            for item in sets[1:]:
                result = result & item
            return frozenset(result)
        result_set: set[int] = set()
        for item in sets:
            result_set.update(item)
        return frozenset(result_set)

    def documents_for_term(self, term: str, *, field: str = "") -> frozenset[int]:
        return frozenset(posting.doc_id for posting in self.postings(term, field=field))

    def field_length(self, doc_id: int, field: str) -> int:
        document = self._documents.get(doc_id)
        if document is None:
            return 0
        item = document.field(field)
        return item.length if item is not None else 0

    def terms_for(self, doc_id: int) -> tuple[str, ...]:
        terms = {term for term, by_document in self._postings.items() if doc_id in by_document}
        return tuple(sorted(terms))

    def stats(self) -> IndexStats:
        lengths = [item.length for document in self._documents.values() for item in document.fields]
        average = sum(lengths) / len(lengths) if lengths else 0.0
        return IndexStats(
            documents=len(self._documents),
            terms=len(self._postings),
            postings=sum(len(by_document) for by_document in self._postings.values()),
            generation=self._generation,
            average_field_length=average,
            updated_at=self._updated_at,
            rebuilds=self._rebuilds,
        )

    def serialize(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot for external persistence."""
        return {
            "version": 1,
            "generation": self._generation,
            "rebuilds": self._rebuilds,
            "updated_at": self._updated_at,
            "documents": [document.as_dict() for document in self.documents()],
        }

    @classmethod
    def deserialize(cls, payload: Mapping[str, Any]) -> InvertedIndex:
        """Restore an index from a snapshot produced by :meth:`serialize`."""
        index = cls()
        for raw in payload.get("documents", ()):
            index._insert(IndexedDocument.from_dict(raw))
        index._generation = int(payload.get("generation", 0))
        index._rebuilds = int(payload.get("rebuilds", 0))
        index._updated_at = str(payload.get("updated_at", index._updated_at))
        return index

    def _insert(self, document: IndexedDocument) -> None:
        self._documents[document.doc_id] = document
        self._fingerprints[document.doc_id] = document.fingerprint()
        for field in document.fields:
            self._insert_field(document.doc_id, field.name, field.text, field.tokens, field.boost)

    def _insert_field(
        self,
        doc_id: int,
        field_name: str,
        text: str,
        tokens: Sequence[Token],
        boost: float,
    ) -> None:
        actual_tokens = list(tokens) or list(tokenize(text, field=field_name))
        length = len(actual_tokens)
        for position, token in enumerate(actual_tokens):
            for term in index_terms(token):
                existing = self._postings[term][doc_id].get(field_name)
                positions = (*existing.positions, position) if existing else (position,)
                self._postings[term][doc_id][field_name] = Posting(
                    term=term,
                    doc_id=doc_id,
                    field=field_name,
                    frequency=len(positions),
                    positions=positions,
                    boost=boost,
                    field_length=length,
                )
