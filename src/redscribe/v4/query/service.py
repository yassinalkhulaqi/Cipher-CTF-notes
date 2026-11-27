"""Parsing, evaluation, faceting, clustering, and saved-query operations.

The parser is a small recursive-descent reader over a hand-written lexer. It
never uses ``eval``, regular-expression backtracking over user code, or dynamic
imports: expressions only select fields, operators, and literal values.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from redscribe.v4.contracts import EntityKind, new_entity_id
from redscribe.v4.events import EventBus, EventKind, event_from_dataclass, utc_now
from redscribe.v4.query.storage import QueryStore
from redscribe.v4.query.types import (
    MAX_CLUSTER_SAMPLES,
    MAX_FACET_VALUES,
    UNKNOWN_CLUSTER_KEY,
    BooleanOp,
    FacetDefinition,
    FacetValue,
    FieldName,
    Operator,
    ParsedQuery,
    QueryError,
    QueryNotFoundError,
    QuerySyntaxError,
    QueryToken,
    ResultCluster,
    SavedQuery,
    coerce_text,
    coerce_values,
    normalize_expression,
)

Document = dict[str, object]


class LexKind(str, Enum):
    """Lexical categories produced by :class:`QueryLexer`."""

    WORD = "word"
    QUOTED = "quoted"
    COLON = "colon"
    LPAREN = "lparen"
    RPAREN = "rparen"
    COMMA = "comma"
    EOF = "eof"


@dataclass(frozen=True, slots=True)
class LexToken:
    """One lexed unit with its source offset."""

    kind: LexKind
    value: str
    position: int

    @property
    def is_value(self) -> bool:
        return self.kind in (LexKind.WORD, LexKind.QUOTED)


_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "0": "\0"}
_DELIMITERS = set(":(),")


class QueryLexer:
    """Split an expression into typed tokens, decoding quoted literals."""

    def tokenize(self, expression: str) -> tuple[LexToken, ...]:
        tokens: list[LexToken] = []
        index = 0
        length = len(expression)
        while index < length:
            char = expression[index]
            if char.isspace():
                index += 1
                continue
            if char == ":":
                tokens.append(LexToken(LexKind.COLON, char, index))
                index += 1
                continue
            if char == "(":
                tokens.append(LexToken(LexKind.LPAREN, char, index))
                index += 1
                continue
            if char == ")":
                tokens.append(LexToken(LexKind.RPAREN, char, index))
                index += 1
                continue
            if char == ",":
                tokens.append(LexToken(LexKind.COMMA, char, index))
                index += 1
                continue
            if char in ('"', "'"):
                value, index = self._read_quoted(expression, index, char)
                tokens.append(LexToken(LexKind.QUOTED, value, index - 1))
                continue
            if char in "=!<>":
                start = index
                while index < length and expression[index] in "=!<>":
                    index += 1
                tokens.append(LexToken(LexKind.WORD, expression[start:index], start))
                continue
            start = index
            while index < length and not expression[index].isspace():
                if expression[index] in _DELIMITERS:
                    break
                index += 1
            if index == start:
                index += 1
                continue
            tokens.append(LexToken(LexKind.WORD, expression[start:index], start))
        tokens.append(LexToken(LexKind.EOF, "", length))
        return tuple(tokens)

    def _read_quoted(self, expression: str, start: int, quote: str) -> tuple[str, int]:
        index = start + 1
        chars: list[str] = []
        length = len(expression)
        while index < length:
            char = expression[index]
            if char == quote:
                return "".join(chars), index + 1
            if char == "\\":
                if index + 1 >= length:
                    raise QuerySyntaxError("unterminated escape sequence", index)
                following = expression[index + 1]
                if following in (quote, "\\"):
                    chars.append(following)
                elif following in _ESCAPES:
                    chars.append(_ESCAPES[following])
                else:
                    raise QuerySyntaxError(f"invalid escape sequence: \\{following}", index)
                index += 2
                continue
            chars.append(char)
            index += 1
        raise QuerySyntaxError("unterminated quoted value", start)


class QueryParser:
    """Recursive-descent parser for structured query expressions.

    Grammar (highest precedence first)::

        clause   := NOT? (FIELD ':' OPERATOR? VALUE | free_text)
        and_expr := clause (AND clause)*
        or_expr  := and_expr (OR and_expr)*

    Parentheses are reserved for operator argument lists such as
    ``tag:in(web,ctf)``; boolean grouping is intentionally rejected with a
    positioned error rather than silently mis-evaluated.
    """

    def __init__(self, lexer: QueryLexer | None = None) -> None:
        self.lexer = lexer or QueryLexer()
        self._tokens: tuple[LexToken, ...] = ()
        self._index = 0

    def parse(self, expression: str) -> ParsedQuery:
        """Parse ``expression`` into an immutable :class:`ParsedQuery`."""
        normalized = normalize_expression(expression)
        self._tokens = self.lexer.tokenize(expression)
        self._index = 0
        if self._peek().kind is LexKind.EOF:
            return ParsedQuery(tokens=(), raw=expression, normalized=normalized)
        tokens = self._parse_or()
        leftover = self._peek()
        if leftover.kind is not LexKind.EOF:
            raise QuerySyntaxError(
                f"unexpected token: {leftover.value or leftover.kind.value}",
                leftover.position,
            )
        return ParsedQuery(tuple(tokens), expression, normalized)

    def _peek(self, offset: int = 0) -> LexToken:
        index = min(self._index + offset, len(self._tokens) - 1)
        return self._tokens[index]

    def _advance(self) -> LexToken:
        token = self._peek()
        if token.kind is not LexKind.EOF:
            self._index += 1
        return token

    def _peek_boolean(self) -> BooleanOp | None:
        token = self._peek()
        if token.kind is not LexKind.WORD:
            return None
        return BooleanOp.parse(token.value)

    def _parse_or(self) -> list[QueryToken]:
        tokens = self._parse_and()
        while self._peek_boolean() is BooleanOp.OR:
            self._advance()
            right = self._parse_and()
            self._connect(right, BooleanOp.OR)
            tokens.extend(right)
        return tokens

    def _is_implicit_text(self) -> bool:
        token = self._peek()
        if token.kind is LexKind.QUOTED:
            return True
        return (
            token.kind is LexKind.WORD
            and BooleanOp.parse(token.value) is None
            and self._peek(1).kind is not LexKind.COLON
        )

    def _parse_and(self) -> list[QueryToken]:
        tokens = self._parse_unary()
        while True:
            connector = self._peek_boolean()
            if connector is BooleanOp.AND or (connector is None and self._is_implicit_text()):
                if connector is BooleanOp.AND:
                    self._advance()
                    right = self._parse_unary()
                else:
                    right = self._parse_clause()
                self._connect(right, BooleanOp.AND)
                tokens.extend(right)
                continue
            break
        return tokens

    @staticmethod
    def _connect(tokens: list[QueryToken], connector: BooleanOp) -> None:
        if not tokens:
            return
        first = tokens[0]
        tokens[0] = replace(first, boolean=connector)

    def _parse_unary(self) -> list[QueryToken]:
        negated = False
        while self._peek_boolean() is BooleanOp.NOT:
            self._advance()
            negated = not negated
        token = self._peek()
        if token.kind is LexKind.LPAREN:
            raise QuerySyntaxError(
                "parenthesised boolean groups are not supported; "
                "parentheses may only follow an operator",
                token.position,
            )
        if token.kind is LexKind.EOF or token.kind in (
            LexKind.RPAREN,
            LexKind.COMMA,
            LexKind.COLON,
        ):
            raise QuerySyntaxError("expected a clause", token.position)
        if token.kind is LexKind.WORD and BooleanOp.parse(token.value) is not None:
            raise QuerySyntaxError(f"unexpected boolean operator: {token.value}", token.position)
        parsed = self._parse_clause()
        if negated:
            first = parsed[0]
            return [replace(first, negated=not first.negated, boolean=None)]
        return parsed

    def _parse_clause(self) -> list[QueryToken]:
        token = self._peek()
        if token.kind is LexKind.QUOTED or (
            token.kind is LexKind.WORD and self._peek(1).kind is not LexKind.COLON
        ):
            self._advance()
            return [
                QueryToken(
                    field=FieldName.BODY,
                    operator=Operator.CONTAINS,
                    value=token.value,
                    free_text=True,
                    position=token.position,
                )
            ]
        if token.kind is not LexKind.WORD:
            raise QuerySyntaxError(
                f"expected a field name, found {token.kind.value}", token.position
            )
        self._advance()
        field = FieldName.require(token.value, token.position)
        colon = self._peek()
        if colon.kind is not LexKind.COLON:
            raise QuerySyntaxError("expected ':' after field name", colon.position)
        self._advance()
        operator = Operator.EQ
        candidate = self._peek()
        if candidate.kind is LexKind.WORD:
            parsed = Operator.parse(candidate.value)
            if parsed is not None:
                operator = parsed
                self._advance()
            elif self._peek(1).kind is LexKind.LPAREN:
                raise QuerySyntaxError(f"unknown operator: {candidate.value}", candidate.position)
        return [self._parse_value(field, operator)]

    def _parse_value(self, field: FieldName, operator: Operator) -> QueryToken:
        token = self._peek()
        if token.kind is LexKind.LPAREN:
            self._advance()
            arguments = self._parse_arguments()
            if operator.is_set:
                if not arguments:
                    raise QuerySyntaxError("value list must not be empty", token.position)
                return QueryToken(
                    field=field, operator=operator, values=arguments, position=token.position
                )
            if len(arguments) != 1:
                raise QuerySyntaxError(
                    f"operator {operator.value} accepts exactly one value", token.position
                )
            return QueryToken(
                field=field, operator=operator, value=arguments[0], position=token.position
            )
        if not token.is_value:
            raise QuerySyntaxError("expected a value", token.position)
        if token.kind is LexKind.WORD and BooleanOp.parse(token.value) is not None:
            raise QuerySyntaxError(f"expected a value, found {token.value}", token.position)
        self._advance()
        if operator.is_set:
            return QueryToken(
                field=field, operator=operator, values=(token.value,), position=token.position
            )
        return QueryToken(
            field=field, operator=operator, value=token.value, position=token.position
        )

    def _parse_arguments(self) -> tuple[str, ...]:
        values: list[str] = []
        expect_value = True
        while True:
            token = self._peek()
            if token.kind is LexKind.RPAREN:
                if expect_value and values:
                    raise QuerySyntaxError("trailing comma in value list", token.position)
                self._advance()
                break
            if token.kind is LexKind.EOF:
                raise QuerySyntaxError("unterminated value list", token.position)
            if token.kind is LexKind.COMMA:
                if expect_value:
                    raise QuerySyntaxError("missing value in list", token.position)
                self._advance()
                expect_value = True
                continue
            if not token.is_value or not expect_value:
                raise QuerySyntaxError(
                    f"unexpected token in value list: {token.value or token.kind.value}",
                    token.position,
                )
            values.append(token.value)
            expect_value = False
            self._advance()
        if len(values) > MAX_FACET_VALUES:
            raise QuerySyntaxError(f"too many values (max {MAX_FACET_VALUES})", position=0)
        return tuple(values)


@dataclass(frozen=True, slots=True)
class TokenResult:
    """Debug view of one clause evaluation."""

    token: QueryToken
    matched: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "expression": self.token.expression,
            "field": self.token.field.value,
            "matched": self.matched,
        }


@dataclass(frozen=True, slots=True)
class EvaluationTrace:
    """Result plus per-clause evidence for an evaluation."""

    matched: bool
    score: int
    clauses: tuple[TokenResult, ...]

    @property
    def matched_clauses(self) -> int:
        return sum(1 for clause in self.clauses if clause.matched)

    def to_dict(self) -> dict[str, object]:
        return {
            "matched": self.matched,
            "score": self.score,
            "clauses": [clause.to_dict() for clause in self.clauses],
        }


_FIELD_ALIASES: dict[FieldName, tuple[str, ...]] = {
    FieldName.TITLE: ("name", "subject"),
    FieldName.BODY: ("text", "content", "summary"),
    FieldName.TAG: ("tags",),
    FieldName.KIND: ("entity_kind",),
    FieldName.STATUS: ("state",),
    FieldName.FLAG: ("flags",),
    FieldName.TARGET: ("targets", "hosts"),
    FieldName.AUTHOR: ("authors", "owner"),
}


def _numeric(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


class SearchEvaluator:
    """Evaluate parsed queries against in-memory document dictionaries."""

    def field_values(self, document: Mapping[str, object], field: FieldName) -> tuple[str, ...]:
        """Collect and de-duplicate all values bound to ``field``."""
        found: list[str] = []
        keys = (field.value, *_FIELD_ALIASES.get(field, ()))
        for key in keys:
            if key not in document:
                continue
            for value in coerce_values(document[key]):
                if not any(value.casefold() == seen.casefold() for seen in found):
                    found.append(value)
        return tuple(found)

    def all_values(self, document: Mapping[str, object]) -> tuple[str, ...]:
        found: list[str] = []
        for field in FieldName:
            for value in self.field_values(document, field):
                if value not in found:
                    found.append(value)
        return tuple(found)

    def compare_value(self, value: str, token: QueryToken) -> bool:
        """Apply ``token`` to a single candidate value."""
        left = value.casefold()
        if token.operator.is_set:
            return any(left == term.casefold() for term in token.terms)
        right = token.value.casefold()
        if token.operator is Operator.EQ:
            return left == right
        if token.operator is Operator.NEQ:
            return left != right
        if token.operator is Operator.CONTAINS:
            return bool(right) and right in left
        if token.operator is Operator.STARTS_WITH:
            return bool(right) and left.startswith(right)
        if token.operator is Operator.GT:
            return self._relational(value, token.value, greater=True)
        if token.operator is Operator.LT:
            return self._relational(value, token.value, greater=False)
        return False

    @staticmethod
    def _relational(left: str, right: str, *, greater: bool) -> bool:
        left_number = _numeric(left)
        right_number = _numeric(right)
        if left_number is not None and right_number is not None:
            return left_number > right_number if greater else left_number < right_number
        a, b = left.casefold(), right.casefold()
        return a > b if greater else a < b

    def matches_token(self, document: Mapping[str, object], token: QueryToken) -> bool:
        """Evaluate one clause, including negation and free-text terms."""
        if token.free_text:
            needle = token.value.casefold()
            matched = any(needle in value.casefold() for value in self.all_values(document))
        else:
            values = self.field_values(document, token.field)
            if not values and token.operator is Operator.NEQ:
                matched = all(bool(term.strip()) for term in token.terms)
            elif not values:
                matched = False
            else:
                matched = any(self.compare_value(value, token) for value in values)
        return not matched if token.negated else matched

    def trace(self, document: Mapping[str, object], query: ParsedQuery) -> EvaluationTrace:
        """Evaluate with per-clause evidence and a relevance score."""
        clause_results = tuple(
            TokenResult(token, self.matches_token(document, token)) for token in query.tokens
        )
        matched = self.combine(clause_results)
        score = 0
        for result in clause_results:
            if not result.matched:
                continue
            score += 2 if result.token.field is FieldName.TITLE else 1
        if matched and clause_results:
            score += 1
        return EvaluationTrace(matched, score, clause_results)

    @staticmethod
    def combine(results: Sequence[TokenResult]) -> bool:
        """Combine clause results with AND before OR (NOT is already applied)."""
        if not results:
            return True
        groups: list[bool] = []
        current = results[0].matched
        for result in results[1:]:
            if result.token.boolean is BooleanOp.OR:
                groups.append(current)
                current = result.matched
            else:
                current = current and result.matched
        groups.append(current)
        return any(groups)

    def matches(self, document: Mapping[str, object], query: ParsedQuery) -> bool:
        return self.trace(document, query).matched

    def filter_documents(self, documents: Sequence[Document], query: ParsedQuery) -> list[Document]:
        """Return documents matching ``query`` in their original order."""
        return [document for document in documents if self.matches(document, query)]

    def rank_documents(
        self, documents: Sequence[Document], query: ParsedQuery, limit: int | None = None
    ) -> list[Document]:
        """Return matching documents ordered by relevance, then input order."""
        scored: list[tuple[int, int, Document]] = []
        for index, document in enumerate(documents):
            trace = self.trace(document, query)
            if trace.matched:
                scored.append((-trace.score, index, document))
        scored.sort(key=lambda item: (item[0], item[1]))
        ordered = [item[2] for item in scored]
        return ordered[:limit] if limit is not None else ordered

    @staticmethod
    def validate(query: ParsedQuery) -> list[str]:
        """Return advisory warnings for a parsed query."""
        warnings: list[str] = []
        if query.is_empty:
            warnings.append("empty query matches every document")
        for token in query.tokens:
            if token.operator.is_relational and token.free_text:
                warnings.append("relational free-text clauses use lexical ordering")
            if token.operator.is_set and len(token.terms) == 1:
                warnings.append(f"single-value in clause on {token.field.value}")
        return warnings


class FacetEngine:
    """Build facet counts and apply facet selections to result sets."""

    def __init__(self, max_values: int = MAX_FACET_VALUES) -> None:
        if max_values < 1:
            raise QueryError("max_values must be >= 1")
        self.max_values = max_values

    def counts(self, results: Sequence[Document], field: FieldName) -> dict[str, int]:
        evaluator = SearchEvaluator()
        buckets: dict[str, int] = {}
        for document in results:
            values = evaluator.field_values(document, field)
            if not values:
                values = (UNKNOWN_CLUSTER_KEY,)
            for value in values:
                key = value.casefold()
                existing = next((name for name in buckets if name.casefold() == key), None)
                name = value if existing is None else existing
                buckets[name] = buckets.get(name, 0) + 1
        return buckets

    def facet(
        self,
        results: Sequence[Document],
        field: FieldName,
        selected: Sequence[str] = (),
        limit: int | None = None,
    ) -> FacetDefinition:
        """Build one facet definition, ordered by count then value."""
        raw = self.counts(results, field)
        ordered = sorted(raw.items(), key=lambda item: (-item[1], item[0].casefold()))
        cap = min(self.max_values, limit or self.max_values)
        values = tuple(FacetValue(value, count) for value, count in ordered[:cap])
        return FacetDefinition(field=field, values=values).with_selection(selected)

    def build(
        self,
        results: Sequence[Document],
        fields: Sequence[FieldName],
        selections: Mapping[str, Sequence[str]] | None = None,
        limit: int = 10,
    ) -> list[FacetDefinition]:
        """Build several facets and apply any user selections."""
        chosen = selections or {}
        return [self.facet(results, field, chosen.get(field.value, ()), limit) for field in fields]

    def filter_by_facets(
        self,
        results: Sequence[Document],
        selections: Mapping[FieldName, Sequence[str]],
    ) -> list[Document]:
        """Filter results: AND across fields, OR within a field's values."""
        evaluator = SearchEvaluator()
        kept: list[Document] = []
        for document in results:
            allowed = True
            for field, wanted in selections.items():
                if not wanted:
                    continue
                values = {value.casefold() for value in evaluator.field_values(document, field)}
                if not values.intersection(value.casefold() for value in wanted):
                    allowed = False
                    break
            if allowed:
                kept.append(document)
        return kept


class ClusteringEngine:
    """Group result documents by a shared field value."""

    def __init__(
        self,
        max_samples: int = MAX_CLUSTER_SAMPLES,
        max_clusters: int = 20,
    ) -> None:
        if max_samples < 0 or max_clusters < 1:
            raise QueryError("invalid clustering limits")
        self.max_samples = max_samples
        self.max_clusters = max_clusters

    @staticmethod
    def document_id(document: Mapping[str, object], index: int) -> str:
        for key in ("id", "ref", "key"):
            value = coerce_text(document.get(key, ""))
            if value:
                return value
        return f"doc-{index}"

    def group(self, results: Sequence[Document], field: FieldName) -> list[ResultCluster]:
        """Build clusters keyed by ``field``, strongest first."""
        evaluator = SearchEvaluator()
        buckets: dict[str, list[str]] = {}
        counts: dict[str, int] = {}
        for index, document in enumerate(results):
            values = evaluator.field_values(document, field) or (UNKNOWN_CLUSTER_KEY,)
            key = values[0]
            normalized = key.casefold()
            canonical = next((name for name in counts if name.casefold() == normalized), key)
            counts[canonical] = counts.get(canonical, 0) + 1
            samples = buckets.setdefault(canonical, [])
            sample = self.document_id(document, index)
            if len(samples) < self.max_samples and sample not in samples:
                samples.append(sample)
        clusters = [
            ResultCluster(key, count, tuple(buckets.get(key, [])[: self.max_samples]))
            for key, count in counts.items()
        ]
        clusters.sort(key=lambda item: (-item.count, item.key.casefold()))
        return clusters[: self.max_clusters]

    def group_many(
        self, results: Sequence[Document], fields: Sequence[FieldName]
    ) -> dict[str, list[ResultCluster]]:
        """Cluster the same results by several fields."""
        return {field.value: self.group(results, field) for field in fields}

    @staticmethod
    def summary(clusters: Sequence[ResultCluster]) -> dict[str, object]:
        total = sum(cluster.count for cluster in clusters)
        return {
            "clusters": len(clusters),
            "results": total,
            "largest": clusters[0].key if clusters else "",
            "coverage": round(sum(cluster.ratio(total) for cluster in clusters), 4),
        }


class SavedQueryService:
    """Application service for named queries, with event emission."""

    def __init__(
        self,
        store: QueryStore | None = None,
        bus: EventBus | None = None,
        parser: QueryParser | None = None,
        clock: Callable[[], str] = utc_now,
        id_factory: Callable[[], str] = new_entity_id,
    ) -> None:
        self.store = store or QueryStore()
        self.bus = bus
        self.parser = parser or QueryParser()
        self.clock = clock
        self.id_factory = id_factory

    def validate(self, expression: str) -> ParsedQuery:
        parsed = self.parser.parse(expression)
        if parsed.is_empty:
            raise QueryError("saved queries must contain at least one clause")
        return parsed

    def save(self, name: str, expression: str) -> SavedQuery:
        self.validate(expression)
        query = SavedQuery(
            id=self.id_factory(),
            name=name,
            expression=expression,
            created_at=self.clock(),
        )
        self.store.put(query)
        self._emit(query, "saved")
        return query

    def get(self, query_id: str) -> SavedQuery:
        query = self.store.get(query_id)
        if query is None:
            raise QueryNotFoundError(query_id)
        return query

    def list(self) -> tuple[SavedQuery, ...]:
        return self.store.list()

    def rename(self, query_id: str, name: str) -> SavedQuery:
        updated = self.get(query_id).rename(name)
        self.store.put(updated)
        self._emit(updated, "renamed")
        return updated

    def replace_expression(self, query_id: str, expression: str) -> SavedQuery:
        self.validate(expression)
        updated = self.get(query_id).with_expression(expression)
        self.store.put(updated)
        self._emit(updated, "updated")
        return updated

    def delete(self, query_id: str) -> SavedQuery:
        query = self.get(query_id)
        self.store.delete(query_id)
        self._emit(query, "deleted")
        return query

    def duplicate(self, query_id: str, name: str) -> SavedQuery:
        original = self.get(query_id)
        return self.save(name, original.expression)

    def export_json(self) -> str:
        return self.store.export_json()

    def _emit(self, query: SavedQuery, action: str) -> None:
        if self.bus is None:
            return
        event = event_from_dataclass(EventKind.QUERY_SAVED, query.id, EntityKind.QUERY, query)
        event.payload["action"] = action
        self.bus.publish(event)


def default_engines() -> tuple[QueryParser, SearchEvaluator, FacetEngine, ClusteringEngine]:
    """Construct the standard parser/evaluator/engine set."""
    return QueryParser(), SearchEvaluator(), FacetEngine(), ClusteringEngine()
