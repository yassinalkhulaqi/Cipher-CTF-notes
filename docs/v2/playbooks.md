# Playbooks, Snippets, and Templates V2

The playbooks feature is an additive V2 capability. It stores structured,
human-reviewed workflows and provides dry-run planning, checklist tracking,
snippet composition, template rendering, recommendations, and portable export
bundles. It never executes commands itself.

## Scope

The feature is split into three layers:

- `redscribe.v2.playbooks` owns domain types, repositories, validation,
  execution state, import/export, and recommendation scoring.
- `redscribe.ui.web.v2.namespaces.playbooks` exposes 50 additive API v2 routes
  through the registry's `_register` hook.
- `frontend/src/features/playbooks` provides the browser UI, mounted through
  the feature's own export surface so the shared shell remains unchanged.

Curated data is loaded from the established snippet catalog and from eight
built-in playbooks covering web, host, CTF, Active Directory, API, forensics,
handoff, and incident response work.

## Domain model

A playbook is a versioned directed acyclic graph of steps. Each step has a
stable id, optional command template, optional snippet reference, checklist
items, preconditions, variables, dependencies, and timing metadata.

Variables are declared once per playbook. They support text, number, boolean,
choice, secret, and list kinds, defaults, validation ranges, and patterns.
Resolution fills missing values from the run target and validates supplied
values before interpolation.

Conditions use a small expression language. Supported operators include
equality, inequality, containment, membership, regular expression matching,
existence, and numeric or lexical ordering. Filters such as `upper`, `lower`,
`join`, `default`, and `coalesce` are available during interpolation.

Checklist items carry their own state and can be gated by conditions. A run
tracker records pending, ready, running, done, skipped, blocked, and failed
states, notes, and an append-only event log.

## Planning and execution state

`PlaybookEngine.plan` produces a deterministic `RunPlan` containing DAG order,
parallel layers, interpolated commands, visible checklist items, unresolved
variables, and diagnostics. The preview renderer turns the plan into Markdown
for operator review.

Run state transitions are explicit: `planned` → `running` → `paused` /
`completed` / `failed` / `cancelled`. Step results update values, context,
checklist state, and the next ready step. Completion occurs only when every
planned step has settled.

## Snippets

Snippet records wrap reusable commands with keys, titles, tags, libraries,
usage counts, and version metadata. The snippet library supports search,
atomic replacement, usage tracking, and safe composition through
`{{snippet:key}}` references. Composition detects missing references and
cycles before rendering.

## Templates

Templates are versioned Markdown or text records with declared variables.
The template engine registers, renders, validates, and tracks history for each
record. Three playbook-specific templates are included:

- `playbook-run` for run handoff notes
- `step-log` for individual step records
- `checklist-summary` for checklist reporting

## Import and export

`build_bundle` creates a deterministic JSON bundle with a manifest and SHA-256
checksum. `import_bundle` validates kind, schema version, sections, manifest
counts, and checksum before applying one of three duplicate strategies:

- `skip` records conflicts and keeps existing records
- `replace` overwrites matching keys
- `rename` creates unique `-import-N` keys

Future schema versions are rejected; older compatible versions produce
warnings. Runs are restored independently and invalid run snapshots are
skipped with warnings.

## Recommendations

The recommendation engine scores playbooks, snippets, and templates from
local signals only: query terms, tags, category, recent use, status, and
snippet usage counts. Results are deterministic and include a human-readable
reason. Target strings can be converted into context tags for web, host, and
CTF work.

## API surface

The namespace registers 50 routes across six groups:

- `playbooks.*` for list, detail, CRUD, validation, graphs, recommendations,
  statistics, options, export, import, and reset
- `steps.*` for add, update, remove, move, link, unlink, and checklist editing
- `variables.*` for add, remove, and resolve
- `snippets.*` for list, detail, CRUD, use, compose, and statistics
- `templates.*` for list, detail, render, history, register, and delete
- `runs.*` for plan, preview, start, detail, list, next, advance, cancel,
  progress, checklist, and checklist updates

All routes use the V2 request envelope and return `RouteResult` values with
ETags, cursor pagination for lists, and stable error codes. Domain errors are
mapped to V2 errors: not-found variants become `not_found`, duplicate keys and
invalid state become `conflict`, and validation failures become
`invalid_request`.

## Safety notes

Commands are stored and rendered as text for copying. There is no shell
execution, network calls, or automatic evidence collection. Secrets are
supported as a variable kind but are never logged by the domain layer.

The feature is registered additively. Shared V2 route tables, transport code,
storage migrations, and the application shell are not modified.
