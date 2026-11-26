# RedScribe v4 Architecture

**Status:** current for the v4 program
**Baseline:** `V4_BASELINE` = `c2123b9`

## 1. Purpose

v4 adds ten feature slices to RedScribe without turning the repository into a
merge battlefield. The architecture is defined by three rules:

1. **One vocabulary.** `redscribe.v4.contracts` owns entities, envelopes, errors,
   and capabilities. No feature invents its own id or error format.
2. **One event stream.** `redscribe.v4.events` owns `DomainEvent` and the outbox.
   Features emit; they never write ad-hoc audit logs.
3. **Additive registration.** Features add files. They never edit a shared
   generated registry.

## 2. Layers

```
┌─────────────────────────────────────────────────────────────┐
│  frontend/src/features/<slug>/   React/Zustand UI + CSS     │
├─────────────────────────────────────────────────────────────┤
│  frontend/src/features/v4-kernel/ client · routes · shell   │
├─────────────────────────────────────────────────────────────┤
│  /api/v4/*   envelope router (contracts.PageMeta, ApiError) │
├─────────────────────────────────────────────────────────────┤
│  src/redscribe/v4/<slug>/   models · service · storage · api │
├─────────────────────────────────────────────────────────────┤
│  v4 contracts · events · migrations_v4 · pagination         │
├─────────────────────────────────────────────────────────────┤
│  SQLite vault (schema v6, append-only migration chain)      │
└─────────────────────────────────────────────────────────────┘
```

## 3. Foundation modules (B00)

| Module | Responsibility |
| --- | --- |
| `v4/__init__.py` | Dynamic namespace discovery; `register_all(api)` |
| `v4/contracts.py` | `EntityId`/`EntityRef`/`EntityLink`, envelopes, errors, capabilities |
| `v4/events.py` | `DomainEvent`, `EventBus`, `InMemoryOutbox`, redaction |
| `v4/capabilities.py` | `FeatureFlag`, `FeatureGate`, requirement resolution |
| `v4/api_v4.py` | Additive route registry, `/api/v4/*` paths |
| `v4/migrations_v4.py` | Checksummed v5→v6 migration chain |
| `v4/pagination.py` | Opaque cursors, `PageResult`, weak ETags |
| `v4/preferences.py` | Theme/density/motion/locale model and store |
| `v4/clock.py` | Injectable clock for deterministic tests |

## 4. Feature package shape

Every feature follows the same layout so readers and tooling know where to look:

```
src/redscribe/v4/<slug>/
  __init__.py     package docstring and optional register(api)
  types.py        enums, dataclasses, validation
  service.py      domain operations (pure where possible)
  storage.py      SQLite adapters keyed by EntityRef
  api.py          route handlers returning v4 envelopes
tests/v4_<slug>/
  test_types.py
  test_service.py
  test_api.py
frontend/src/features/<slug>/
  <Slug>Panel.tsx
  client.ts
  state.ts
  <slug>.css
frontend/scripts/
  v4-<slug>.test.ts
frontend/scripts/test-suites/
  v4-XX.json
docs/v4/<slug>.md
```

## 5. Data flow

A write request enters `/api/v4/<slug>`, is validated against `v4.contracts`,
passes through `FeatureGate`, reaches `service.py`, persists via `storage.py`,
and emits a `DomainEvent` to the bus. The outbox applies `default_redactor`
before storing. Responses are wrapped in `ok(data, PageMeta)` or `fail(ApiError)`.

## 6. Safety properties

- **No code execution.** Playbooks, macros, queries, and extensions are data.
- **No network.** The client uses loopback only; no external assets.
- **No secret leakage.** Event payloads are redacted before persistence.
- **No downgrade.** `MigrationChain.refuse_downgrade` blocks older schemas.
- **No unstable pagination.** Cursors encode offset + sort key and are versioned.

## 7. Testing strategy

- Python: strict typing, unit tests per layer, migration round-trips, event replay.
- Frontend: `node --test` bundles built by esbuild, manifests select suites.
- LOC gate: net lines measured against `V4_BASELINE`, never a moving ref.
