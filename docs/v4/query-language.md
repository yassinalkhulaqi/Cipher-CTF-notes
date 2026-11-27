# Query language (v4)

The `query-language` feature adds structured search to RedScribe v4. It is a
data-only slice: a hand-written lexer and recursive-descent parser turn text
into immutable tokens, an evaluator applies them to in-memory dictionaries, and
facets/clusters summarize the results. No user expression is ever executed as
code.

## Package layout

| Path | Responsibility |
| --- | --- |
| `src/redscribe/v4/query/types.py` | Enums, immutable records, validation, error taxonomy |
| `src/redscribe/v4/query/service.py` | Lexer, parser, evaluator, facet and clustering engines, saved-query service |
| `src/redscribe/v4/query/storage.py` | CRUD store, name index, JSON export/import, read-only view |
| `src/redscribe/v4/query/api.py` | v4 envelopes, capability checks, pagination, route registration |
| `frontend/src/features/query-language/` | Typed client, reducer, `QueryBar` component, token styles |
| `frontend/scripts/v4-query-language.test.ts` | Frontend unit suite |

## Grammar

```
expression := or_expr
or_expr     := and_expr (OR and_expr)*
and_expr    := unary (AND unary)*
unary       := NOT? clause
clause      := FIELD ':' OPERATOR? VALUE | free_text
VALUE       := bare_word | quoted | '(' argument (',' argument)* ')'
```

Fields: `title`, `body`, `tag`, `kind`, `status`, `flag`, `target`, `author`.

Operators: `=` (default), `!=`, `contains`, `starts_with`, `>`, `<`, `in`.
Aliases include `==`, `!`, `<>`, `>=`, `<=`, `startswith`, `sw`, `has`, and
`oneof`. `in` takes a parenthesized list; the other operators take one value,
optionally in parentheses. Quoted values use either quote character and support
`\n`, `\r`, `\t`, `\\`, and escaped quotes. Bare words are free-text clauses
combined with `AND`.

Examples:

```
title:contains(sql) AND tag:in(web,ctf)
status:!=closed OR flag:=true
body:"shellcode analysis" AND author:starts_with(ada)
target:>100
# trailing bare words become free-text clauses, not SQL
```

Grouping parentheses for boolean expressions are deliberately rejected with a
positioned syntax error. Parentheses are reserved for operator argument lists,
so a rejected expression can never be silently mis-evaluated.

## Lexer and parser

`QueryLexer` emits `word`, `quoted`, `colon`, `lparen`, `rparen`, `comma`, and
`eof` tokens with source offsets. Operator symbols are tokenized separately so
`status:!=closed` parses as `!=` plus `closed`. `QueryParser` is recursive
descent: `parse()` calls `_parse_or()` → `_parse_and()` → `_parse_unary()` →
`_parse_clause()` → `_parse_value()`.

Errors are `QuerySyntaxError` with a `position` and an explicit message, e.g.
`unknown field: bogus at position 0`, `unterminated quoted value at position 6`,
or `value list must not be empty at position 11`. The API converts them to
`invalid_input` envelopes with a `position=N` detail.

## Evaluation semantics

`SearchEvaluator` reads document dictionaries. It looks up a field by its
canonical name and by aliases (`tags`, `text`, `state`, `flags`, `targets`,
`authors`, and others). Values are coerced to stable text: booleans become
`true`/`false`, collections are flattened, and `None` is skipped. Comparisons
are case-insensitive. `>` and `<` compare numerically when both sides parse as
numbers and lexicographically otherwise. `NEQ` is true for missing fields.

Clauses are combined with AND before OR; `NOT` is stored per token as
`negated`. An empty query matches every document. `trace()` returns per-clause
evidence, and `rank_documents()` orders matches by a simple relevance score
that favours title hits.

## Facets and clusters

`FacetEngine.counts()` builds case-insensitive buckets, using `(unknown)` for
missing values. `facet()` orders buckets by descending count then value,
applies optional selections, and caps the list. `filter_by_facets()` applies
OR within a field and AND across fields.

`ClusteringEngine.group()` groups by the first value of a field, keeps up to
`max_samples` document ids per group, and returns `ResultCluster` records
sorted by size. `summary()` reports cluster count, total results, largest key,
and coverage.

## Saved queries

`SavedQueryService` validates an expression before saving, then persists a
`SavedQuery` through `QueryStore`. It supports `save`, `get`, `list`, `rename`,
`replace_expression`, `duplicate`, `delete`, and `export_json`. Every mutation
publishes a `QUERY_SAVED` domain event whose payload includes the action and the
redacted-safe query fields. Both the clock and id factory are injectable, so
tests are deterministic.

`QueryStore` maintains an id map, a case-insensitive unique-name index, and an
insertion-order list. Renames update the index atomically. `snapshot()`,
`restore()`, `export_json()`, and `import_json()` provide adapter-level
portability; malformed input raises a `QueryError` rather than partially
mutating the store.

## HTTP surface

`register_routes()` adds two routes to a `RouteRegistry`:

- `/api/v4/query` — `GET` actions `search`, `list`, `get`; `POST` actions
  `search`, `save`, `rename`, `delete`, `export`.
- `/api/v4/query/saved` — alias for saved-query operations.

`QueryApi.execute(method, params)` wraps `dispatch()` and translates every
expected exception (`QueryError`, `PaginationError`, `PermissionError`,
`ApiError`, `ValueError`) into a v4 failure envelope. Successful responses use
`ok(data, PageMeta)` with a weak ETag and an opaque next cursor. The
`QUERY_LANGUAGE` feature flag and `QUERY_CAPABILITIES` map gate each action:
search/list/get need `read`, save/rename need `write`, delete needs `delete`,
and export needs `export`.

`GET` parameters include `expression` (or `q`), `page`, `page_size`, `facets`
(comma-separated), `cluster_field`, `rank`, `cursor`, and `facet_selections`
(a JSON object encoded as a query-string value).

## Frontend

`QueryLanguageClient` composes the shared `V4Client`: `buildSearchPath()`
encodes structured parameters, and methods decode `V4Envelope` results or throw
`V4ApiError`. `state.ts` holds a discriminated `QueryAction` union, a pure
`queryReducer`, facet toggling helpers, `appendClause()`, and
`highlightExpression()` for syntax hints.

`QueryBar.tsx` renders the query input with a colored token preview, suggestion
chips, a facet sidebar with checkboxes, result cards with pagination, cluster
cards, and saved-query chips plus a save form. All styling lives in
`query-language.css`, which imports `tokens-v4.css` and uses only `var(--v4-*)`
design tokens, including responsive and reduced-motion rules.

## Testing

Python tests cover enums, validation, dict round-trips, every lexer/parser
error class, every operator and boolean, facets, clusters, saved-query CRUD
with injected clock/id/event bus, store indexes and JSON portability, API
envelopes, capability failures, cursors, and route registration. The frontend
suite covers URL encoding, typed client success/error paths, reducer actions,
facet selection, clause building, and syntax highlighting.
