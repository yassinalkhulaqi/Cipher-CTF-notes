# RedScribe v2 — Master Plan

Status: Proposed
Owner: yassinalkhulaqi
Date: 2026-11-17
Supersedes: `.agent/PLAN.md`, `docs/FRONTEND-PLAN.md` (kept for history)
Baseline: `origin/main` (`ef47adf`)
Delivery model: 12 stacked branches, each ≥ 4,000 net added code LOC

---

## 1. Executive review

### 1.1 What the project is today

RedScribe is a local-first desktop notebook for CTFs, pentests, and security
research. It is a Python standard-library backend, a single SQLite vault, a
localhost JSON API, and a bundled React/Zustand frontend opened in a webview or
browser. The product is already useful: a tree of folders/notes, Markdown editor
with live preview, full-text search, tags, flag intelligence, snippets, graph,
backlinks, timeline, trash/undo, version history, backups, exports, an API
contract layer, security middleware, and a CLI.

### 1.2 Measured state

| Area | `origin/main` |
| --- | --- |
| Tracked source, docs, tests | ~44,900 lines |
| Backend `src/redscribe` | ~12,300 lines |
| Frontend `frontend/src` | ~25,500 lines |
| Python tests | ~6,400 lines |
| Schema | `SCHEMA_VERSION = 3` (`nodes`, `snippets`, `settings`, `nodes_history`, FTS5) |
| Frontend tests | `node --test` suites bundled by `frontend/scripts/test.mjs` |
| CI | Python 3.10–3.13 + Windows 3.12, ruff, mypy, coverage ≥85, frontend build, committed bundle check, wheel smoke test |

`origin/main` reports 218 passing Python tests in its changelog. A clean checkout
needs `pip install -e ".[dev]"` before pytest can import `redscribe`.

### 1.3 Current repository risks

1. **Local `main` is stale.** Local `HEAD` (`c61721f`) is 32 commits behind
   `origin/main` (`ef47adf`), which already contains PRs #16–#22: API contracts,
   storage integrity/retention, content rendering, graph/search improvements,
   security hardening, and CLI/observability.
2. **Dirty work does not pass its own gates.** The working tree has ~422 tracked
   changed lines plus untracked editor/accessibility files. `npm run typecheck`
   currently fails with 7 TypeScript errors (`EditorEnginePanel.tsx`,
   `editorEngine.ts`), and `ruff check` reports 7 errors.
3. **The architecture is growing monolithically.** `Vault` is ~1,400 lines,
   `api.py` is a hand-written flat dispatch table, `NoteWorkspace.tsx` is ~800
   lines, and several CSS files exceed 1,000 lines. Adding ten large features
   without seams will create merge pain and regressions.
4. **The data model is note-centric.** Targets, findings, credentials, evidence,
   and reports are text fields on notes rather than first-class records. That is
   the largest product limitation for pentest work.
5. **The API has no v2 contract.** There is no pagination envelope, ETag/version
   concurrency, idempotency, request IDs, or namespaced routes. Large new
   features need these before they are safe.
6. **Branch sprawl.** There are ~39 local and ~19 remote branches, many one-off
   `feat/aurora-*` experiments. Several overlap; some are stale. The branch plan
   must include triage and deletion, not just creation.
7. **No browser-level E2E suite, no performance budgets, no i18n, no encryption,
   no offline/PWA path, and no blob/attachment store on `origin/main`.**

### 1.4 Strengths to preserve

- Zero required runtime dependencies in the Python core and no telemetry.
- Strict `mypy`, ruff, coverage, and frontend typecheck gates.
- Immutable domain dataclasses and a clear storage/content/services/UI split.
- A working local-only security posture: loopback bind, token auth, strict CSP,
  rate limiting, audit events, path traversal defenses.
- Design tokens, motion modes, accessibility documentation, and a large set of
  hand-built UI primitives that can be standardized rather than replaced.
- The existing feature set is a strong base; the v2 plan extends it rather than
  rewriting it.

### 1.5 Decisions

1. **Do not branch from the dirty local `main`.** Preserve the dirty work on a
   `wip/` branch, fast-forward `main` to `origin/main`, then start the v2 train.
2. **Salvage, do not merge blindly.** Reuse the untracked editor engine in the
   block-editor branch and the accessibility helpers in the accessibility
   branch. Close duplicate/stale `aurora-*` branches after cherry-picking.
3. **Contract-first, then feature branches.** `B00` establishes schema
   migration conventions, API v2, frontend routing, design-system primitives,
   test harness, and the LOC gate. Every later branch builds on those seams.
4. **Keep local-first invariants.** No accounts, no telemetry, no remote calls.
   New runtime dependencies require explicit approval; encryption and packaging
   may use optional extras, never core dependencies.
5. **Enforce the 4,000-line requirement with tooling, not trust.** A LOC gate
   measures human-authored production + test additions per branch and excludes
   generated bundles, lockfiles, images, and vendored files.

---

## 2. Product scope for v2

### 2.1 Product statement

Turn RedScribe from a strong CTF notebook into a complete **local-first security
research workbench**: capture notes, model the engagement, store evidence, reason
over relationships, produce client-ready reports, move vaults safely between
machines, and do all of it offline with a strong privacy boundary.

### 2.2 Primary workflows

1. **Capture:** quick note, template, snippet, or pasted output becomes structured
   knowledge in seconds.
2. **Model:** an engagement contains scope, targets, assets, services, credentials,
   findings, evidence, and activity.
3. **Author:** write in blocks, link entities, attach evidence, reference findings.
4. **Find:** query with facets and operators, save searches, jump by command.
5. **Reason:** graph, backlinks, duplicate/orphan detection, flag and target intel.
6. **Report:** select findings/evidence, redact, preview, print/export HTML,
   Markdown, or JSON with a stable manifest.
7. **Move:** export/import/merge bundles, verify integrity, restore backups.
8. **Trust:** optional encrypted vault, secret detection, redaction, audit trail,
   local auth, no network egress.
9. **Operate:** fast on large vaults, offline-capable, keyboard-first, accessible,
   localized, and scriptable through the CLI.

### 2.3 Non-goals for v2

- Team collaboration, accounts, cloud sync, or hosted services.
- Executing offensive tools from the app. Snippets and playbooks are reference
  material and checklists; the app never runs arbitrary commands.
- A general-purpose document suite or full IDE.
- A plugin marketplace. Internal extension seams are welcome; third-party code
  execution is not.
- Telemetry, crash reporting, or remote assets of any kind.

### 2.4 Success criteria

- A full engagement can be created, evidenced, reported, exported, and re-imported
  without editing the SQLite file by hand.
- Every v1 route and workflow keeps working through the v2 API adapter.
- `pytest`, frontend typecheck/tests, lint, mypy, format, wheel smoke, and the new
  LOC gate pass on every branch.
- Large-vault targets: 20,000 notes, 10,000 findings, 5,000 attachments, tree
  interactions under 100 ms, search first results under 150 ms on a laptop.
- WCAG 2.2 AA for all new surfaces; keyboard-only completion of every workflow.
- No runtime network calls beyond `127.0.0.1`.

---

## 3. Target architecture

### 3.1 Backend layout

Keep the current layered shape, but split the monoliths into explicit seams:

```
src/redscribe/
  domain/            pure dataclasses, value objects, validation, scoring
  content/           markdown, block AST, highlighting, templates, snippets
  storage/
    db.py            Vault facade and compatibility methods
    migrations/      ordered, testable schema migrations
    repositories/    nodes, engagements, findings, blobs, reports, sync, settings
    integrity.py     integrity, drift, repair
    retention.py     prune/backup/rotation
  services/          import/export, reports, graph, intel, sync, redaction
  api/
    contracts/       request/response schemas and error codes
    routes/          namespaced handlers (engagements, evidence, search, ...)
    serializers/     model -> JSON
    middleware/      auth, rate limit, request id, idempotency, audit
  cli/               doctor, stats, backup, migrate, export, import, verify
  ui/web/            local server and bundled static assets
```

Rules:

- The core (`domain`, `storage`, `services`) never imports the web UI.
- One `Vault` facade remains for compatibility; feature repositories are wired
  behind it. Existing methods do not change signatures unless deprecated.
- All SQL lives in storage repositories or the `Vault` facade, never in services
  or routes.
- Every mutation is transactional and, where it has external effects, journaled.
- New schema versions are append-only migrations. Vaults from newer versions are
  still rejected. Migration tests cover every historical version.

### 3.2 Data model roadmap

| Version | Branch | New storage |
| --- | --- | --- |
| v4 | B00 | `schema_migrations`, `entity_events`, `idempotency_keys`, `request_audit` |
| v5 | B01 | `engagements`, `targets`, `assets`, `services`, `credentials`, `findings`, `finding_evidence` |
| v6 | B02 | `blobs`, `evidence_items`, `evidence_links`, `evidence_annotations` |
| v7 | B03 | `documents`, `document_blocks`, `document_revisions` |
| v8 | B04 | `saved_searches`, `search_history`, `search_terms`, FTS v2 |
| v9 | B05 | `playbooks`, `playbook_steps`, `playbook_runs`, `snippet_usage` |
| v10 | B06 | `entities`, `entity_links`, `link_candidates`, `graph_snapshots` |
| v11 | B07 | `reports`, `report_sections`, `report_items`, `report_exports` |
| v12 | B08 | `sync_bundles`, `sync_ops`, `sync_conflicts`, `bundle_manifests` |
| v13 | B09 | `vault_keys`, `secret_findings`, `redactions`, `security_prefs` |
| v14 | B10 | `ui_preferences`, `keybindings`, `themes`, `locales` |
| v15 | B11 | `perf_cache`, `offline_manifests`, `startup_samples` |

Backward compatibility: `nodes` remains the note/folder table through v2.
Engagements/findings link to notes rather than replacing them. Existing
`target`, `status`, `difficulty`, and `flag` fields are backfilled into new
entities by B01 and remain readable until the v3 schema cleanup.

### 3.3 API v2 contract

Keep RPC-style calls to minimize churn, but add a namespaced, versioned surface:

```
POST /api/v2/<namespace>/<action>
GET  /api/v2/download/<kind>/<id>
GET  /api/v2/events?since=<cursor>
```

Response envelope:

```json
{
  "ok": true,
  "data": {},
  "meta": {
    "request_id": "ulid",
    "page": { "cursor": "opaque", "next": "opaque", "total": 42 },
    "etag": "sha256:...",
    "api_version": "2.0"
  }
}
```

Error envelope:

```json
{
  "ok": false,
  "error": {
    "code": "not_found",
    "message": "Finding does not exist",
    "details": {},
    "retryable": false,
    "request_id": "ulid"
  }
}
```

Contract requirements:

- Typed request/response schemas for every new route; generated route inventory
  exposed through `system.api_schema`.
- Pagination, filtering, sorting, and sparse fields for list routes.
- Idempotency keys for all mutations; safe replay returns the original result.
- Optimistic concurrency with ETags / `expected_version` on mutable records.
- Request IDs echoed in logs and errors.
- v1 compatibility adapter for the current flat method names; it is removed only
  in v3.
- Auth token, origin checks, CSP, and rate limits apply to v2 exactly as they do
  to v1.

Reserved namespaces:

| Branch | Namespaces |
| --- | --- |
| B00 | `system`, `api`, `events` |
| B01 | `engagements`, `targets`, `assets`, `services`, `credentials`, `findings` |
| B02 | `blobs`, `evidence` |
| B03 | `documents`, `blocks` |
| B04 | `search`, `commands`, `saved_searches` |
| B05 | `snippets`, `playbooks`, `runs` |
| B06 | `graph`, `intel` |
| B07 | `reports`, `exports` |
| B08 | `sync`, `bundles` |
| B09 | `security`, `secrets`, `redactions` |
| B10 | `prefs`, `i18n`, `themes` |
| B11 | `perf`, `offline` |

### 3.4 Frontend architecture

Move from modal-heavy single-screen state to explicit workspaces while keeping
the existing shell and design language:

```
frontend/src/
  app/           router, shell, providers, route registry, error boundaries
  features/      engagements, evidence, editor, search, playbooks, graph,
                 reports, sync, security, settings
  components/    shared visual components (existing, progressively extracted)
  ui/            design-system primitives: Button, Dialog, DataTable, Field,
                 Tabs, Menu, Toolbar, EmptyState, Toast, Banner
  lib/           api client v2, query cache, tree, tags, router, i18n, a11y
  store/         small Zustand slices (app, workspace, ui, selection, prefs)
  motion/        existing motion engine
  styles/        tokens, primitives, feature styles, print, RTL, high contrast
```

Rules:

- One route registry, hash-based first (desktop/webview-safe), with typed params.
- Feature folders own their API calls, store slice, components, styles, and tests.
- A shared query cache handles dedupe, cancellation, pagination, and invalidation.
- The command registry becomes the single source of truth for palette commands,
  menus, toolbars, and keyboard shortcuts.
- No new runtime dependencies without approval. Prefer React/Zustand/lucide,
  custom SVG, CSS, and browser APIs.
- Every stylesheet uses tokens; no new raw colors, radii, durations, or widths.
- Generated static bundles are rebuilt and committed, but excluded from LOC
  accounting.

### 3.5 Local-first and security invariants

- Server binds only to loopback; no CORS; origin and host validated.
- Auth token, CSP, `nosniff`, `no-referrer`, `no-store` for API responses.
- Vault data stays in one SQLite file; blobs live in `<vault>.assets/` with
  content-addressed names and hash verification.
- Optional encryption uses an opt-in extra; the core remains dependency-free.
- Secret detection and redaction never upload content; they run locally.
- Exports include a manifest with hashes so recipients can verify integrity.
- No analytics, remote fonts, remote images, or update pings.

---

## 4. Engineering rules and quality gates

### 4.1 Definition of done (every branch)

- Production code, tests, docs, and changelog entry are in the branch.
- New schema migration tested from an empty vault and every prior schema version.
- New API routes documented and covered by contract tests.
- New UI is keyboard-complete, screen-reader-labelled, and works in dark, light,
  high-contrast, reduced-motion, and 420–1440 px layouts.
- No unhandled promise rejections, no swallowed errors in new code.
- Bundle rebuilt and committed (excluded from LOC count).
- `python -m ruff check .`, `ruff format --check .`, `mypy src`, `pytest`,
  frontend `npm test`, `npm run typecheck`, `npm run format:check`,
  `npm run build`, wheel smoke test, and the LOC gate pass.
- Branch diff reviewed for dead code, duplicated code, and accidental secrets.
- The branch does not reduce existing coverage or break v1 compatibility.

### 4.2 LOC gate

Every branch must add **at least 4,000 human-authored production + test lines**
before merge. Docs are required but counted separately, so a branch cannot meet
the floor with prose alone.

Counted paths:

- `src/**/*.py`
- `tests/**/*.py`
- `frontend/src/**/*.ts`, `*.tsx`, `*.css`
- `frontend/scripts/**/*.ts`, `*.mjs`
- `scripts/**/*.py`, `*.mjs` (tooling)
- `docs/**/*.md` only for the separate documentation minimum

Excluded:

- `src/redscribe/ui/web/static/assets/*` (generated bundle)
- `frontend/package-lock.json`
- images, snapshots, fixtures over 100 KB, `.autonomous/`, `.opencode/`
- generated JSON/CSV fixtures

Suggested measurement:

```bash
BASE="$(git merge-base origin/main HEAD)"
git diff --numstat "$BASE" HEAD -- \
  'src/**/*.py' 'tests/**/*.py' 'scripts/**/*.py' \
  'frontend/src/**/*.ts' 'frontend/src/**/*.tsx' 'frontend/src/**/*.css' \
  'frontend/scripts/**/*.ts' 'frontend/scripts/**/*.mjs' \
  | awk '{add += $1; del += $2} END {printf "added=%d deleted=%d total=%d\n", add, del, add+del}'
```

The gate requires **added ≥ 4,000** and **test additions ≥ 500**. A branch below
the floor is not padded; it absorbs a listed stretch item or merges with its
neighbor.

### 4.3 Test matrix

| Layer | Tool | Gate |
| --- | --- | --- |
| Domain/storage/services | pytest | all green, coverage ≥85 |
| API contracts and server | pytest + HTTP client | every route, error, pagination, auth |
| Migrations | pytest | empty + v1/v2/v3 → latest, idempotent reopen |
| Frontend pure logic | `node --test` via scripts/test.mjs | all green |
| Type safety | `tsc --noEmit` | clean |
| Visual/accessible UI | manual checklist + automated axe-style checks where possible | no serious issues |
| End-to-end | Node fetch/HTTP smoke + browser manual (B11 may add dev-only automation) | full workflow |
| Packaging | wheel build + install + CLI/web smoke | clean |
| Large vault | seeded 20k-note/5k-attachment benchmark | budgets met |

### 4.4 Performance budgets

- App boot to interactive: < 1.5 s with a 5,000-note vault.
- Tree expand/select: < 100 ms perceived.
- Search first page: < 150 ms on 20k notes.
- Editor keystroke: < 16 ms input handling; preview render debounced.
- Graph layout: < 2 s for 2,000 nodes, progressive rendering above that.
- Report export: < 5 s for a 200-finding engagement.
- No unbounded DOM lists: tree, search, findings, and evidence use virtualization.

### 4.5 Branch and commit policy

- Branch names: `dev/v2-00-platform-kernel` through `dev/v2-11-performance-offline`.
- Remote enforcement: this repository only accepts `dev/*` branch pushes, so all
  v2 branches use the `dev/` prefix; `feat/*` is local-only unless policy changes.
- Bases: each branch starts from `main` after its dependencies are merged.
- Merge order: numeric branch order; parallel wave branches rebase before merge.
- Never push or commit directly to `main`; merge through PRs with the full gate.
- Commits are small and scoped: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`,
  `chore:`.
- Each branch includes a `BRANCH.md` note in its PR description or `.agent/` log
  with scope, files, tests run, LOC count, and known gaps.
- Existing stale branches are triaged in B00 and deleted after salvage.

---

## 5. Branch strategy

### 5.1 Branch train

| # | Branch | Theme | Depends on | Schema | Merge slot |
| --- | --- | --- | --- | --- | --- |
| 00 | `dev/v2-00-platform-kernel` | Rescue, foundation, API v2, UI shell | baseline | v4 | 1 |
| 01 | `dev/v2-01-engagement-core` | Engagement/target/finding model | 00 | v5 | 2 |
| 02 | `dev/v2-02-evidence-vault` | Attachments, blobs, evidence, annotations | 01 | v6 | 3 |
| 03 | `dev/v2-03-block-editor` | Block document model and editor | 00 | v7 | 4 |
| 04 | `dev/v2-04-search-commands` | Query language, facets, saved searches, command system | 01, 03 | v8 | 5 |
| 05 | `dev/v2-05-playbooks-snippets` | Variables, playbooks, runbooks, safe copy | 01 | v9 | 6 |
| 06 | `dev/v2-06-graph-intel` | Entity graph, suggestions, duplicates, orphans | 01, 02, 04 | v10 | 7 |
| 07 | `dev/v2-07-reporting-studio` | Report builder, redaction, HTML/print/JSON/MD | 01, 02, 05 | v11 | 8 |
| 08 | `dev/v2-08-sync-portability` | Bundles, merge/conflict, import/export, CLI | 01, 02 | v12 | 9 |
| 09 | `dev/v2-09-security-privacy` | Secrets, redaction, encryption, audit UI | 02, 08 | v13 | 10 |
| 10 | `dev/v2-10-a11y-i18n-themes` | i18n/RTL, keybindings, theme studio, WCAG 2.2 | 01–09 UI | v14 | 11 |
| 11 | `dev/v2-11-performance-offline` | Virtualization, workers, PWA, desktop polish, release | 00–10 | v15 | 12 |

### 5.2 Waves

- **Wave 0 — foundation (B00):** repo rescue, API v2, routing, design primitives,
  migration framework, LOC gate, CI updates.
- **Wave 1 — core domain and authoring (B01, B03, B09 start):** engagement model,
  block editor, initial security/redaction rules. These are the new foundations.
- **Wave 2 — evidence and findability (B02, B04, B05):** evidence vault, advanced
  search/commands, snippets/playbooks.
- **Wave 3 — intelligence and output (B06, B07, B08):** graph/intel, reporting,
  portability/sync.
- **Wave 4 — experience (B10):** accessibility, i18n/RTL, themes, keybindings.
- **Wave 5 — speed and release (B11):** virtualization, workers, offline/PWA,
  desktop integration, release hardening.

Parallel work uses the reserved schema versions, API namespaces, and feature
folder ownership in this document. A branch that needs another branch's data
ships a contract stub behind a feature flag until the dependency merges.

### 5.3 Existing branch disposition

| Existing work | Action |
| --- | --- |
| `origin/main` through PR #22 | Become the new baseline; no rework |
| Untracked `editorEngine.ts`, `EditorEnginePanel.tsx` | Stabilize and fold into B03 |
| Untracked `a11y.ts`, `announcer.ts`, `useAccessibility.ts`, `ScreenReaderAnnouncer.tsx`, `accessibility.css` | Fold into B10; dedupe against origin accessibility docs |
| `dev/feat/attachments` | Re-implement under B02 with the v2 blob model; do not merge the old branch as-is |
| `dev/feat/rich-text` / `rich-editor*` | Cherry-pick callout/task-list parser ideas into B03 |
| `feat/aurora-*`, `feat/aurora-*-copy`, `dev/auto-*` | Review, cherry-pick unique tests/docs, then delete |
| `auto/engine-accessibility-20261116` | Blocked; salvage tests/ideas into B10 |
| `auto/engine-security-hardening-20261116` | Already represented in origin security work; close after comparison |
| `.autonomous/`, `.opencode/` | Keep out of product branches unless intentionally tooling-scoped |

### 5.4 Conflict-avoidance rules

- Backend: one feature owns one repository module and one route namespace.
- Schema: only the reserved version per branch; never edit an already-merged
  migration.
- Frontend: one feature owns one `frontend/src/features/<feature>/` folder; shared
  primitives change only in B00 or through a small reviewed PR.
- Styles: feature CSS in the feature folder; token changes only in B00/B10.
- API contracts: additive only unless the contract owner approves a breaking
  change; v1 adapter preserved.
- Generated bundle: rebuild last, after source merges; never hand-edit.

---

## 6. Branch specifications and LOC budgets

Legend: **BE** = Python production, **FE** = TypeScript/TSX/CSS production,
**T** = Python + frontend tests. Docs are additional and required. All totals
exceed the 4,000-line floor.

### B00 — `dev/v2-00-platform-kernel`

**Mission:** make the repository safe to build on for ten more branches. Rescue
the dirty work, synchronize with `origin/main`, establish API v2, routing, design
primitives, migration conventions, and automated gates.

**Backend**
- Preserve the dirty tree on `wip/aurora-editor-a11y`; fast-forward `main` to
  `origin/main`; triage untracked files into future branches.
- Add `storage/migrations/` registry and schema v4: migrations bookkeeping,
  entity event journal, idempotency keys, request audit. Migrate v1/v2/v3.
- Add API v2 router, request/response envelopes, request IDs, pagination,
  idempotency middleware, ETag helpers, and v1 compatibility adapter.
- Add `system.api_schema`, `system.health`, `system.capabilities`, `system.events`.
- Split `api.py` dispatch into route modules without changing v1 behavior.
- Add `scripts/loc_gate.py`, `scripts/branch_report.py`, and CI jobs.

**Frontend**
- Hash router and route registry; app shell extracted from `App.tsx`.
- Design-system primitives: `Button`, `IconButton`, `Dialog`, `Field`, `Tabs`,
  `Menu`, `Toolbar`, `DataTable`, `Banner`, `EmptyState`, `Toast`, `Skeleton`.
- API client v2: cancellation, retries, request IDs, pagination cache, typed
  errors; keep existing `api` calls via adapter.
- Feature-folder convention and one migrated feature as the reference pattern.
- Command registry abstraction over the existing palette and hotkeys.
- Fix the current TypeScript failures; either finish or quarantine the editor
  engine behind a disabled flag.

**Tests and docs**
- Migration tests, contract snapshot tests, idempotency/pagination tests,
  router tests, primitive keyboard/ARIA tests, LOC gate tests.
- `docs/V2_ARCHITECTURE.md`, `docs/API_V2.md`, `docs/BRANCH_PLAYBOOK.md`,
  `docs/QUALITY_GATES.md`.
- Update CI for Python 3.13, Node 20, LOC gate, v2 contract checks.

**LOC budget:** BE 1,350 · FE 1,950 · T 900 · **code total 4,200** · docs 250

**Exit:** clean checkout passes every gate; v1 frontend behavior unchanged; v2
routes callable; LOC gate rejects a seeded 3,999-line branch; branch backlog
triage completed.

**Stretch:** OpenAPI-like schema export, request replay tester, route fuzzing.

---

### B01 — `dev/v2-01-engagement-core`

**Mission:** make engagements, scope, targets, assets, services, credentials, and
findings first-class records, with notes as the narrative layer.

**Backend**
- Schema v5 and repositories for engagements, targets, assets, services,
  credentials, findings, finding-evidence links.
- Domain value objects: scope status, severity, CVSS vector validation, CWE/CVE
  references, confidence, finding state machine (`draft → confirmed → reported →
  retested`).
- Backfill `nodes.target`, status, difficulty, and flags into entities.
- Services: engagement lifecycle, scope warnings, duplicate finding detection,
  severity rollups, target coverage.
- API namespaces: `engagements`, `targets`, `assets`, `services`, `credentials`,
  `findings`; paginated list routes and optimistic concurrency.
- Import/export hooks for the new models; audit events on every mutation.

**Frontend**
- Router routes `#/engagements`, `#/engagements/:id`, `#/targets/:id`,
  `#/findings/:id`.
- Engagement list/detail, scope editor, target/asset/service tables, credible
  empty/loading/error states.
- Finding editor: title, severity, CVSS, CWE/CVE, affected target/asset, status,
  reproduction, impact, remediation, references, evidence placeholders.
- Dashboard widgets: open findings by severity, scope coverage, stale findings.
- Notes stay the authoring surface; "create note from finding" and
  "link note to finding" flows.

**Tests**
- Entity CRUD, state transitions, scope validation, backfill from v3, rollups,
  pagination, concurrency conflicts, API contracts, frontend table/filter logic.

**LOC budget:** BE 1,950 · FE 2,000 · T 700 · **code total 4,650** · docs 180

**Exit:** a user can create an engagement, add scope/targets/assets/services/
credentials, file a finding, link a note, and see accurate dashboard rollups.

**Stretch:** reusable scopes, target import from CSV/JSON, finding templates.

---

### B02 — `dev/v2-02-evidence-vault`

**Mission:** store, deduplicate, preview, annotate, redact, and link evidence
without bloating the SQLite file.

**Backend**
- Schema v6: blobs, evidence items, evidence links, annotations. Blob store under
  `<vault>.assets/v2/<sha256>` with temp-write + atomic rename.
- Streaming upload/download with size caps, MIME sniffing, hash verification,
  refcounts, orphan GC, and path-traversal defenses.
- Evidence metadata: filename, media type, size, hashes, source, timestamp,
  caption, linked finding/target/note, redaction state.
- Annotation model: rectangles, arrows, text, redaction strokes as normalized
  coordinates; revision-safe updates.
- API: `blobs.put/get/head/gc`, `evidence.*`; download routes with content
  disposition; manifest export.
- Integrity checks: missing blob, hash mismatch, orphaned row, dangling link.

**Frontend**
- Evidence gallery, drag/drop, paste image, file picker, progress, dedupe notice.
- Preview: image, text, code, PDF placeholder/embed, unknown-type download card.
- Annotation canvas with pointer and keyboard nudging; redaction mode.
- Evidence picker for notes/findings; thumbnails; usage panel; delete/refcount
  messaging.
- Broken/missing evidence state and repair action.

**Tests**
- Dedup, hash mismatch, size limit, traversal, GC, refcount, annotation
  round-trip, redaction, API download headers, frontend file-type/preview tests.

**LOC budget:** BE 1,650 · FE 1,950 · T 750 · **code total 4,350** · docs 160

**Exit:** drop a file, attach it to a finding, annotate/redact it, restart, and
retrieve a byte-identical file with verified hash; GC leaves live data intact.

**Stretch:** image thumbnail cache, clipboard HTML evidence, evidence bundles.

---

### B03 — `dev/v2-03-block-editor`

**Mission:** introduce a structured block document model and editor while keeping
Markdown as the portable source of truth.

**Backend**
- Schema v7: documents, blocks, revisions; block AST with a versioned schema.
- Bidirectional Markdown ↔ blocks conversion for paragraphs, headings, lists,
  checklists, code, tables, quotes, callouts, dividers, images/files, links,
  finding references, and raw Markdown fallback.
- Validation, stable block IDs, reorder/move transactions, undo-friendly
  revisions, and migration from existing `nodes.content`.
- Render pipeline integration with safe HTML and syntax highlighting.
- API: `documents.get/save/patch/reorder`, `blocks.*`, conversion endpoints.

**Frontend**
- Salvage `editorEngine.ts` from the dirty tree; build a block editor surface
  with slash menu, block handles, drag reorder, keyboard selection, and
  Markdown fallback mode.
- Block types, inline formatting, code language picker, table editing, task
  lists, callouts, image/evidence insertion, finding links.
- Autosave, conflict banner, revision history, find/replace across blocks,
  outline, reading view compatibility.
- Keep split preview and synchronized scroll; ensure mobile/coarse-pointer
  behavior.

**Tests**
- Markdown round-trip for all block types, AST validation, block operations,
  migration of existing notes, editor command logic, keyboard navigation,
  corrupt/unknown block fallback.

**LOC budget:** BE 1,300 · FE 2,350 · T 700 · **code total 4,350** · docs 160

**Exit:** existing Markdown notes open unchanged; editing in blocks and
switching to Markdown does not lose content; every block type round-trips.

**Stretch:** table column resize, collapsible sections, Mermaid-like fenced
diagram fallback without a rendering dependency.

---

### B04 — `dev/v2-04-search-commands`

**Mission:** make search and command execution feel like a precise instrument:
operators, facets, saved searches, frecency, and a unified command registry.

**Backend**
- Schema v8: saved searches, search history, search terms; FTS v2 indexes for
  notes, findings, targets, evidence metadata, and reports.
- Query language: quoted phrases, boolean `AND/OR/NOT`, parentheses, field
  operators (`tag:`, `status:`, `severity:`, `target:`, `type:`, `flag:`,
  `after:`, `before:`, `has:evidence`, `path:`), and safe error messages.
- Facet aggregation, cursor pagination, ranked snippets, highlight offsets, and
  query timing.
- Saved searches, recent searches, frecency, and per-vault defaults.
- API: `search.query/facets/suggest/saved.*`; `commands.list/execute` for safe
  app commands only.

**Frontend**
- Full search workspace with query bar, operator autocomplete, facet rail,
  result grouping, preview pane, keyboard navigation, and "open in context".
- Saved-search manager, recent history, empty/error/zero-result states.
- Palette v2: command registry, context-aware commands, frecency, recent notes,
  snippets, findings, settings, and actions.
- Keyboard customization foundation with conflict detection and reset.
- Virtualized result list and query timing display.

**Tests**
- Parser precedence/edges, malicious query input, facet correctness, ranking,
  pagination, saved-search CRUD, command availability, keyboard navigation,
  frecency ordering.

**LOC budget:** BE 1,450 · FE 2,050 · T 700 · **code total 4,200** · docs 150

**Exit:** a compound query with facets returns correct, paginated, highlighted
results in under 150 ms on the benchmark vault; every palette action is
discoverable and keyboard-operable.

**Stretch:** query explain mode, search macros, per-engagement default filters.

---

### B05 — `dev/v2-05-playbooks-snippets`

**Mission:** turn snippets into safe, reusable playbooks with variables,
checklists, usage history, and engagement-aware runs.

**Backend**
- Schema v9: playbooks, steps, runs, snippet usage.
- Variable schema and resolver scoped to note, target, engagement, operator, and
  environment; escaped substitution; missing-variable reporting.
- Built-in packs, custom snippets, categories, favorites, import/export, usage
  stats, and deprecation metadata.
- Playbook step types: command/reference, checklist, note, decision, evidence
  capture. Progress and per-run state; never execute commands.
- Safety classifier: destructive/credential/network warnings, required
  confirmation, redaction hints.
- API: `snippets.*`, `playbooks.*`, `runs.*`.

**Frontend**
- Snippet library v2: categories, search, favorites, variable preview, copy with
  resolved values, safety banner.
- Snippet/playbook editor with step ordering, variable definitions, preview, and
  validation.
- Run mode: progress, per-step checkboxes, notes/evidence capture, skip/reset,
  export run log.
- Engagement-aware insertion and "insert at cursor" against the block editor.
- Import/export UI for packs.

**Tests**
- Variable escaping, missing values, scope precedence, step ordering, run state,
  import/export, safety classification, frontend copy/insertion logic.

**LOC budget:** BE 1,550 · FE 1,950 · T 700 · **code total 4,200** · docs 160

**Exit:** a playbook runs end-to-end as a record of work, resolves variables
correctly, warns on dangerous steps, and exports a reproducible run log.

**Stretch:** community pack format versioning, snippet diff, bulk tag changes.

---

### B06 — `dev/v2-06-graph-intel`

**Mission:** reason over the whole vault: typed entity graph, link intelligence,
similarity, duplicates, orphans, and actionable insights.

**Backend**
- Schema v10: entities, entity links, link candidates, graph snapshots.
- Build a typed graph across notes, folders, engagements, targets, assets,
  findings, evidence, tags, and reports.
- Edges: containment, explicit wikilink, entity reference, shared evidence,
  shared target/service, suggested similarity, duplicate candidate.
- Algorithms: orphan detection, unresolved links, duplicate findings/notes,
  related-note suggestions, coverage gaps, stale evidence, tag/target clusters.
- Incremental graph rebuild with cache invalidation; snapshot export.
- API: `graph.query/insights/rebuild`, `intel.*`.

**Frontend**
- Graph workspace with SVG canvas, pan/zoom, typed lenses/filters, search focus,
  node inspector, progressive layout, and empty/loading states.
- Insights panel: duplicates, orphans, unresolved links, missing evidence,
  stale findings, untagged targets.
- Link suggestions in the editor and finding side panel.
- Timeline v2 with entity scope and filters; graph export as SVG/JSON.
- Keyboard traversal and screen-reader list alternative for the graph.

**Tests**
- Graph construction, cycle handling, incremental rebuild, duplicate detection,
  similarity ranking, insight determinism, large-graph performance, SVG layout
  math, accessibility list parity.

**LOC budget:** BE 1,750 · FE 1,850 · T 700 · **code total 4,300** · docs 150

**Exit:** graph and insights are deterministic, fast enough at 2,000 nodes, and
every graph action has a keyboard-accessible non-canvas equivalent.

**Stretch:** graph snapshots/diff over time, cluster collapse, saved graph views.

---

### B07 — `dev/v2-07-reporting-studio`

**Mission:** produce client-ready reports from findings and evidence, with
redaction, templates, print/HTML/PDF-via-print, Markdown, and JSON.

**Backend**
- Schema v11: reports, sections, report items, exports.
- Report model: cover, scope, methodology, findings, evidence, appendices,
  custom sections, ordering, inclusion rules, variables.
- Safe HTML renderer with document TOC, print CSS, page breaks, headers/footers,
  and stable hashes.
- Redaction pipeline: field-level, evidence-level, and pattern-based; verify no
  secret leaks in output.
- Markdown and JSON export with manifest; export history and deterministic
  filenames.
- API: `reports.*`, `exports.*`, preview/download routes.

**Frontend**
- Report workspace: section outline, add/reorder/toggle items, finding selector,
  evidence picker, redaction controls, template chooser, theme/style options.
- Live preview with pagination hints and print preview.
- Export dialog, history, integrity manifest, and open/download actions.
- Empty/error states for missing evidence, no findings, and redacted content.

**Tests**
- Renderer escaping, TOC/page breaks, inclusion rules, redaction, manifest
  hashes, export determinism, migration, preview/print snapshots, frontend
  section editing.

**LOC budget:** BE 2,050 · FE 1,950 · T 700 · **code total 4,700** · docs 180

**Exit:** a 200-finding engagement exports a complete, redacted report; no
un-redacted secret appears; output is byte-for-byte deterministic given the same
vault state.

**Stretch:** report templates, custom CSS theme, audience-specific variants.

---

### B08 — `dev/v2-08-sync-portability`

**Mission:** make vaults safely portable: export/import bundles, merge with
conflict policy, verify integrity, and operate from the CLI.

**Backend**
- Schema v12: sync bundles, operations, conflicts, manifests.
- Bundle format (`.rsvault` zip): manifest, schema version, SQLite snapshot or
  logical records, blob manifest with hashes, optional signatures.
- Export/import/merge services with dry-run, conflict detection, and policies:
  newest-wins, local-wins, remote-wins, duplicate-copy, manual.
- Logical merge for notes, engagements, findings, evidence, playbooks, reports;
  blob reference reconciliation and orphan handling.
- CLI: `export`, `import`, `merge`, `verify`, `diff`, `restore`, plus JSON output
  and non-zero exit codes for automation.
- Integrity and schema compatibility checks before any write.

**Frontend**
- Sync center: export wizard, import preview, conflict list, per-field/entity
  resolution, progress, and result summary.
- Dry-run diff before merge; backup-before-merge notice.
- Restore/verify UI for backup bundles; readable diagnostics.
- No background network; bundles are local files.

**Tests**
- Round-trip export/import, merge matrices for each policy, conflict resolution,
  corrupted bundle rejection, schema mismatch, hash mismatch, CLI exit codes,
  large-bundle streaming, frontend conflict selection.

**LOC budget:** BE 2,250 · FE 1,300 · T 750 · **code total 4,300** · docs 200

**Exit:** export a vault, edit both copies, merge with a chosen policy, and prove
the result is deterministic and integrity-verified; CLI does the same headlessly.

**Stretch:** bundle signing, selective export by engagement/tag, incremental
sync journal compaction.

---

### B09 — `dev/v2-09-security-privacy`

**Mission:** make RedScribe trustworthy for sensitive engagements: secret
detection, redaction, optional encryption, stronger local auth, and an audit UI.

**Backend**
- Schema v13: vault keys, secret findings, redactions, security preferences.
- Secret scanner for common tokens, keys, passwords, private keys, and
  engagement-specific patterns; local-only, cancellable, deterministic.
- Redaction engine shared by reports, exports, search results, and preview.
- Optional encrypted vault: passphrase-derived key, authenticated encryption,
  encrypted blob store, lock/unlock, rotation, and recovery guidance. Implemented
  behind an optional extra; core stays dependency-free.
- Harden local auth: token rotation, origin/host validation, CSRF defenses, rate
  limits, CSP nonces if needed, secure headers for downloads.
- Audit log query/export, failed-auth history, redaction audit, security health
  checks; CLI security commands.

**Frontend**
- Security center: scan, findings list with context, bulk redaction, ignore/allow
  with reason, re-scan, and export-safe preview.
- Lock screen / unlock flow with clear recovery warnings.
- Audit viewer with filters and export.
- Inline secret warnings in editor/preview and report redaction status.
- Security settings with safe defaults and explicit destructive confirmations.

**Tests**
- Secret-pattern precision/recall fixtures, redaction leakage tests, encryption
  round-trip, wrong-passphrase, rotation, lock state, audit retention, auth/rate
  limit, CSP/header tests, frontend redaction flow.

**LOC budget:** BE 2,250 · FE 1,400 · T 750 · **code total 4,400** · docs 220

**Exit:** a seeded vault with fabricated secrets scans, redacts, exports, and
passes a leakage test suite; encrypted vaults unlock correctly and fail safely;
core install remains dependency-free.

**Stretch:** per-field encryption, secure clipboard expiry, OS keyring unlock.

---

### B10 — `dev/v2-10-a11y-i18n-themes`

**Mission:** make every surface accessible, localizable, RTL-ready, themed, and
keyboard-remappable without compromising the Aurora identity.

**Backend**
- Schema v14: UI preferences, keybindings, themes, locales.
- Preferences API with validation, migration, export/import, and defaults.
- Locale metadata and fallback chain; no remote translation fetch.
- Theme tokens persisted as data with safe validation; no arbitrary CSS injection.

**Frontend**
- i18n runtime: message catalogs, pluralization, number/date formatting, locale
  switcher, missing-key diagnostics, English baseline and RTL locale scaffold.
- Convert layout CSS to logical properties; test RTL for shell, tree, editor,
  tables, modals, toasts, and graph.
- WCAG 2.2 AA audit and fixes: focus-visible, target sizes, motion, contrast,
  announcements, error identification, list/grid semantics, reduced motion.
- Keybinding editor with conflict detection, reset, and printable cheat sheet.
- Theme studio: token presets, live preview, import/export, contrast validation,
  dark/light/high-contrast.
- Accessibility test helpers and a manual QA matrix.

**Tests**
- Locale/plural formatting, RTL unit checks, keybinding conflict resolution,
  theme token validation/contrast, screen-reader announcements, focus management,
  keyboard-only flows, and visual regression-style snapshots where practical.

**LOC budget:** BE 750 · FE 2,600 · T 850 · **code total 4,200** · docs 220

**Exit:** every v2 workflow is keyboard-only and screen-reader-labelled; an RTL
locale renders correctly; theme studio cannot produce unreadable combinations;
all UI strings are externalized.

**Stretch:** additional locale packs, color-blind simulation preview, voice
control labels.

---

### B11 — `dev/v2-11-performance-offline`

**Mission:** make the workbench fast at scale, offline-capable, and polished as a
desktop application, then cut the v2 release.

**Backend**
- Schema v15: performance cache, offline manifests, startup samples.
- Server improvements: compressed static assets, cache validators, streaming
  downloads, request coalescing for read-heavy routes, and benchmark scripts.
- Offline manifest generation and verification; versioned asset hashes.
- Desktop integration: native window state, single-instance, deep links to
  notes/findings, menu wiring, and graceful webview fallback.
- Release tooling: version bump, changelog, wheel/source build, signed artifact
  checksum, smoke install.

**Frontend**
- Virtualized tree, findings, evidence, and search results; memoized selectors.
- Web worker for fuzzy search/graph layout; incremental rendering and idle work.
- PWA/service worker for offline shell and cached static assets; no data sync.
- Route-level code splitting (if compatible with esbuild setup), bundle budgets,
  and startup instrumentation without telemetry.
- Large-vault UX: skeletons, progressive loading, cancellation, and backpressure.
- Final accessibility/performance polish, print checks, and release QA.

**Tests**
- 20k-note/10k-finding/5k-blob benchmark fixtures, tree/search virtualization
  logic, worker message protocol, offline manifest integrity, service worker
  cache tests where feasible, startup benchmark thresholds, packaging smoke,
  desktop fallback tests.

**LOC budget:** BE 950 · FE 2,400 · T 850 · **code total 4,200** · docs 200

**Exit:** benchmark vault meets the budgets in §4.4; app boots offline; wheel and
source installs pass; v2 release checklist is complete.

**Stretch:** incremental static asset compression, background index rebuild,
crash-safe editor recovery snapshots.

---

## 7. Budget summary

| Branch | BE | FE | Tests | Code total | Docs | Floor |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| B00 platform kernel | 1,350 | 1,950 | 900 | **4,200** | 250 | ✅ |
| B01 engagement core | 1,950 | 2,000 | 700 | **4,650** | 180 | ✅ |
| B02 evidence vault | 1,650 | 1,950 | 750 | **4,350** | 160 | ✅ |
| B03 block editor | 1,300 | 2,350 | 700 | **4,350** | 160 | ✅ |
| B04 search/commands | 1,450 | 2,050 | 700 | **4,200** | 150 | ✅ |
| B05 playbooks/snippets | 1,550 | 1,950 | 700 | **4,200** | 160 | ✅ |
| B06 graph/intel | 1,750 | 1,850 | 700 | **4,300** | 150 | ✅ |
| B07 reporting studio | 2,050 | 1,950 | 700 | **4,700** | 180 | ✅ |
| B08 sync/portability | 2,250 | 1,300 | 750 | **4,300** | 200 | ✅ |
| B09 security/privacy | 2,250 | 1,400 | 750 | **4,400** | 220 | ✅ |
| B10 a11y/i18n/themes | 750 | 2,600 | 850 | **4,200** | 220 | ✅ |
| B11 performance/offline | 950 | 2,400 | 850 | **4,200** | 200 | ✅ |
| **Total** | **19,250** | **23,850** | **9,150** | **52,050** | **2,230** | 12/12 |

These are implementation targets, not permission to pad. If a branch's honest
scope falls short, pull in its listed stretch items; if it still falls short,
merge it into its nearest dependency rather than adding filler.

---

## 8. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Branch train becomes a 12-step rebase nightmare | High | Contract-first B00, reserved migrations/namespaces, merge numeric order, short-lived parallel waves |
| 4,000-line floor encourages dead code | High | LOC gate plus review; floors include tests; no generated files; stretch scope is real product work |
| Schema evolution breaks existing vaults | High | Append-only migrations, fixture vaults for v1/v2/v3, upgrade tests, newer-version rejection |
| API v2 drifts from v1 | High | Compatibility adapter, contract tests against both layers, deprecation only at v3 |
| Encryption crypto misuse | High | Optional extra, vetted library, test vectors, lockout/recovery tests, external review |
| Blob store path/hash bugs | High | Atomic writes, content-addressed names, traversal tests, hash verification, GC dry-run |
| Report export leaks secrets | Critical | Shared redaction pipeline, leakage fixtures, mandatory redaction check before export |
| UI complexity outgrows maintainability | Medium | Feature folders, primitive extraction, monolith size warnings, per-feature ownership |
| Accessibility deferred again | Medium | B10 is a release gate, not a follow-up; new UI checked in every branch |
| Large vault performance regresses | Medium | Benchmarks from B00 onward; budgets enforced in B11 |
| Local dirty work lost during rescue | Medium | Preserve on `wip/aurora-editor-a11y` before fast-forward; salvage by cherry-pick |
| Stale branches confuse contributors | Low | B00 triage table, delete after salvage, documented branch playbook |

---

## 9. Release definition for v2

v2 ships only when:

1. B00–B11 are merged through the full gate and the branch train is clean.
2. All existing v1 workflows still work through the v2 frontend and v1 API adapter.
3. A complete engagement (scope → target → finding → evidence → redacted report)
   round-trips through export/import and verifies.
4. The security leakage suite passes and the optional encrypted vault is documented.
5. Accessibility, RTL, high-contrast, reduced-motion, and keyboard-only QA pass.
6. Performance budgets pass on the seeded large vault.
7. Wheel, source, and desktop/webview smoke installs pass on the CI matrix.
8. Documentation, changelog, migration guide, and recovery guide are complete.

---

## 10. Immediate next actions

1. Create `wip/aurora-editor-a11y` from the dirty tree and commit it; do not lose
   the untracked editor/accessibility files (they are inputs to B03/B10).
2. Fast-forward `main` to `origin/main` and verify a clean checkout in a fresh
   virtualenv: `pip install -e ".[dev]"`, then the full Python and frontend gates.
3. Triage the branch list (§5.3): salvage, then delete stale `aurora-*`/`auto-*`
   branches.
4. Open `dev/v2-00-platform-kernel`; implement the migration framework, API v2
   router, app shell/router, design primitives, LOC gate, and CI updates.
5. Land B00 through a PR; do not start feature branches on red gates.
6. Start Wave 1 in parallel after B00: B01, B03, and the reversible initial part
   of B09.
7. At each merge, re-measure LOC with the gate and update the changelog/branch log.

---

## Appendix A — Branch PR checklist

- [ ] Branch is based on current `main` and rebased if needed.
- [ ] Scope matches the branch spec; no unrelated features.
- [ ] Schema migration reserved version only; upgrade tests for all prior versions.
- [ ] New API routes namespaced, paginated where applicable, contract-tested.
- [ ] v1 compatibility preserved.
- [ ] Frontend routes/components/hooks/styles live under the feature folder.
- [ ] Keyboard, screen reader, focus, dark/light/high-contrast, reduced motion,
      mobile/RTL checked.
- [ ] Tests added for rule branches and failure paths; no flaky timing tests.
- [ ] Docs and changelog updated; generated bundle rebuilt.
- [ ] LOC gate: added ≥4,000, test additions ≥500, generated files excluded.
- [ ] No secrets, no telemetry, no remote calls, no new core runtime dependency.
- [ ] PR description includes files, tests run, LOC count, known gaps.

## Appendix B — Command reference

```bash
# Python
python -m ruff check .
python -m ruff format --check .
python -m mypy src
python -m pytest

# Frontend
cd frontend
npm test
npm run typecheck
npm run format:check
npm run build

# Packaging
python -m build
python scripts/smoke_web.py

# LOC gate (requires scripts/loc_gate.py from B00)
python scripts/loc_gate.py --base origin/main --min-added 4000 --min-tests 500
```

## Appendix C — Baseline rescue commands

```bash
# Preserve the dirty tree before syncing
git switch -c wip/aurora-editor-a11y
git add -A
git commit -m "wip: preserve aurora editor engine and accessibility work"

# Sync main (local main is an ancestor of origin/main)
git switch main
git merge --ff-only origin/main

# Create the foundation branch
git switch -c dev/v2-00-platform-kernel
```

Do not push `main`, force-push shared branches, or merge a feature branch whose
LOC gate or full quality gate is red.
