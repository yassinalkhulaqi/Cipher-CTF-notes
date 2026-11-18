# V2 block editor

The block editor is an additive V2 feature for structured note editing. It keeps
the shipped v1 API and frontend untouched while providing a block IR, optimistic
revisions, autosave coalescing, block-level search, mention indexing, and an API
`blocks` namespace.

## Scope

- Backend domain: `src/redscribe/v2/blocks/`
- API namespace: `src/redscribe/ui/web/v2/namespaces/blocks.py`
- Frontend feature: `frontend/src/features/blocks/`
- Frontend tests: `frontend/scripts/blocks.test.ts`
- Backend tests: `tests/v2_blocks/`

Shared V2 route registration, the v1 API, storage migrations, and the shipped
frontend shell are not modified. Integrators opt in by calling
`redscribe.ui.web.v2.namespaces.blocks.register(api)` or by building a standalone
registry with `create_blocks_api(vault)`.

## Block model

A document is an immutable `BlockDocument` with an id, title, ordered blocks,
revision counter, timestamp, tags, and metadata. Every mutation returns a new
value so stale revisions and remote edits can be detected without shared mutable
state.

Supported block types:

| Type | Key fields | IR marker |
| --- | --- | --- |
| Paragraph | `text` | plain lines |
| Heading | `text`, `level` (1–6) | `#`–`######` |
| Code | `text`, `language` | fenced code block |
| Quote | `text` | `>` lines |
| List | `items`, `checked`, `style` | `-`, `1.`, `- [x]` |
| Table | `headers`, `rows` | pipe table with separator |
| Callout | `text`, `tone` | `> [!TONE]` |
| Divider | none | `---` |
| Image | `alt`, `source` | `![alt](source)` |

All types also carry `id`, `mentions`, and free-form string `attrs`. The model
normalizes Unicode, line endings, whitespace, ids, heading levels, list lengths,
table geometry, and mention offsets at every boundary. Sensitive image schemes
such as `javascript:` are rejected by validation.

## Markdown-like IR

`markdown.py` converts block documents to and from a small deterministic IR used
for note storage and paste round trips. Each block occupies one paragraph-sized
chunk; nested geometry is expressed with ordinary Markdown markers. Paragraph
lines that would start another block are escaped with a backslash.

```python
from redscribe.v2.blocks import parse_document, serialize_document

document = parse_document("# Report\n\nSee @[vault](note:home)", document_id="doc-1")
text = serialize_document(document)
```

`serialize_document(..., include_title=True)` prepends the document title as a
level-one heading when it is not already present.

## Diffs and patches

`diff_documents` computes a deterministic block-level delta with `add`, `remove`,
`replace`, and `move` entries. Signatures cover every rendering field, so content
changes on the same block id become `replace` rather than `move`. Pure reordering
becomes `move`.

`patch_from_diff` converts a diff into a `BlockPatch` with `insert`, `update`,
`delete`, and `move` operations. `apply_patch` requires the patch base revision to
match the document revision unless explicitly bypassed, and advances the revision
on success. `merge_entries` coalesces autosave streams:

- delete followed by insert of the same id becomes one update;
- update after insert keeps the insert position but uses the latest block;
- a move clears earlier operations for that id;
- repeated updates keep only the latest payload.

## Revisions

Revision tokens bind document id, revision, content signature, and content hash.
They are HMAC digests when a secret is configured and plain SHA-256 otherwise.
Tokens are encoded as opaque `rev1.<base64url-json>` strings and verified before
whole-document saves, patches, and note writes.

A mismatch raises `RevisionConflictError`, which the API maps to HTTP 409 with
`code: conflict` and details containing `expected`, `actual`, and `reason`.

## Autosave

`AutosaveCoalescer` buffers patch operations per document until either the idle
interval elapses or the maximum wait is reached. `merged_from` counts how many
edits were folded into one batch. `flush`, `flush_all`, and `flush_document`
return batches for persistence; `acknowledge` drops a batch once its revision has
been saved.

The store exposes `queue_autosave`, `flush_autosave`, `flush_all_autosave`, and
autosave status telemetry. `BlockVaultService.flush` also writes the resulting IR
back to the vault note body.

## Search and mentions

`BlockSearchIndex` is a token-postings index over block plain text. It supports
match-all or match-any queries, block-type and document filters, limits, offsets,
facets, snippets, and highlight terms. Replacing a document atomically updates
postings.

`MentionIndex` indexes `@[label](kind:target)` tokens across six namespaces:
`note`, `user`, `target`, `finding`, `evidence`, and `tag`. It provides backlinks
by target or kind plus ranked autocomplete suggestions. `refresh_block_mentions`
recomputes offsets after text edits.

## Vault bridge

`BlockVaultService` maps vault notes to document ids of the form `note-<id>`.
`load` parses note content into blocks and stores metadata for `note_id`,
`target`, and `status`. `save`, `save_patch`, and `flush` serialize back to IR and
call `Vault.update_node` so the note body remains the durable representation.
Non-note documents remain in the in-memory `BlockStore`.

## API namespace

All routes use the standard V2 envelope and `POST /api/v2/blocks/<action>` shape.
Mutating routes participate in request auditing, entity events, and idempotent
replay.

| Route | Purpose |
| --- | --- |
| `blocks.capabilities` | Block types, features, mention kinds, and limits |
| `blocks.schema` | Field contracts for all `blocks.*` routes |
| `blocks.create` | Create a document from blocks, Markdown IR, or a note id |
| `blocks.get` | Return a document, fresh token, and serialized IR |
| `blocks.list` | Paginated document summaries |
| `blocks.parse` | Parse Markdown IR into a detached document |
| `blocks.serialize` | Serialize a stored or inline document |
| `blocks.validate` | Return a structural validation report |
| `blocks.diff` | Diff two ids or inline documents |
| `blocks.patch` | Apply an optimistic patch and sync note-backed docs |
| `blocks.save` | Save a full document with a revision token |
| `blocks.replace_blocks` | Replace blocks from Markdown IR |
| `blocks.search` | Search indexed blocks with filters and pagination |
| `blocks.mentions` | Mention backlinks or autocomplete suggestions |
| `blocks.autosave` | Queue patch operations for coalescing |
| `blocks.autosave_status` | Report queue state and known documents |
| `blocks.flush` | Persist queued autosave batches |
| `blocks.delete` | Remove a document and derived indices |
| `blocks.reindex` | Rebuild search and mention indices |
| `blocks.status` | Store and service telemetry |

### Create and get

```json
{"title": "Report", "markdown": "## Summary\n\nSee @[vault](note:home)", "tags": ["ctf"]}
```

The response contains `document`, `token`, and `markdown`. Pass `note_id` instead
of an inline document to load a vault note. `blocks.get` accepts `id`,
`document_id`, or `note_id`.

### Patch

```json
{
  "id": "doc-1",
  "patch": {
    "document_id": "doc-1",
    "base_revision": 0,
    "label": "edit",
    "entries": [
      {
        "operation": "update",
        "block_id": "b1",
        "index": 0,
        "block": {"id": "b1", "type": "paragraph", "text": "new text"}
      }
    ]
  }
}
```

A patch may also be supplied as `operations` or `entries` plus `base_revision`.
Omitting `token` issues a fresh token for the addressed document.

### Autosave and flush

```json
{"id": "doc-1", "patch": {"base_revision": 0, "entries": []}, "token": "rev1...."}
```

`queued` is true when work was accepted into the debounce queue or produced an
immediate batch. `blocks.flush` accepts an optional `id`; omitting it flushes all
queued documents.

## Frontend feature

`frontend/src/features/blocks/` is a self-contained React feature:

- `types.ts`, `blocks.ts`, `ids.ts`: editor value types and defaults;
- `normalize.ts`, `markdown.ts`, `diff.ts`, `autosave.ts`, `validation.ts`: pure
  logic mirroring the backend contracts;
- `engine.ts`, `selection.ts`, `keyboard.ts`, `slashCommands.ts`, `mentions.ts`,
  `search.ts`: editing behavior and menu support;
- `api.ts`, `useBlockAutosave.ts`, `useBlockEditor.ts`: V2 client bindings;
- `components/`: block view, toolbar, slash menu, mention menu, diff view,
  search panel, and the composed editor.

`api.ts` converts between camelCase frontend values and snake_case API payloads.
`V2Client.call` unwraps the envelope, so flush results read `payload.saved`.
Selection updates are represented explicitly and applied through
`applyRemoteDocument` so remote revisions do not corrupt caret position.

The feature is not mounted in the shared `App.tsx` or `app/routes.ts`; host
applications opt in by composing `BlockEditor` with `useBlockEditor` and
`useBlockAutosave`.

## Error mapping

| Condition | HTTP | V2 code |
| --- | --- | --- |
| Unknown document or note | 404 | `not_found` |
| Missing required field | 400 | `missing_field` |
| Wrong field type | 400 | `invalid_type` |
| Unknown enum choice | 400 | `invalid_choice` |
| Malformed patch | 400 | `invalid_request` |
| Structural validation failure | 422 | `invalid_request` with `details.report` |
| Stale revision token | 409 | `conflict` with `details.code = revision_conflict` |

## Tests

Backend tests cover the model, normalization, Markdown IR, diffing, patching,
revision tokens, autosave, validation, search, mentions, store, vault bridge, and
API namespace under `tests/v2_blocks/`. Frontend tests cover the mirrored pure
logic, engine behavior, keyboard and slash handling, API conversion, and remote
document selection under `frontend/scripts/blocks.test.ts`.

Run the feature tests with:

```bash
PYTHONPATH=src python3 -m pytest -q -p no:asyncio tests/v2_blocks
cd frontend && npm test
```
