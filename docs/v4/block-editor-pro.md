# Block Editor Pro (v4)

The professional block editor provides safe round-tripping between immutable
documents and annotated markdown, an LCS change model, autosave snapshots,
structural validation, revisioned storage, and a v4 HTTP surface.

## Files

| Layer | Location |
| --- | --- |
| Value types | `src/redscribe/v4/blocks_pro/types.py` |
| Domain services | `src/redscribe/v4/blocks_pro/service.py` |
| Persistence | `src/redscribe/v4/blocks_pro/storage.py` |
| API handlers | `src/redscribe/v4/blocks_pro/api.py` |
| Tests | `tests/v4_blocks_pro/` |
| Frontend | `frontend/src/features/block-editor-pro/` |
| Frontend tests | `frontend/scripts/v4-block-editor-pro.test.ts` |

## Data model

`BlockKind` covers seven kinds: paragraph, heading, code, list, quote, table,
and divider. `InlineMark` covers bold, italic, code, and link decorations.
Every `Block` carries an identifier, kind, text, heading level, code language,
item tuple, and a sorted attribute tuple. `BlockDocument` is an ordered tuple
of blocks with an identifier and title. `EditOperation` describes an insert,
update, delete, or move with positional metadata.

All records are frozen and slots-based. They validate identity, size, and
shape at construction and convert to plain dictionaries through `to_dict` and
`from_dict`. Checksums are SHA-256 digests truncated to 24 hex characters and
are stable across dictionary key order.

## Markdown codec

`MarkdownCodec.encode` renders a document as markdown. By default every block
is preceded by an identity annotation, for example:

```markdown
# Investigation notes

<!-- block:b1 -->
## Findings

<!-- block:b2 -->
```python
print("hello")
```
```

`decode` reads those annotations back, so identifiers, heading levels,
languages, list styles, table headers, and item order survive a full
round-trip. `with_annotations(False)` produces clean markdown; decoding it
assigns fresh identifiers from the injected factory. `decode_with_id` restores
a document under an externally supplied identifier.

Headings use `#` runs, code uses fenced blocks with a language, quotes prefix
each line with `>`, lists support bullet, ordered, and task styles, tables use
a header plus separator row, and dividers render as `---`. The codec raises
`CodecError` for unterminated fences, malformed tables, and non-string input.

`apply_mark` and `strip_markdown` support toolbar formatting and plain-text
search. `markdown_summary` counts lines, blank lines, headings, and fences.

## Diffing

`BlockDiff.compare` computes an LCS over block identifiers and returns a tuple
of `EditOperation` values:

- `insert` for identifiers that appear only in the new document.
- `delete` for identifiers that appear only in the old document.
- `update` when a matched identifier has different content.
- `move` when a shared identifier changes position.

`apply` replays operations against the old document, handling deletes in
reverse index order, inserts in ascending order, updates by identifier, and
moves by target position. `line_diff` uses the same LCS engine for text lines.
`summary` counts operations by kind. Duplicate block identifiers and very
large document pairs are rejected with `DiffError`.

## Autosave

`AutosaveManager` creates immutable `Snapshot` records with sequential
revisions, reason strings, timestamps, and checksums. `verify` detects
tampering by recomputing the document checksum. `restore` optionally requires
an expected checksum for optimistic concurrency. `prune` and `prune_all`
remove snapshots older than an age limit and then trim to a maximum count;
malformed timestamps are discarded. The identifier factory and clock are
injected in tests for deterministic output.

## Validation

`BlockValidator` reports `ValidationIssue` values with stable codes and
severities. It checks blank titles, duplicate identifiers, heading depth and
content, code languages, list styles and empty lists, table header widths,
empty dividers, and paragraph blank lines. `validate_operations` also checks
index bounds, missing or duplicated identifiers, and conflicting destructive
operations on the same block.

## Storage

`BlockStore` provides create, save, replace, apply, get, list, delete, search,
export, and import. Every commit appends a `Revision` with a number, checksum,
timestamp, and author. `save` and `replace` accept an expected checksum to
reject stale writes with `ConflictError`. `restore_revision` appends a new
revision from an older one, and `prune_history` trims the tail. Snapshots are
delegated to an injected `AutosaveManager`. `export` uses the annotated codec,
`import_markdown` decodes and commits, and `digest` checksums the whole store.

## HTTP surface

| Route prefix | Method | Purpose |
| --- | --- | --- |
| `/api/v4/blocks` | GET | Get one document or a paginated list |
| `/api/v4/blocks/document` | PUT | Create or replace a document |
| `/api/v4/blocks/patch` | PATCH | Replay edit operations |
| `/api/v4/blocks/history` | GET | Page through revisions |
| `/api/v4/blocks/snapshots` | GET/PATCH | List, create, or restore snapshots |

Handlers return v4 envelopes with request identifiers, versions, pagination,
and weak ETags. They require the `BLOCKS_PRO` feature plus the relevant
`Capability`, and translate domain failures into stable `ErrorCode` values.
Every successful edit publishes a `BLOCK_EDITED` event with the document id,
revision checksum, operation labels, and actor. Registration is additive and
idempotent through the v4 `RouteRegistry`.

## Frontend

`ProEditor` renders a block list, a slash-command menu, an inline toolbar for
the four marks, a find/replace bar, a diff gutter, and a focus-mode toggle.
`state.ts` contains the typed reducer, selectors, and pure helpers; `client.ts`
wraps the shared `V4Client` with typed block-editor methods. CSS imports
`tokens-v4.css` and uses only `var(--v4-*)` design tokens.

## Safety

The feature is data-only. No shell execution, evaluation, or network access
occurs outside the HTTP client abstraction, and event payloads pass through
the foundation outbox redactor before persistence.
