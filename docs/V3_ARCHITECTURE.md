# RedScribe V3 Architecture

## 1. Purpose

V3 adds a universal entity/identity layer, a typed event stream, and a stable
API envelope on top of the V2 feature packages. It does not replace V2: V2
packages keep their behavior and their routes. V3 is an additive contract layer
that lets 15 independently developed branches share one vocabulary.

## 2. Layers

```
frontend/src/v3            V3 API client, registries, primitives, tokens
frontend/src/features/*    feature slices (one per branch)
        |
API v3 envelope + router   src/redscribe/v3/api
        |
domain services            src/redscribe/v3/{entities,events,findings,...}
        |
namespace registry         src/redscribe/v3/namespaces (dynamic discovery)
        |
storage / SQLite           existing src/redscribe/storage + schema v5
```

## 3. Universal contracts

### 3.1 Entities

`EntityId` is `kind:value`. `EntityRef` adds a display label. `EntityLink` is a
typed directed edge (contains, relates, evidences, derives, references,
duplicates, supersedes). `EntityRecord` is an immutable, versioned snapshot.
`EntityService` stores records and links in memory; branch services persist
snapshots through their own repositories.

`EntityKindRegistry` is additive and always returns a fallback spec, so a branch
can render a kind whose owning branch has not merged yet.

### 3.2 Events

`DomainEvent` is immutable and carries a subject `EntityId`, an actor, a
severity, and a JSON payload. `EventBus` records every event, dispatches to
kind-specific and wildcard subscribers, and isolates subscriber failures.
`OutboxWriter` persists events through `MemoryOutbox` or `JsonFileOutbox`.
`EventFilter`, `EventReplay`, and `RedactionPolicy` power the activity stream.

### 3.3 API v3

Every response is `{ data, meta }` or `{ error, meta }`. `meta` carries a request
ID, API version, optional ETag, pagination, and warnings. Errors use stable
codes from `V3ErrorCode` with a fixed status table. `PageRequest` uses signed
opaque cursors. `IdempotencyGuard` caches write results by key + payload
fingerprint. `V3Router` discovers namespace modules dynamically; no central
dispatch table is edited by feature branches.

### 3.4 Schema v5

Migration steps are append-only, named, checksummed, and idempotent
(`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`). The chain refuses
downgrades from a newer schema. All V3 tables are prefixed `v3_`.

### 3.5 Capabilities and configuration

`Capabilities` gates optional features at runtime. `V3Config` is immutable and
carries pagination, rate-limit, redaction, offline-only, and capability flags.

## 4. Conflict strategy

- Python namespaces are discovered with `pkgutil.iter_modules`; later branches
  add a module file, not an import line.
- Frontend tests are listed in `frontend/scripts/test-suites/NN.json`;
  `test.mjs` reads the union. No branch edits the base list.
- CSS lives per feature (`frontend/src/features/<name>/<name>.css`) and tokens
  live in `frontend/src/styles/tokens-v3.css`; generated bundles are rebuilt.
- API routes, migrations, entity kinds, and design tokens register as data.

## 5. Offline and security invariants

No runtime dependencies, no telemetry, no remote requests, no external assets.
Playbooks and extensions are data only; the app never executes user commands.
Event payloads are redacted before display or export. Secrets never appear in
logs or error envelopes.
