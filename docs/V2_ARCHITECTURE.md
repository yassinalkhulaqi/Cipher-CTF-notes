# RedScribe V2 Architecture

RedScribe V2 is an additive evolution of the local-first application. The v1
SQLite vault, localhost HTTP API, and React frontend remain the production path
until each feature branch migrates a slice deliberately.

## Design principles

1. **Additive first.** New modules live beside existing ones; v1 callers must not
   change during B00.
2. **Contract before feature.** API shapes, error codes, pagination, and
   idempotency are defined once in `redscribe.ui.web.v2.contracts`.
3. **Storage owns durability.** Migrations, event journaling, and idempotency are
   SQLite-backed, not process-local.
4. **Frontend primitives are boring.** Shared UI components carry ARIA and
   keyboard behavior so feature branches only compose them.
5. **Every branch pays for itself.** LOC, tests, docs, and quality gates are
   enforced before a branch can merge.

## Backend layers

| Layer | Modules | Responsibility |
| --- | --- | --- |
| Storage core | `storage/db.py`, `storage/migrations/` | Schema versioning, migration registry, vault access |
| Storage support | `storage/events.py`, `storage/idempotency.py` | Entity journal, request audit, idempotent writes |
| Domain/API v1 | `ui/web/api.py` | Existing RPC dispatch and compatibility adapter |
| API v2 | `ui/web/v2/contracts.py`, `router.py`, `routes.py` | Envelopes, errors, pagination, routing, replay |
| Transport | `ui/web/server.py` | Localhost HTTP, security headers, JSON framing |
| Tooling | `scripts/loc_gate.py`, `scripts/branch_report.py` | Branch accounting and enforced budgets |

### Storage migration registry

`storage/migrations/__init__.py` freezes each migration as an immutable record
with a version, name, SQL, and checksum. `migrations_through(version)` returns a
validated ordered chain, so `Vault` never guesses the upgrade path. Schema v4
adds:

- `schema_migrations` — applied migration history.
- `entity_events` — append-only entity activity.
- `idempotency_keys` — stored request digests and responses.
- `request_audit` — route status, timing, and error codes.

All new tables are additive. A v3 vault upgrades without data rewriting.

### API v2 request flow

```text
client
  -> POST /api/v2/{namespace}/{action}
  -> ApiServer._do_post_v2
  -> Api.handle_v2
  -> V2Router.dispatch
       -> route lookup
       -> idempotency replay check
       -> ApiV2.invoke
       -> event + audit recording
  -> stable Envelope
```

`V2Router.dispatch` catches known errors and always returns an envelope, so HTTP
status and machine-readable error codes stay aligned. Mutating routes require a
stable `Idempotency-Key`; the replay body is canonical JSON, which makes raw HTTP
replays byte-for-byte identical.

### v1 compatibility

`Api.handle` keeps its existing dispatch table. A `v2:` prefixed call is unwrapped
and forwarded to `Api.handle_v2`; no v1 method names, payloads, or error strings
changed in B00. The frontend continues to call `lib/api.ts` until a feature
branch opts into `lib/apiClient.ts`.

## Frontend layers

| Area | Modules | Responsibility |
| --- | --- | --- |
| App shell | `app/AppShell.tsx`, `app/RouterProvider.tsx`, `app/routes.ts` | Additive shell, hash routing, route registry |
| UI kit | `ui/*.tsx`, `styles/ui.css` | Button, dialog, field, tabs, menu, toolbar, table, banner, toast, skeleton |
| API client | `lib/apiClient.ts` | v2 envelopes, request IDs, cancellation, retries, cursors |
| Commands | `lib/commands.ts` | Registry over palette actions and shortcuts |
| Existing app | `App.tsx`, `lib/api.ts`, stores | Unchanged v1 behavior |

The new shell is not wired into `main.tsx` during B00. That keeps the shipped
application behavior identical while giving B01–B11 a stable place to land
routes. Integration becomes a small, reviewed change once those routes exist.

## Compatibility and extension points

- New API namespaces register in `ApiV2._register_routes`.
- New migrations append to `MIGRATIONS`; never edit an applied migration.
- New frontend routes register in `app/routes.ts` with a unique name and hash.
- New primitives live in `ui/`, export from `ui/index.ts`, and style in
  `styles/ui.css` with existing design tokens.
- Feature branches own their folders; shared tokens change only in B00 or B10.
