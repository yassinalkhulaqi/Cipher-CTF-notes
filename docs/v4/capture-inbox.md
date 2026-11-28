# Capture inbox (v4)

The capture inbox is the universal entry point for material found during an
engagement. Notes, URLs, pasted code, CTF flags, and clipboard drops all enter
one pipeline, are normalized and classified, then move through a small triage
funnel into the rest of the vault. This document describes the v4 slice
`redscribe.v4.inbox` and its frontend counterpart `capture-inbox`.

## Goals

- One immutable record type for every capture, regardless of origin.
- Deterministic classification with conservative heuristics; explicit source
  assertion when the caller knows better than the text.
- Strict templates that never evaluate user input.
- A closed triage state machine with no implicit transitions.
- Stable deduplication by normalized content hash.
- Standard v4 envelopes, capabilities, errors, and events.
- A responsive inbox UI with keyboard-first triage.

## File layout

```
src/redscribe/v4/inbox/
  __init__.py    package exports and register(api)
  types.py       enums, validation, CaptureDraft, CaptureItem
  service.py     parser, templates, triage machine, orchestration
  storage.py     indexed in-memory store with JSON import/export
  api.py         v4 route handlers and error translation
tests/v4_inbox/
  test_types.py  validation and serialization tests
  test_service.py parser, template, machine, store, and service tests
  test_api.py    envelopes, pagination, capabilities, and error tests
frontend/src/features/capture-inbox/
  client.ts      typed API client
  state.ts       reducer and pure selectors
  InboxPanel.tsx React inbox panel
  capture-inbox.css design-token styles
frontend/scripts/v4-capture-inbox.test.ts node:test suite
frontend/scripts/test-suites/v4-01.json
docs/v4/capture-inbox.md
```

## Data model

`CaptureItem` is a frozen, slotted dataclass with eight fields:

| Field | Meaning |
| --- | --- |
| `id` | RFC-4122-style lowercase identifier from `new_entity_id()` |
| `raw` | Original text after whitespace folding |
| `source` | One of `manual`, `link`, `snippet`, `flag`, `clipboard` |
| `state` | One of `untriaged`, `accepted`, `rejected`, `archived` |
| `tags` | Sorted tuple of canonical lowercase tags |
| `confidence` | Classifier confidence in `[0.0, 1.0]` |
| `created_at` | Timezone-aware ISO-8601 timestamp |
| `content_hash` | SHA-256 of normalized, casefolded raw text |

Validation is strict: identifiers must match the universal entity-id pattern,
timestamps must carry a timezone, tags must match the tag slug grammar, and the
stored hash must equal the hash recomputed from the raw text. `to_dict` and
`from_dict` round-trip without loss. `CaptureItem.create` derives the id, hash,
and timestamp; callers may inject all three for deterministic tests.

`CaptureDraft` carries the parser's interpretation — raw text, chosen source,
tags, confidence, extracted URLs, and flag tokens — before it is materialized
into a persisted item.

## Parsing

`CaptureParser` performs data-only text analysis:

1. `extract_urls` finds HTTP(S) URLs and trims trailing punctuation. Duplicate
   URLs are removed while encounter order is preserved.
2. `detect_flags` finds `flag{...}` tokens case-insensitively and requires the
   closing brace.
3. `looks_like_snippet` recognizes code fences, language markers, assignment
   and semicolon patterns, and structured multi-line text.
4. `classify` checks flags first, then URLs, then snippets; otherwise it
   returns `manual`. `clipboard` is never inferred — a caller must assert it.
5. `tag_hints` adds conservative hints such as `flag`, `link`, `web`,
   `snippet`, `todo`, and `cve`, merged with caller tags and canonicalized.
6. `confidence_for` starts from a per-source base score and applies small,
   bounded bonuses for concrete signals.

## Templates

`TemplateEngine` renders named templates by substituting `{{placeholder}}`
tokens from a caller-supplied mapping. Placeholder names must be identifiers;
anything else is left as literal text. A missing key raises
`MissingTemplateKeyError` listing every missing key — templates never silently
emit `None` or evaluate code. Built-ins are `note`, `flag`, `link`, `snippet`,
and `handoff`; new templates can be registered at runtime after validation.
`render_capture` derives the standard value set for a stored item.

## Triage state machine

```
untriaged ──accept──▶ accepted ──archive──▶ archived ──reset──▶ untriaged
     ├──── reject────▶ rejected ──archive──▶ archived
     └──── archive────────────────────────▶ archived
```

`TriageMachine` is the only writer of `CaptureItem.state`. `transition` and
`apply` reject every pair outside the graph with `TransitionError`, whose
`legal` tuple names the valid targets from the current state. Actions map to
target states (`accept`, `reject`, `archive`, `reset`) so UI and API callers
speak the same vocabulary.

## Storage

`InboxStore` maintains three structures: an id map, a content-hash map, and an
insertion-order list. `insert` and `update` reject duplicate ids and hashes;
`delete` removes all three entries. `list` filters by state, source, tag, and
case-insensitive text query, then sorts newest first with id as a tiebreaker.
`rebuild_index` recomputes both indexes from the item map and refuses stale
hashes. `index_report` and `is_consistent` support diagnostics. JSON export
emits a versioned payload; import revalidates every item, skips exact duplicates,
ignores duplicate content hashes, and rejects conflicting ids or bad versions.

The interface is deliberately SQL-adapter-shaped so a persistent backend can
replace the dictionaries without touching the service or routes.

## Service and events

`InboxService.capture` parses input, checks the hash index, and either returns
the existing item (`created=False`) or stores a new one and publishes
`CAPTURE_CREATED`. `triage` validates the transition, stores the updated item,
and publishes `CAPTURE_TRAGED`. Event payloads are JSON-safe and intentionally
omit full raw text; the outbox redactor would strip secret-looking fields.
Convenience methods cover `accept`, `reject`, `archive`, `list`, `stats`,
`render`, `remove`, and JSON portability. A clock callable is injectable for
deterministic tests.

## API

Three routes are registered additively through the v4 route registry:

- `GET /api/v4/inbox` — list with `page`, `page_size`, `state`, `source`, `tag`,
  `query`, and opaque `cursor`; returns a weak ETag and supports
  `If-None-Match` via a `not_modified` response.
- `POST /api/v4/inbox/capture` — create from `raw` with optional `source`,
  `tags`, and `confidence`; duplicates return the stored item with
  `created=false`.
- `PATCH /api/v4/inbox/triage` — move by `state` or `action`; illegal moves
  become `409 conflict` errors naming the legal targets.

All handlers return `ok(data, meta)` envelopes. Validation uses
`ApiError(INVALID_INPUT)`, missing captures map to `NOT_FOUND`, illegal
transitions to `CONFLICT`, and missing capabilities to `FORBIDDEN`. The `guard`
decorator translates domain exceptions into structured API errors without
weakening validation errors. Routes require `READ` for listing and `WRITE` for
creating and triaging, gated by `FeatureFlag.INBOX`.

## Frontend

`InboxPanel` is a keyboard-first React panel. It offers a quick-capture
textarea, source chips, quick tags, state and source filters, a text query, and
an item list with accept/reject/archive buttons disabled when the transition is
illegal. Keyboard hints cover `Ctrl+Enter` (capture), `J`/`K` (move selection),
`A`/`R` (triage), and `/` (focus composer). `InboxClient` wraps `V4Client` with
typed list/capture/triage methods and local validation. `state.ts` holds a pure
reducer plus selectors for visible items, counts, selection, and legal targets.

All styling lives in `capture-inbox.css`, imports `tokens-v4.css`, and uses only
`var(--v4-*)` tokens for palette, spacing, type, elevation, focus, and motion.
Responsive rules collapse the toolbar on narrow screens; reduced-motion users
get no transitions.

## Verification

```bash
python3 -m ruff check .
python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
cd frontend && npm test && npm run format:check && npm run typecheck && npm run build
python3 scripts/loc_gate.py --baseline 9f0459cf510def70e9e78f08b54ec86795c246be \
  --min-added 2500 --min-net 2500 --min-test-loc 400
```
