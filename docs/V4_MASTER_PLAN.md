# RedScribe v4 — Master Plan

**Status:** Approved for execution
**Owner:** RedScribe contributors
**Date:** 2026-11-26
**Supersedes (as the active program):** `docs/V3_MASTER_PLAN.md` (kept as history)
**Baseline (`V4_BASELINE`):** `c2123b9ab6de4e6a28450bc40abf5edaccb1d42a` (tip of `main` at program start)
**Delivery model:** 11 branches — `dev/v4-00` (foundation) plus `dev/v4-01` … `dev/v4-10` (ten feature slices).
**LOC contract:** every delivery branch adds **≥ 2,500 net lines** against `V4_BASELINE`; the program adds **≥ 25,000 net lines** in total.
**Planning branch:** `dev/v4-master-plan` (this document; not a delivery branch).

---

## 1. Why v4

V2 built the structures, V3 unified them into a coherent workbench. V4 makes
RedScribe the **best-in-class local security research notebook**: it closes the
remaining gaps between "a tool that has features" and "a product that feels
complete" — a universal capture inbox, first-class CVSS v4 findings, a real
evidence lab, a pro block editor, a structured query language, real playbook
automation, a visual report designer, a graph workbench, an end-to-end encrypted
vault, and a unified accessible/i18n design system.

Repository state at planning time:

| Area | State |
| --- | --- |
| Backend | `src/redscribe/v2/*` and `src/redscribe/v3/*` feature packages, plus legacy `domain/`, `services/`, `storage/`, `content/`, `ui/web/` |
| Frontend | `frontend/src/features/*` (20+ slices), `ui/`, `motion/`, `styles/` |
| Python tests | `tests/` plus `tests/v2_*`, `tests/v3_*` packages; 200+ passing tests |
| Frontend tests | `node --test` suites aggregated by `frontend/scripts/test.mjs` with per-branch `test-suites/*.json` manifests |
| Tooling | `scripts/loc_gate.py`, `scripts/branch_report.py`, `scripts/smoke_web.py`; ruff + mypy strict + pytest |
| Docs | `docs/V2_*`, `docs/V3_*`, `QUALITY_GATES.md`, `BRANCH_PLAYBOOK.md` |

## 2. Non-negotiables

1. **Local-first.** No accounts, no telemetry, no remote fetches, no external assets. Every feature works offline.
2. **No code execution.** Snippets, playbooks, macros, and extensions are data, never executed shell.
3. **Zero required runtime dependencies.** Core stays stock Python 3.10+.
4. **Strict gates on every branch.** ruff, format, mypy strict, pytest, frontend test, format check, typecheck, build, LOC gate. No skips, no weakened tests.
5. **Only `dev/*` is pushed.** Never push `main`, never force-push a shared branch.
6. **Additive registries.** New features add their own files; no branch rewrites a shared generated file.
7. **Depth over padding.** LOC is earned with typed models, services, tests, and real UI — never duplicated code or filler.

## 3. Baseline and hygiene (done)

```bash
git rev-parse HEAD > /tmp/opencode/v4-baseline.txt   # V4_BASELINE
git status --porcelain                               # clean
git switch -c dev/v4-master-plan                     # this branch
```

All LOC measurements use `V4_BASELINE`, never a moving `origin/main`.

## 4. Branch table

| Branch | Slug | Scope | LOC target | Frontend / UX / design deliverable | Depends on |
| --- | --- | --- | ---: | --- | ---: |
| B00 | `dev/v4-00-platform-kernel` | Architecture docs, v4 contracts, quality gates, LOC tooling, design tokens v4, API v4 envelope skeleton | 2,500 | Design tokens v4, density modes, v4 API client, shell routes, primitive upgrades | — |
| B01 | `dev/v4-01-capture-inbox` | Universal capture, parsers, triage queue, templates | 2,500 | Inbox panel, quick-capture UX, triage keyboard flow, inbox styling | B00 |
| B02 | `dev/v4-02-finding-cvss-v4` | Finding lifecycle, CVSS v4 scoring, remediation/retest | 2,500 | Finding studio, score gauge, remediation timeline, status chips | B00 |
| B03 | `dev/v4-03-evidence-lab` | Binary inspection, hex/strings, hashing, custody graph | 2,500 | Evidence lab, hex viewer, custody timeline, lab theming | B00, B02 |
| B04 | `dev/v4-04-block-editor-pro` | Block model, markdown round-trip, diff, autosave | 2,500 | Pro editor, slash menu, find/replace, diff gutter, editor focus mode | B00 |
| B05 | `dev/v4-05-query-language` | Structured query language, facets, saved searches, clustering | 2,500 | Query bar, facet sidebar, result clusters, saved-search chips | B00 |
| B06 | `dev/v4-06-playbook-automation` | DAG execution, dry-run trace, schedules, parameterized runs | 2,500 | DAG canvas, dry-run trace viewer, schedule editor, run history UX | B00 |
| B07 | `dev/v4-07-report-designer` | Page layouts, themes, WYSIWYG pagination, export | 2,500 | Page designer, zoom modes, theme-aware print preview, cover/toc editor | B00, B02 |
| B08 | `dev/v4-08-graph-workbench` | Entity graph, link analysis, layout, styling | 2,500 | Graph canvas, relationship styling, filter rail, inspector panel | B00, B03 |
| B09 | `dev/v4-09-security-vault` | Encryption at rest, key rotation, recovery, redaction | 2,500 | Security posture dashboard, key/recovery UX, privacy modes | B00 |
| B10 | `dev/v4-10-a11y-i18n-polish` | Accessibility, i18n, themes, motion, onboarding, release polish | 2,500 | Focus system, RTL layouts, motion unification, onboarding, empty states | B00 |

**Merge order.** Branches are cut from `V4_BASELINE` and delivered independently;
integrate in numeric order (B00 first). Each branch's shared files are additive,
so merges stay conflict-free.

## 5. Foundation contracts (B00) — build first

- **Schema v6 (append-only):** migration chain v5 → v6 with new tables for inbox items, CVSS v4 assessments, evidence inspection results, query definitions, DAG runs, report layouts, graph filters, key metadata, and a11y/i18n preferences. Tested against fresh v4, v5, v6 vaults plus downgrade refusal.
- **API v4 envelope:** `{ data, meta: { request_id, page, etag, version } }` and `{ error: { code, message, details } }` under `/api/v4/*`. Keeps v1/v2/v3 adapters green.
- **Event bus v4:** typed `DomainEvent` dataclasses, synchronous in-process bus, durable outbox, subscription registry, replay, redaction hooks.
- **Universal entity model v4:** `EntityId`, `EntityKind`, `EntityRef`, `EntityLink`, resolver registry.
- **Conflict-resistant registries:** dynamic Python namespace discovery; frontend test manifests `v4-*.json`; per-feature CSS files; API route registry; design-token registry.
- **Gate tooling:** `scripts/loc_gate.py --min-net 2500 --program-min-net 25000 --aggregate`; `scripts/branch_report.py` rollup; seed test proving a 2,499-net branch is rejected.
- **Design system v4:** `frontend/src/styles/tokens-v4.css`, `docs/DESIGN_SYSTEM_V4.md`, density modes, focus rings, semantic colors.

## 6. Branch briefs (shape: Intent · Backend · Frontend/UX/design · Tests · Docs)

### B00 — `dev/v4-00-platform-kernel`
Establish every shared seam, gate, and baseline so ten branches can work in parallel without collisions. Backend: schema v6, API v4 envelope, event bus v4, universal entity model, capability flags. Frontend: tokens v4, v4 API client, routing shell. Tests: migration up/down-refusal, envelope contracts, event replay/redaction, LOC gate seed rejection, token/primitive tests via manifest `v4-00.json`. Docs: `V4_ARCHITECTURE.md`, `API_V4.md`, `DESIGN_SYSTEM_V4.md`, `V4_BRANCH_PLAYBOOK.md`, updated `QUALITY_GATES.md`.

### B01 — `dev/v4-01-capture-inbox`
Intent: one frictionless inbox for raw notes, links, snippets, and flags. Backend: `v4/inbox/` capture parser, source classifiers, template engine, triage state machine, dedupe. Frontend: inbox panel, quick-capture bar, keyboard triage, styling. Tests: parser/classifier/template/dedupe/state-machine. Docs: `docs/v4/inbox.md`.

### B02 — `dev/v4-02-finding-cvss-v4`
Intent: a first-class finding lifecycle with CVSS v4. Backend: `v4/findings_v4/` CVSS v4 base/threat/environmental/supplemental metrics, score calculator, lifecycle state machine, remediation/retest tracking. Frontend: finding studio, score gauge, remediation timeline, status chips. Tests: score vectors, state transitions, retest logic. Docs: `docs/v4/findings.md`.

### B03 — `dev/v4-03-evidence-lab`
Intent: turn evidence metadata into an inspection lab. Backend: `v4/evidence_lab/` binary inspector, hex/strings extraction, hash verification, custody graph, bundle diff. Frontend: evidence lab, hex viewer, custody timeline, lab theming. Tests: hex dump, string extraction, hash chains, diff. Docs: `docs/v4/evidence-lab.md`.

### B04 — `dev/v4-04-block-editor-pro`
Intent: a professional block editor with safe round-tripping. Backend: `v4/blocks_pro/` block model, markdown serializer/parser, diff engine, autosave snapshots, validation. Frontend: pro editor, slash menu, find/replace, diff gutter, focus mode. Tests: round-trip, diff, snapshot pruning. Docs: `docs/v4/editor.md`.

### B05 — `dev/v4-05-query-language`
Intent: structured search beyond plain text. Backend: `v4/query/` query parser (fields, operators, booleans), facet engine, saved searches, result clustering. Frontend: query bar, facet sidebar, cluster cards, saved-search chips. Tests: parser grammar, facet counts, clustering. Docs: `docs/v4/query.md`.

### B06 — `dev/v4-06-playbook-automation`
Intent: real automation as data. Backend: `v4/automation_v4/` DAG model, topological executor, dry-run trace, schedules, parameterized runs, run records. Frontend: DAG canvas, dry-run trace viewer, schedule editor, run history. Tests: DAG validation, execution order, dry-run, recurrence. Docs: `docs/v4/automation.md`.

### B07 — `dev/v4-07-report-designer`
Intent: visual, client-ready reports. Backend: `v4/report_designer/` page layouts, theme model, pagination engine, cover/toc/appendix builder, exporters. Frontend: page designer, zoom, theme-aware print preview, cover/toc editor. Tests: pagination, theme inheritance, export. Docs: `docs/v4/report-designer.md`.

### B08 — `dev/v4-08-graph-workbench`
Intent: understand relationships across the vault. Backend: `v4/graph_v4/` graph model, link analysis (degree, components, paths), layout strategies, filters. Frontend: graph canvas, relationship styling, filter rail, inspector. Tests: metrics, components, path finding, layout determinism. Docs: `docs/v4/graph.md`.

### B09 — `dev/v4-09-security-vault`
Intent: end-to-end local encryption. Backend: `v4/vault_security/` envelope encryption, key derivation, rotation, recovery codes, redaction, privacy modes. Frontend: posture dashboard, key/recovery UX, privacy modes. Tests: encrypt/decrypt round-trip, rotation, recovery, redaction. Docs: `docs/v4/security.md`.

### B10 — `dev/v4-10-a11y-i18n-polish`
Intent: make the product accessible and polished everywhere. Backend: `v4/a11y_i18n/` a11y audit rules, i18n catalogs, locale formatting, preference model, motion policy. Frontend: focus system, RTL layouts, motion unification, onboarding tour, empty states. Tests: audit rules, catalog completeness, locale formatting, motion policy. Docs: `docs/v4/a11y-i18n.md`.

## 7. Conflict-resistant registries

- **Python:** every v4 package is self-contained under `src/redscribe/v4/<slug>/`; no branch edits `src/redscribe/v4/__init__.py`. A single dynamic namespace initializer (shipped in B00) discovers submodules with `pkgutil.iter_modules`.
- **Frontend tests:** fixed base list plus per-branch `frontend/scripts/test-suites/v4-XX.json` manifests; `test.mjs` reads the union. No branch edits `test.mjs` or another branch's manifest.
- **CSS:** each feature owns `frontend/src/features/<slug>/<slug>.css`; no shared stylesheet is hand-edited.
- **Docs:** each feature owns `docs/v4/<slug>.md`; no branch edits another branch's doc.

## 8. Quality gates

```bash
python3 -m ruff check .
python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
cd frontend && npm test
cd frontend && npm run format:check
cd frontend && npm run typecheck
cd frontend && npm run build
python3 scripts/loc_gate.py --baseline V4_BASELINE --min-net 2500 --min-test-loc 400
```

Never disable a gate. If a gate is environment-blocked, record the exact command and failure and retry later.

## 9. Delivery workflow

1. Cut each `dev/v4-XX-*` branch from `V4_BASELINE` (worktree per branch).
2. Build implementation + tests + docs + frontend slice; run all gates.
3. Commit only intended files; do not stage `node_modules`, build outputs, or tool state.
4. Run the aggregate LOC gate across all ten branches with `--program-min-net 25000`.
5. Integrate `main` into feature branches, resolve conflicts with canonical universal files, rerun gates.
6. Push only `dev/*` branches (explicitly authorized by the engagement owner).

## 10. Acceptance

- Ten feature branches, each ≥ 2,500 net LOC; program ≥ 25,000 net LOC.
- All gates green on every branch.
- README upgraded; architecture/API/design docs added.
- Final report table: branch, commit, net LOC, tests, gate status, PR URL.
