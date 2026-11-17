# V2 Search and Commands

The V2 search layer adds an incremental inverted index, ranked full-text queries,
deterministic snippets, saved searches, and a slash-command grammar. It is exposed
through the `search.*`, `saved.*`, and `commands.*` API v2 namespaces and consumed by
the `frontend/src/features/search` module.

## Design goals

- Search every vault node without network services or external dependencies.
- Keep the index incremental: edits touch only the changed documents.
- Make ranking explainable by returning score components and matched terms.
- Produce snippets as structured chunks so the UI can highlight them without HTML injection.
- Reuse the same command parser for API validation, frontend completion, and tests.
- Keep all shared V2 kernel files untouched; the feature registers itself as a namespace.

## Components

| Component | Location | Responsibility |
| --- | --- | --- |
| Models | `src/redscribe/v2/search/models.py` | Typed payloads, boosts, limits, serialization |
| Tokenizer | `src/redscribe/v2/search/tokenizer.py` | Unicode folding, stemming, n-grams |
| Synonyms | `src/redscribe/v2/search/synonyms.py` | Transitive synonym expansion |
| Filters | `src/redscribe/v2/search/filters.py` | Field filters and facet counting |
| Index | `src/redscribe/v2/search/index.py` | In-memory inverted index with generation tracking |
| Query | `src/redscribe/v2/search/query.py` | Query grammar, synonym expansion, fingerprints |
| Snippets | `src/redscribe/v2/search/snippets.py` | Highlights and chunked text rendering |
| Ranking | `src/redscribe/v2/search/ranking.py` | BM25-style scoring, grouping, facets |
| Saved queries | `src/redscribe/v2/search/saved.py` | Persistence in vault settings |
| Service | `src/redscribe/v2/search/service.py` | Vault-aware orchestration |
| Commands | `src/redscribe/v2/search/commands/` | Grammar, catalog, parsing, suggestions |
| API namespace | `src/redscribe/ui/web/v2/namespaces/search.py` | HTTP routes |
| Frontend module | `frontend/src/features/search/` | Pure helpers, adapters, service client |

## Indexing

Each node is converted into a `SearchDocument` with boosted fields:

| Field | Default boost |
| --- | --- |
| `title` | 5.0 |
| `flag` | 4.0 |
| `tags` | 3.0 |
| `target` | 2.0 |
| `content` | 1.0 |
| `path` | 0.5 |

Text is Unicode-normalized, lowercased, and split into word tokens. Tokens are
stemmed conservatively and also indexed as prefix n-grams. Synonym expansion adds
low-weight optional terms that can make a result relevant without outranking exact
matches.

`InvertedIndex.sync(nodes)` compares document fingerprints and returns an
`IndexUpdate` with `added`, `updated`, `removed`, `unchanged`, `generation`, and
`changed` fields. A full rebuild increments `rebuilds`; an incremental sync only
rewrites postings for changed documents.

## Query grammar

Free text is combined with optional field filters and term modifiers:

| Syntax | Meaning |
| --- | --- |
| `nmap ports` | Require both terms |
| `"sql injection"` | Phrase match |
| `title:report` | Restrict a term to one field |
| `tag:web` | Filter by tag |
| `-tag:archived` | Exclude a tag |
| `status!=closed` | Exclude a field value |
| `port*` | Prefix match |
| `scan~` | Fuzzy match |
| `title:flag^3` | Boost a term |
| `+optional` | Optional term |
| `-noise` | Negated term |
| `OR`, `AND`, `NOT` | Boolean hints |

Supported filter fields include `tag`, `tags`, `status`, `kind`, `target`, `path`,
`title`, `flag`, `difficulty`, `pinned`, `id`, `node_id`, `created`, `updated`, and
`group`. Filter operators are `:`, `=`, `!=`, `~`, `>`, `>=`, `<`, and `<=`.

Every query is reduced to a stable 8-character fingerprint. Fingerprints are used
to cache repeated searches and to identify saved-query duplicates.

## Ranking

Ranking is BM25-style with field boosts. Each hit includes:

- `score`: the final weighted score.
- `score_details.total`: the same total for convenience.
- `score_details.components`: per-signal contributions such as `title`, `content`,
  `tag`, `proximity`, `coverage`, and `freshness`.
- `score_details.matched_terms`: normalized terms that matched.
- `score_details.coverage`: fraction of required terms matched.

Sort keys are `relevance` (default), `updated`, `title`, and `id`. Optional grouping
uses `group_by=<field>` and returns groups ordered by size.

## Snippets

Snippets are generated around the best matching window. The response contains both
`highlights` (character offsets) and `chunks` (alternating plain and matching text).
Clients must render chunks as text nodes with `<mark>` elements for matching chunks;
they must never inject snippet text as HTML.

## Saved queries

Saved queries are stored in the vault settings key `v2.saved_queries.v1`. Each record
has `id`, `name`, `query`, `description`, `tags`, `created_at`, `updated_at`,
`use_count`, and `pinned`. Export and import use a portable JSON list payload;
importing an existing id generates a new id.

The `saved.use` route increments `use_count` and returns the updated record.

## Commands

Commands are parsed from a single `/name arguments --option=value` string. The catalog
contains `search`, `find`, `goto`, `open`, `tag`, `untag`, `bookmark`, `pin`, `saved`,
`filter`, `sort`, and `reindex`, plus aliases such as `/s`, `/f`, `/g`, and `/save`.

A parsed command returns:

- `node.name`: canonical command name.
- `node.arguments`: ordered values with source positions and quoted flags.
- `node.options`: option names mapped to values.
- `issues`: typed parse problems with codes and positions.
- `plan`: the execution preview with action, query, filters, and target.

Suggestions are context-aware: at the first token the parser suggests command names,
then options, saved-query names for `/saved`, and examples otherwise. Mutating
commands are marked so the UI can ask for confirmation.

## API routes

All routes use POST with a JSON body unless noted. Route names are dot-separated and
map to `/api/v2/<namespace>/<action>`.

| Route | Body | Result |
| --- | --- | --- |
| `search.query` | `query`, `limit`, `cursor`, `sort`, `group_by`, `facet_field`, `width` | `{ result, page }` |
| `search.suggest` | `text` | Query, command, and saved-query suggestions |
| `search.facets` | `field`, `text` | Facet counts |
| `search.snippet` | `node_id`, `text`, `width` | Structured snippet |
| `search.terms` | — | Index vocabulary |
| `search.status` | — | Index and catalog statistics |
| `search.reindex` | — | Full rebuild update |
| `search.describe` | — | Fields, boosts, limits, grammar description |
| `saved.list` | — | Saved-query records |
| `saved.get` | `id` | One saved query |
| `saved.create` | `name`, `query`, `description`, `tags`, `pinned` | Created record |
| `saved.update` | `id` plus editable fields | Updated record |
| `saved.delete` | `id` | `{ deleted: true }` |
| `saved.use` | `id` | Record with incremented use count |
| `commands.parse` | `text` | Parsed command |
| `commands.suggest` | `text`, `limit` | Suggestion list |
| `commands.complete` | `text` | Completion context and suggestions |
| `commands.list` | — | Command metadata |
| `commands.help` | `name` | Help payload |
| `commands.run` | `text` | Execution preview or result |

`search.query` response example:

```json
{
  "ok": true,
  "data": {
    "result": {
      "query": {
        "text": "nmap tag:web",
        "terms": [{ "value": "nmap", "field": "", "boost": 1, "prefix": false, "fuzzy": false, "phrase": false, "negated": false, "optional": false, "synonym": false }],
        "filters": [{ "field": "tag", "operator": ":", "value": "web", "negated": false }],
        "sort": "relevance",
        "group_by": "",
        "fingerprint": "7c1a4f20"
      },
      "items": [
        {
          "node_id": 12,
          "title": "Nmap notes",
          "path": "recon/nmap.md",
          "snippet": {
            "text": "nmap found open ports",
            "highlights": [{ "start": 0, "end": 4, "term": "nmap", "kind": "exact" }],
            "chunks": [{ "text": "nmap", "match": true }, { "text": " found open ports", "match": false }],
            "fragments": 1,
            "matched": true
          },
          "score": 18.7,
          "score_details": {
            "total": 18.7,
            "components": { "title": 8.0, "content": 3.5, "tag": 2.0 },
            "matched_terms": ["nmap"],
            "coverage": 1.0
          },
          "metadata": { "tags": ["web"] },
          "group": "web"
        }
      ],
      "total": 1,
      "facets": [{ "value": "web", "count": 1 }],
      "suggestions": [],
      "generation": 3,
      "elapsed_ms": 0.8
    },
    "page": {
      "cursor": null,
      "next": null,
      "total": 1,
      "limit": 50,
      "has_more": false
    }
  },
  "meta": { "request_id": "req-..." }
}
```

## Frontend module

`frontend/src/features/search` re-exports the complete feature API from `index.ts`:

- `query.ts` mirrors query parsing and synonym expansion for instant feedback.
- `filters.ts` builds chips, toggles facets, and applies client-side filters.
- `highlight.tsx` provides `HighlightedText` plus pure segmentation helpers.
- `ranking.ts` groups, sorts, deduplicates, and explains hits.
- `saved.ts` validates drafts and organizes saved queries.
- `commands.ts` parses commands and produces contextual completions.
- `service.ts` wraps `V2Client` with typed methods and error normalization.
- `adapter.ts` converts search results into `CommandDescriptor` objects.
- `format.ts` formats counts, scores, dates, and summaries.

The frontend never edits the shared command registry. It returns descriptors that
the host application may register.

Example:

```ts
import { V2Client } from "../lib/apiClient";
import { SearchService, HighlightedText, parseSearchQuery } from "../features/search";

const client = new V2Client();
const search = new SearchService(client);
const response = await search.search({ query: "nmap tag:web", limit: 20 });
const parsed = parseSearchQuery("nmap tag:web");
```

## Testing

Backend tests live in `tests/v2_search/`. Frontend tests live in
`frontend/scripts/search.test.ts` and are registered in `frontend/scripts/test.mjs`.

Run:

```bash
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
python3 -m ruff check .
python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
cd frontend && npm test && npm run format:check && npm run typecheck && npm run build
python3 scripts/loc_gate.py --base origin/dev/v2-00-platform-kernel --min-added 4000 --min-tests 500
```
