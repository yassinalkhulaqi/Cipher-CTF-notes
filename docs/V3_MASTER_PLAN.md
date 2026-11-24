# RedScribe v3 — Master Plan

**Status:** Proposed — ready to execute
**Owner:** yassinalkhulaqi
**Date:** 2026-11-23
**Supersedes (as the active program):** `docs/V2_MASTER_PLAN.md` (kept as history)
**Baseline:** the merge base of `origin/main` and the tip of the last merged `dev/v2-*` branch — recorded as `V3_BASELINE` on day 0
**Delivery model:** 15 delivery branches (`dev/v3-00` … `dev/v3-14`), each ≥ 4,000 added code lines and ≥ 600 test lines, program total ≥ 30,000 net lines
**Planning branch:** `dev/v3-master-plan` (this document; not one of the 15 delivery branches)

---

## 1. Executive summary

### 1.1 Where the project stands

RedScribe is a local-first desktop notebook for CTFs, pentests, and security
research: a Python standard-library core, one SQLite vault, a loopback-only JSON
API, and a bundled React/Zustand frontend. The V2 program delivered the
structural work — API v2 contracts, schema v4, engagements, evidence, block
editor, search/commands, playbooks, graph, reporting, sync, security, and
a11y/i18n/themes — across `dev/v2-00` … `dev/v2-10`.

Repository state observed at planning time:

| Area | Observed state |
| --- | --- |
| Backend | `src/redscribe/v2/{engagements,evidence,blocks,search,playbooks,graph,reporting,sync,security,a11y}` plus legacy `domain/`, `services/`, `storage/`, `content/`, `ui/web/` |
| Frontend | `frontend/src/features/*` (11 feature slices), `frontend/src/ui/*` primitives, `frontend/src/motion/*`, `frontend/src/styles/*` |
| Python tests | `tests/` plus 10 `tests/v2_*` packages; ~218 passing tests reported in `CHANGELOG.md` |
| Frontend tests | `node --test` suites aggregated by `frontend/scripts/test.mjs`, with `frontend/scripts/test-suites/*.json` manifests |
| Tooling | `scripts/loc_gate.py`, `scripts/branch_report.py`, `scripts/smoke_web.py`; ruff + mypy strict + pytest coverage ≥ 85% |
| Gates doc | `docs/QUALITY_GATES.md`; branch rules in `docs/BRANCH_PLAYBOOK.md` |
| Branches | ~50 local and ~30 remote branches, including many `feat/aurora-*`, `auto/*`, and stale one-offs |
| Untracked work | `.autonomous/`, `.opencode/` deliberately untracked tool state; `wip/aurora-editor-a11y` holds rescued early work |

### 1.2 Why V3 exists

V2 built the *structures*. V3 makes them feel like one **powerful, coherent
workbench** and closes the gaps that remain:

1. **Feature slices are disconnected.** Eleven feature areas each have their own
   client, state, CSS, and vocabulary. There is no single command center, no
   unified activity stream, and no cross-feature navigation model.
2. **Findings are still thin.** There is no first-class finding lifecycle with
   CVSS v4, remediation tracking, retest state, or evidence-backed proof blocks.
3. **Evidence is metadata, not a lab.** Hashing and custody exist, but there is no
   binary inspection surface, no hex/strings view, no bundle diff, no chain-of-
   custody visualization.
4. **Reporting is export-centric.** There is no visual page designer, no reusable
   report themes, no live WYSIWYG pagination, no client-ready cover/toc/appendix
   workflow.
5. **Automation stops at checklists.** No real DAG execution, no dry-run with
   trace, no schedule/recurrence, no parameterized re-runs with captured output.
6. **Search is text-first.** No faceted query language, no saved facet sets, no
   result clustering, no cross-entity "pivot" navigation.
7. **Performance is unmeasured.** No large-vault benchmarks, no virtualization,
   no incremental index, no explicit budgets for 20k+ notes.
8. **Security is opt-in but not end-to-end.** Encryption primitives exist but are
   not wired to a full vault lifecycle, key rotation, or recovery workflow.
9. **No extensibility surface.** Everything is hard-wired; there is no stable local
   API/SDK or CLI scripting path for power users.
10. **Polish is fragmented.** Motion, themes, components, and onboarding were
    built in separate branches and never unified into a single design system v3.

### 1.3 V3 product statement

Turn RedScribe into a **single, keyboard-first, offline security research
cockpit**: every entity (note, target, finding, evidence, playbook, report) is
first-class, cross-linked, searchable, automatable, auditable, and reportable —
with a design system that finally feels like one product.

### 1.4 Non-negotiables

1. **Local-first.** No accounts, no telemetry, no remote fetches, no external
   assets. Every new feature works with the network unplugged.
2. **No code execution.** Snippets, playbooks, and extensions are data and
   checklists. The app never runs user-defined commands.
3. **Zero required runtime dependencies.** Optional extras only; core stays
   stock Python 3.10+.
4. **Strict gates on every branch.** ruff, format, mypy, pytest, frontend test,
   format check, typecheck, build, packaging smoke, LOC gate. No skips, no
   weakened tests, no generated-file edits to pass a gate.
5. **Only `dev/*` pushed.** Never push `main`, never force-push a shared branch.
6. **Additive registries.** Shared files are made conflict-resistant *before*
   branching (§7).
7. **Depth over padding.** LOC is earned with typed models, services, tests, and
   real UI — never duplicated code, comment blocks, or filler fixtures.

### 1.5 Non-goals for V3

- Team collaboration, cloud sync, hosted services, or multi-user accounts.
- Executing offensive tooling or arbitrary scripts inside the app.
- A general-purpose document suite or IDE.
- Third-party plugin code execution (a data-only extension contract is in scope).
- Rewriting V2 features for their own sake; V3 extends and integrates them.

---

## 2. Baseline and repository hygiene (day 0, before B00)

### 2.1 Capture and preserve

```bash
git fetch origin --prune
git rev-parse HEAD > /tmp/opencode/v3-baseline.txt          # V3_BASELINE
git status --porcelain                                      # confirm only tool state
git switch -c wip/v3-preflight                              # rescue anything dirty
git add -A && git commit -m "chore: preserve pre-v3 working state"
git switch main && git pull --ff-only origin main
```

Record `V3_BASELINE` in the plan and in `docs/V3_ARCHITECTURE.md`. All LOC
measurements in §6 use this ref, not a moving `origin/main`.

### 2.2 Branch triage

Keep `wip/*` rescue branches until their content is reachable from a V3 branch.
For the ~50 stale `feat/aurora-*`, `auto/*`, and one-off branches: inventory with
`git log --oneline <branch> ^V3_BASELINE`, cherry-pick anything unique onto its
owning V3 branch, then delete only after the content is reachable. This triage
is tracked in `docs/V3_BRANCH_PLAYBOOK.md` and is part of B00, not a silent
cleanup.

### 2.3 Remote policy

The server rejects pushes outside `dev/*`:

```text
BLOCKED: only dev/* branches may be pushed
```

Delivery branches are `dev/v3-NN-slug`. The plan lives on
`dev/v3-master-plan`. No `main`, no `feat/*`, no force-push.

---

## 3. The 15-branch program at a glance

Merge order is strictly numeric; each branch is based on the merged tip of its
predecessor. LOC targets are **net added lines** (additions − deletions) against
`V3_BASELINE`, and comfortably exceed the 2,000-per-branch / 25,000-program
floor.

| # | Branch | Theme | Net LOC target | Test LOC | Depends on |
| ---: | --- | --- | ---: | ---: | --- |
| 00 | `dev/v3-00-platform-kernel` | Schema v5, API v3, event bus, registries, gates, design tokens v3 | 4,500 | 900 | — |
| 01 | `dev/v3-01-command-center` | Unified command bar, navigation graph, focus sessions, workspace panes | 3,800 | 750 | 00 |
| 02 | `dev/v3-02-finding-studio` | Finding lifecycle, CVSS v4, remediation, retest, proof blocks | 4,200 | 850 | 01 |
| 03 | `dev/v3-03-evidence-lab` | Binary inspection, hex/strings, bundle diff, custody visualization | 3,900 | 800 | 02 |
| 04 | `dev/v3-04-graph-workbench` | Layout engine, clustering, relationship editor, graph export | 3,600 | 700 | 01, 02 |
| 05 | `dev/v3-05-search-intelligence` | Query language v2, facets, clustering, pivot navigation, saved facets | 3,700 | 750 | 01, 04 |
| 06 | `dev/v3-06-playbook-automation` | DAG engine, traced dry-run, variables, recurrence, run capture | 4,000 | 800 | 02, 05 |
| 07 | `dev/v3-07-report-designer` | Visual page designer, themes, pagination preview, cover/toc/appendix | 4,300 | 850 | 02, 03, 06 |
| 08 | `dev/v3-08-timeline-activity` | Event-sourced activity stream, filters, daily digest, retrospection | 2,800 | 600 | 00, 06 |
| 09 | `dev/v3-09-sync-portability-pro` | Encrypted bundles, version vectors, 3-way merge, conflict workbench | 3,600 | 750 | 03, 08 |
| 10 | `dev/v3-10-security-vault` | Vault encryption lifecycle, key rotation, recovery, policy engine | 4,100 | 850 | 09 |
| 11 | `dev/v3-11-performance-scale` | Virtualization, incremental index, worker offload, benchmark harness | 3,200 | 700 | 05, 09 |
| 12 | `dev/v3-12-a11y-i18n-refinement` | WCAG 2.2 AA/AAA audit fixes, RTL, locales, theme/motion unification | 3,000 | 650 | 01, 07 |
| 13 | `dev/v3-13-extensibility-cli` | Stable local API/SDK, scripting CLI, data-only extension manifests | 3,400 | 700 | 00, 11 |
| 14 | `dev/v3-14-polish-release` | Design system v3, onboarding, release docs, golden-path E2E, docs site | 3,500 | 700 | all |
| | **Total** | | **≈ 55,600** | **≈ 11,350** | |

> The explicit floor is **≥ 2,000 net LOC per branch** and **≥ 30,000 net LOC
> for the program**. The table's targets are higher on purpose so the floor is
> never at risk from a single quiet branch. Dependencies are additive: a branch
> requires all lower-numbered branches it relies on, merged in numeric order.

### 3.1 Frontend / UX / design distribution

Design work is deliberately spread across the train, not dumped into B14:

- B00 design tokens v3 and component contracts.
- B01 command center chrome, focus mode, pane chrome.
- B02 finding cards, severity rails, remediation panels.
- B03 hex viewer, evidence strip, custody timeline.
- B04 graph canvas interactions, cluster styling, inspector.
- B05 facet sidebar, result clustering, pivot chips.
- B06 DAG run view, trace timeline, variable injection UX.
- B07 page designer, zoom modes, theme-aware print preview.
- B08 activity density modes, digest cards.
- B09 conflict diff UI, bundle wizard.
- B10 security posture dashboard, key/recovery UX.
- B11 skeleton/virtualized states, performance HUD.
- B12 focus indicators, RTL layouts, motion/theme unification.
- B13 developer console, API explorer styling.
- B14 onboarding, empty states, release-quality polish.

---

## 4. Foundation contracts (B00) — build these first

Every later branch depends on these seams. They must be universal and additive
*before* the first feature branch is cut.

### 4.1 Schema v5 (append-only migration)

Extend `src/redscribe/storage/` with a migration chain from v4 → v5. New tables:
`entities` (universal entity index), `activity_events` (event-sourced stream),
`finding_lifecycle`, `run_records`, `report_layouts`, `key_metadata` (no key
material), `extension_manifests`. Every migration is checksummed and tested
against fresh v3, v4, and v5 vaults, plus a downgrade-refusal test.

### 4.2 API v3 envelope

Extend `src/redscribe/ui/web/v2/` with a `v3` namespace layer. Stable envelopes:
`{ data, meta: { request_id, page, etag, version } }` and
`{ error: { code, message, details } }`. Namespaced routes:
`/api/v3/{engagements,findings,evidence,graph,search,playbooks,reports,activity,sync,security,extensions,system}`.
Keep the v1/v2 adapters untouched and green. Add idempotency keys, cursor
pagination, ETag concurrency, and a request-ID middleware. Document all of it in
`docs/API_V3.md`.

### 4.3 Event bus

`src/redscribe/v3/events/`: typed `DomainEvent` dataclasses, an in-process
synchronous bus, durable outbox to `activity_events`, subscription registry,
replay API, and redaction hooks. Every later feature emits events through this
bus, never ad-hoc logging.

### 4.4 Universal entity model

`src/redscribe/v3/entities/`: `EntityId` (typed ULID-like), `EntityKind`,
`EntityRef`, `EntityLink`, and a resolver registry. This is what lets a finding
reference evidence, a report reference findings, and the graph reference
everything without per-feature foreign keys.

### 4.5 Conflict-resistant registries

See §7 — Python namespace discovery, frontend test manifests, CSS files,
migration registry, API route registry, design-token registry. B00 ships the
*universal* versions so no later branch has to edit them.

### 4.6 Gate tooling v3

Enhance `scripts/loc_gate.py` with `--baseline V3_BASELINE`,
`--min-net 2000`, `--min-test-loc 600`, `--program-min-net 30000`, and
`--aggregate` across all 15 branch refs. Enhance `scripts/branch_report.py` with
a per-branch and program rollup table. Add a seed test that proves a 1,999-net
branch is rejected. Never loosen the existing v2 gate to make a branch pass.

### 4.7 Design system v3 foundations

`frontend/src/styles/tokens-v3.css`, updated `frontend/src/ui/` primitives, and
`docs/DESIGN_SYSTEM_V3.md`: spacing scale, type scale, elevation, semantic
colors, focus rings, density modes, and component state contracts. Later
branches import tokens; they never redefine them.

---

## 5. Branch briefs

Each brief follows the same shape: **Intent · Backend · Frontend/UX/design ·
Contracts & tests · Docs · Exit criteria**.

### 5.1 B00 — `dev/v3-00-platform-kernel`

**Intent.** Establish every shared seam, tooling gate, and baseline measurement
so the next 14 branches can work in parallel without collisions.

**Backend.** Schema v5 migration chain; API v3 envelope + namespaced router;
`DomainEvent` bus and durable outbox; universal `EntityId`/`EntityRef`/link
registry; request-ID, ETag, idempotency, and cursor utilities; capability flags.

**Frontend/UX/design.** Design tokens v3, density modes, updated primitives,
a v3 API client with envelope decoding, and a routing shell that can host all
future feature routes.

**Contracts & tests.** Migration up/down-refusal tests; contract tests for every
envelope and error code; event replay/redaction tests; LOC gate seed-rejection
test; frontend token/primitive tests registered via manifest `00.json`.

**Docs.** `docs/V3_ARCHITECTURE.md`, `docs/API_V3.md`, `docs/DESIGN_SYSTEM_V3.md`,
`docs/V3_BRANCH_PLAYBOOK.md`, updated `docs/QUALITY_GATES.md`.

**Exit criteria.** Clean checkout green on all gates; v1/v2 routes unchanged;
LOC gate rejects a seeded 1,999-net branch; branch triage inventory recorded.

### 5.2 B01 — `dev/v3-01-command-center`

**Intent.** One keyboard-first entry point for every action, object, and place in
the app — replacing eleven disconnected command UIs with a single, extensible
command graph.

**Backend.** `src/redscribe/v3/commands/`: command registry (data-driven),
context resolver, command scoring, recent/frequent model, macro recorder
(stores command sequences as data, never shell), and permission/capability
checks.

**Frontend/UX/design.** Global command bar (`Ctrl+K`), grouped results, inline
argument forms, breadcrumb navigation, focus-session mode, and a multi-pane
workspace with resizable panes and per-pane context. New `CommandPaletteV3`,
`WorkspaceCanvas`, `FocusOverlay`, `PaneHeader` components.

**Contracts & tests.** Parser, scoring, macro round-trip, capability denial,
keyboard traversal, focus restore, pane state persistence.

**Docs.** `docs/v3/commands.md`, updated `docs/SHORTCUTS.md`.

**Exit criteria.** Any action reachable in ≤ 2 keystrokes from any pane; no
focus trap regressions; works fully offline.

### 5.3 B02 — `dev/v3-02-finding-studio`

**Intent.** Make findings first-class, lifecycle-aware, and evidence-backed.

**Backend.** `src/redscribe/v3/findings/`: immutable models, CVSS v4 base +
temporal + environmental scoring, severity bands, lifecycle state machine
(`draft → confirmed → remediated → retested → closed` with reopen), remediation
tracker, duplicate detection using existing `v2/engagements/duplicates.py`,
proof-block links to entities, and CWE/mapping metadata.

**Frontend/UX/design.** Finding cards with severity rails, CVSS v4 calculator
with vector builder and live score, remediation checklist, retest panel,
duplicate-suggestion UI, and keyboard-driven finding editor.

**Contracts & tests.** CVSS vectors against published examples, transition
legality, duplicate false-positive controls, proof-link integrity, API v3
pagination/ETag on finding lists.

**Docs.** `docs/v3/findings.md`, CVSS v4 scoring guidance.

**Exit criteria.** A finding can be created, duplicated, scored, evidenced,
remediated, retested, and closed entirely through the UI and API.

### 5.4 B03 — `dev/v3-03-evidence-lab`

**Intent.** Turn the evidence vault into an inspection lab with verifiable
binary provenance.

**Backend.** `src/redscribe/v3/evidence_lab/`: chunked hex dump generator,
printable-string extraction, entropy estimation, magic-byte classification,
multi-hash panel (SHA-256/BLAKE2b), bundle diff, chain-of-custody graph
builder, and thumbnail/attachment streaming with range support. All built on
the existing `v2/evidence` records and hashing.

**Frontend/UX/design.** Virtualized hex viewer with offset navigation and
selection, strings/entropy tabs, custody timeline visualization, evidence
comparison view, and a drag-and-drop ingest strip with integrity badges.

**Contracts & tests.** Hex/offset correctness, string extraction edge cases,
range request handling, custody graph cycles, large-file streaming memory bound.

**Docs.** `docs/v3/evidence-lab.md`.

**Exit criteria.** A 100 MB evidence file can be inspected without loading it
into memory; every displayed hash matches the stored record.

### 5.5 B04 — `dev/v3-04-graph-workbench`

**Intent.** Make the graph an analytical workbench, not just a visualization.

**Backend.** Extend `v2/graph` with `src/redscribe/v3/graph/`: pluggable layout
strategies (force, hierarchical, radial, timeline), clustering by tag/entity/
severity, shortest-path and cut-vertex analysis, relationship editor with undo,
graph snapshots/diffs, and DOT/JSON/Mermaid export.

**Frontend/UX/design.** Layout switcher, cluster chips, relationship editing
gestures, path explorer with step explanations, minimap, and inspector showing
entity metadata from the universal resolver.

**Contracts & tests.** Layout determinism with seeded RNG, clustering
correctness, path algorithms against fixtures, snapshot round-trip, export
validity.

**Docs.** `docs/v3/graph-workbench.md`.

**Exit criteria.** Any two entities can be connected, explained, and exported;
graph interactions stay under 100 ms at 5,000 nodes.

### 5.6 B05 — `dev/v3-05-search-intelligence`

**Intent.** A query language and result experience that pivots across every
entity type.

**Backend.** `src/redscribe/v3/search/`: query language v2 grammar
(`kind: tag: severity: status: before: has:link`), facet extraction, result
clustering, cross-entity pivot suggestions, saved facet sets, query templates,
and incremental index hooks (consumed by B11).

**Frontend/UX/design.** Facet sidebar with counts, cluster groups, pivot chips,
saved-search management, highlight/fragment rendering, and a query builder with
autocomplete and inline error help.

**Contracts & tests.** Grammar fuzzing, facet counts, pivot correctness, saved
query round-trip, ranking stability, index consistency after entity edits.

**Docs.** `docs/v3/search-v2.md`.

**Exit criteria.** A user can express a cross-entity query, save it, and pivot
from a result into the owning finding/evidence/report without losing context.

### 5.7 B06 — `dev/v3-06-playbook-automation`

**Intent.** Upgrade checklists into deterministic, inspectable automation of
*documentation and workflow* (never command execution).

**Backend.** `src/redscribe/v3/automation/`: DAG compiler with cycle detection,
step executor for data operations (create note/finding, attach evidence, render
section, emit event), variable resolution with typed inputs, traced dry-run
that records every would-be mutation, recurrence rules, run persistence in
`run_records`, and rollback via compensating events.

**Frontend/UX/design.** DAG editor with drag connections, variable form with
validation, dry-run trace timeline, run history with diff, recurrence picker,
and guided step runner with keyboard nav.

**Contracts & tests.** Cycle/validation rejection, variable interpolation,
dry-run purity (zero writes), recurrence expansion, rollback equivalence, run
replay determinism.

**Docs.** `docs/v3/automation.md`.

**Exit criteria.** A 20-step playbook can be dry-run, inspected step by step,
executed, and replayed with identical results.

### 5.8 B07 — `dev/v3-07-report-designer`

**Intent.** A visual report designer that produces client-ready deliverables.

**Backend.** `src/redscribe/v3/reports/`: layout document model, reusable report
themes, pagination engine, cover/TOC/appendix builders, finding/evidence
selection with stable inclusion rules, live redaction preview, and renderers for
HTML, Markdown, JSON, and print CSS. Builds on `v2/reporting`.

**Frontend/UX/design.** Page designer with drag sections, zoom/pagination
preview, theme picker, section visibility toggles, inline redaction controls,
and a print-ready preview that matches the export byte-for-byte in structure.

**Contracts & tests.** Pagination across fixtures, TOC anchors, inclusion
rules, redaction completeness, export determinism, theme isolation.

**Docs.** `docs/v3/report-designer.md`.

**Exit criteria.** A designed report exports with identical section order,
pagination, and redactions in HTML, Markdown, and print preview.

### 5.9 B08 — `dev/v3-08-timeline-activity`

**Intent.** Give the user a reliable memory of what happened and when.

**Backend.** `src/redscribe/v3/activity/`: event projections, filtering DSL,
daily/weekly digest aggregation, "since last visit" computation, retrospective
summaries, and privacy-aware redaction of sensitive event payloads. Consumes
the B00 event bus.

**Frontend/UX/design.** Activity stream with density modes, filter chips,
date grouping, digest cards, retrospective view, and jump-to-entity actions that
open the universal resolver target.

**Contracts & tests.** Projection correctness, filter DSL, digest boundaries
(timezone-safe), redaction of payloads, replay idempotency.

**Docs.** `docs/v3/activity.md`.

**Exit criteria.** Every meaningful mutation emits a visible, linkable activity
event; digests are deterministic for a fixed clock.

### 5.10 B09 — `dev/v3-09-sync-portability-pro`

**Intent.** Make vault movement safe, verifiable, and conflict-free.

**Backend.** `src/redscribe/v3/portability/`: encrypted portable bundles,
version-vector comparison, three-way merge for entity families, conflict
detection with reason codes, manifest verification, device identity, and a
conflict-resolution service that produces auditable decisions.

**Frontend/UX/design.** Bundle wizard with step indicators, dry-run preview,
conflict workbench with side-by-side diff and strategy choices, progress with
cancel/resume, and a verification receipt view.

**Contracts & tests.** Round-trip fidelity, version-vector ordering, three-way
merge cases, conflict reason codes, tamper detection, interrupted-transfer
resume.

**Docs.** `docs/v3/portability.md`.

**Exit criteria.** Two independently edited vaults can be merged with every
conflict explained and resolved without data loss.

### 5.11 B10 — `dev/v3-10-security-vault`

**Intent.** Make encryption, privacy, and audit a complete lifecycle rather than
a set of primitives.

**Backend.** `src/redscribe/v3/vault_security/`: at-rest vault encryption wiring,
key derivation and rotation, recovery codes, policy engine (secret patterns,
redaction defaults, consent gates), audit trail export, and a posture scorer
that reports gaps without exposing secrets.

**Frontend/UX/design.** Security posture dashboard, setup/rotation wizard,
recovery flow with confirmation, policy editor, audit viewer with filters, and
clear locked/unlocked states that never leak content.

**Contracts & tests.** Encrypt/decrypt round-trip, wrong-key refusal, rotation
preserves data, recovery code single-use, policy precedence, audit redaction,
no-secret-in-logs assertions.

**Docs.** `docs/v3/security-vault.md`, updated `SECURITY.md`.

**Exit criteria.** A fresh vault can be encrypted, locked, unlocked, rotated,
and recovered with documented, tested steps; no secret appears in logs or API
errors.

### 5.12 B11 — `dev/v3-11-performance-scale`

**Intent.** Prove and enforce performance at realistic research scale.

**Backend.** `src/redscribe/v3/performance/`: incremental index, batched event
flush, query plan instrumentation, worker-friendly pure functions, benchmark
harness and fixtures (20k notes, 10k findings, 5k evidence), and budget
assertions.

**Frontend/UX/design.** Virtualized tree/table/lists, skeleton states, a
performance HUD (frame time, index freshness), deferred rendering for the graph,
and interaction budgets documented in the design system.

**Contracts & tests.** Benchmark reproducibility, index consistency under
concurrent edits, virtualized list correctness, budget failures in CI.

**Docs.** `docs/v3/performance.md` with measured numbers, not estimates.

**Exit criteria.** Tree interaction < 100 ms, first search results < 150 ms,
and no full-vault load on startup at the 20k-note fixture.

### 5.13 B12 — `dev/v3-12-a11y-i18n-refinement`

**Intent.** Unify the accessibility, localization, theme, and motion work from
V2 into one verified experience.

**Backend.** Extend `v2/a11y`: WCAG 2.2 audit rules, contrast automation,
locale-aware formatting, RTL layout metadata, complete keyboard map export,
and preference synchronization across all V3 features.

**Frontend/UX/design.** Full keyboard pass on every V3 surface, screen-reader
labels, focus order fixes, RTL layouts for all panes, additional locale
catalogs, one unified theme/motion control, and reduced-motion behavior that
keeps all content usable.

**Contracts & tests.** Automated a11y assertions, contrast checks for new
surfaces, locale round-trips, RTL layout smoke, motion-mode equivalence.

**Docs.** `docs/v3/a11y-i18n.md`, updated `docs/ACCESSIBILITY.md`.

**Exit criteria.** No new surface fails the a11y audit; both themes and RTL pass
contrast and keyboard checks.

### 5.14 B13 — `dev/v3-13-extensibility-cli`

**Intent.** Give power users a stable, safe, local-only surface for automation.

**Backend.** `src/redscribe/v3/api_sdk/`: typed SDK over API v3, data-only
extension manifests (declares contributions, never code), capability
negotiation, and a scripting CLI with read-only-by-default commands and explicit
write opt-in.

**Frontend/UX/design.** In-app API explorer, manifest editor with validation,
developer console with request/response history, and consistent error display
for extension declarations.

**Contracts & tests.** SDK round-trips, manifest schema validation, capability
denial, CLI read-only enforcement, no arbitrary code path (static assertion
and review).

**Docs.** `docs/v3/extensibility.md`, CLI reference.

**Exit criteria.** A user can script a read-only workflow against a live local
vault and author a valid manifest without any code execution path.

### 5.15 B14 — `dev/v3-14-polish-release`

**Intent.** Ship one coherent, polished product.

**Backend.** Golden-path E2E fixtures, release smoke suite, docs generation,
changelog and migration notes, and final gate hardening.

**Frontend/UX/design.** Onboarding flow, empty and first-run states, design
system v3 applied everywhere, iconography/label consistency, animation audit,
responsive polish, and release screenshots.

**Contracts & tests.** Golden-path E2E covering capture → finding → evidence →
report → export → import → merge; full gate matrix on every branch ref.

**Docs.** `docs/v3/release.md`, updated `README.md`, `CHANGELOG.md`.

**Exit criteria.** All 15 branches green; full program LOC report produced;
final table delivered (§12).

---

## 6. Quality gates and enforcement

### 6.1 Commands (run on every branch before push)

```bash
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
python3 -m ruff check .
python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
cd frontend && npm ci && npm test && npm run format:check && npm run typecheck && npm run build
cd .. && python -m build && python scripts/smoke_web.py
python scripts/loc_gate.py --baseline V3_BASELINE --min-net 2000 --min-test-loc 600
python scripts/branch_report.py --baseline V3_BASELINE
```

`-p no:asyncio` is a local environment workaround; CI runs pytest normally.
The LOC gate compares **net LOC** (additions − deletions) using
`git diff --numstat V3_BASELINE..HEAD`, counting `.py/.ts/.tsx/.css/.mjs/.js/.jsx`
and excluding lockfiles, generated bundles, images, snapshots, and tool state.

### 6.2 Gate matrix

| Gate | B00 | B01–B13 | B14 |
| --- | --- | --- | --- |
| ruff check / format | ✓ | ✓ | ✓ |
| mypy strict | ✓ | ✓ | ✓ |
| pytest (+ new suites) | ✓ | ✓ | ✓ |
| coverage ≥ 85% | ✓ | ✓ | ✓ |
| frontend test / format / typecheck / build | ✓ | ✓ | ✓ |
| committed bundle freshness | ✓ | ✓ | ✓ |
| wheel + web smoke | ✓ | ✓ | ✓ |
| LOC net ≥ 2,000, test ≥ 600 | ✓ | ✓ | ✓ |
| golden-path E2E | — | — | ✓ |

### 6.3 Program aggregation

At the end, run:

```bash
python scripts/loc_gate.py --baseline V3_BASELINE --aggregate \
  --branches dev/v3-00-platform-kernel,... --program-min-net 30000
```

This must report ≥ 30,000 net LOC and per-branch ≥ 2,000 net LOC. If a gate is
environment-blocked, record the exact command and failure and rerun when the
environment recovers — never disable the gate.

---

## 7. Conflict-resistant shared files

These are implemented in B00 and reused unchanged by later branches.

### 7.1 Python namespace registration

`src/redscribe/v3/namespaces/__init__.py` discovers submodules with
`pkgutil.iter_modules(__path__)`, imports with `importlib.import_module()`, and
returns a real submodule first from `__getattr__`. `register_all(api)` calls
`register` on every discovered module that exposes it. `install_namespaces()`
is idempotent via a class-level flag. `__all__` is sorted (Ruff `RUF022`).
Later branches add a module file; they never edit the initializer.

### 7.2 Frontend test registration

Keep a fixed base test list containing only baseline-guaranteed tests. Each
branch adds `frontend/scripts/test-suites/NN.json`. `frontend/scripts/test.mjs`
reads all manifests, deduplicates, and runs the union. Do not scan every test
file in the checkout, because a branch may contain tests for features its
dependencies have not yet landed. `REDSCRIBE_SKIP_TYPECHECK=1` is a local triage
escape hatch only; CI always typechecks.

### 7.3 CSS and generated assets

Each feature owns `frontend/src/features/<name>/<name>.css`, imported through
its own component or a branch manifest. No branch hand-edits a shared generated
stylesheet. Resolve conflicts by keeping both imports and regenerating the
bundle with `frontend/scripts/build.mjs`. Never stage `node_modules` or caches.

### 7.4 Migrations, routes, and registries

Migrations are append-only and discovered by a registry. API v3 routes and
design tokens register by data, not by editing a central switch. Activity event
types, commands, entity kinds, and extension contributions all use additive
registries so an early branch can merge before later modules exist.

---

## 8. Worktrees and execution order

One worktree per delivery branch, predictable paths:

```bash
mkdir -p /tmp/opencode/v3wt
git worktree add -b dev/v3-01-command-center /tmp/opencode/v3wt/wt01 dev/v3-00-platform-kernel
# ... wt02 … wt14
```

Reuse dependencies via symlinks only when safe; never stage `node_modules`.
Execute B00 → B14 in order. Independent branches may be developed in parallel
in their worktrees, but **merge** in numeric order. Rebase each branch on the
merged predecessor before opening its PR.

---

## 9. Merge workflow and PR discipline

1. Fetch the latest integration branch (`dev/v3-(N-1)-*`).
2. Merge it into the feature branch.
3. Resolve shared-file conflicts with the canonical universal versions from §7.
4. Rerun the full gate matrix (§6).
5. Commit the merge, push the `dev/*` branch, open the PR.
6. If PRs merged before final fixes landed, open follow-up PRs from the updated
   branches. Never push `main`.
7. One branch, one theme; unrelated fixes get their own small PR.
8. Keep migrations append-only; document namespace reservations.

---

## 10. Risk register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Many stale branches hide unique work | Lost features | B00 triage inventory; cherry-pick before deletion; keep `wip/*` |
| Shared registry conflicts | Broken merges | Universal additive registries in B00 (§7) |
| LOC padding to hit targets | Low-quality code | Review + test-line floor + depth requirement; gate counts real code only |
| Encryption key loss | Data loss | Recovery codes, rotation tests, explicit warnings in B10 UX |
| Large-vault regressions | Sluggish app | B11 budgets enforced in CI; measured numbers in docs |
| A11y/RTL regressions late | Rework | Distribute design work per §3.1; B12 verification gate |
| Gate blocked by environment | Delayed delivery | Record exact command + failure; rerun; never skip |
| Scope creep into tooling execution | Security violation | Non-goals §1.5; static no-code-execution assertion in B13 |

---

## 11. Success criteria

- All 15 `dev/v3-*` branches pass the full gate matrix and are pushed.
- Program total ≥ 30,000 net LOC; each branch ≥ 2,000 net LOC.
- Full engagement workflow: capture → finding → evidence → automation → report →
  export → import → merge, entirely in-app.
- Every entity is reachable from command bar, search, graph, and activity.
- v1/v2 routes and workflows remain green throughout.
- Measured performance budgets met at the 20k-note fixture.
- No new surface fails a11y/contrast/theme checks.
- No telemetry, no remote calls, no code execution paths added.

---

## 12. Final report format

| Branch | Commit | Net LOC | Tests | Gates | PR |
| --- | --- | ---: | --- | --- | --- |
| `dev/v3-00-platform-kernel` | — | — | — | — | — |
| `dev/v3-01-command-center` | — | — | — | — | — |
| `dev/v3-02-finding-studio` | — | — | — | — | — |
| `dev/v3-03-evidence-lab` | — | — | — | — | — |
| `dev/v3-04-graph-workbench` | — | — | — | — | — |
| `dev/v3-05-search-intelligence` | — | — | — | — | — |
| `dev/v3-06-playbook-automation` | — | — | — | — | — |
| `dev/v3-07-report-designer` | — | — | — | — | — |
| `dev/v3-08-timeline-activity` | — | — | — | — | — |
| `dev/v3-09-sync-portability-pro` | — | — | — | — | — |
| `dev/v3-10-security-vault` | — | — | — | — | — |
| `dev/v3-11-performance-scale` | — | — | — | — | — |
| `dev/v3-12-a11y-i18n-refinement` | — | — | — | — | — |
| `dev/v3-13-extensibility-cli` | — | — | — | — | — |
| `dev/v3-14-polish-release` | — | — | — | — | — |

Then state: total program net LOC; whether the 2,000-per-branch and 30,000-total
targets were met; any environment-blocked gate with the exact command; and
whether follow-up PRs are needed after branch updates.
