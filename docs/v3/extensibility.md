# V3 Extensibility and Local SDK

B13 adds a stable, local-only automation surface on top of the API v3 contracts
from B00. It has three parts:

1. `redscribe.v3.api_sdk` — a typed Python SDK over B00 envelopes, pagination,
   ETags, idempotency, and capabilities.
2. `redscribe.v3.namespaces.extensions` — API routes under `/api/v3/extensions`
   for manifest validation, installation, discovery, and capability negotiation.
3. `frontend/src/features/api-explorer` — an in-app API explorer, manifest editor,
   and developer console with sanitized request/response history.

Everything runs in-process. There are no sockets, no subprocesses, and no
dynamic imports in the SDK. Extensions ship **data only**.

## 1. Non-negotiable invariants

- **No arbitrary code execution.** Manifests are JSON documents limited to a
  fixed set of fields. Keys such as `code`, `script`, `eval`, `exec`, `handler`,
  `path`, `url`, and `module` are rejected anywhere in the document. Values must
  be JSON primitives. The static audit in
  `redscribe.v3.api_sdk.safety.assert_no_code_execution()` parses every shipped
  SDK source file with `ast` and fails on forbidden imports (`subprocess`,
  `socket`, `pickle`, `os`, `importlib`, …), forbidden calls (`eval`, `exec`,
  `compile`, `__import__`), process/network/deserialization paths, and inline
  code objects (`lambda`). It runs automatically via the `extensions.safety`
  route and the `sdk safety` CLI command.
- **Read-only by default.** `SdkClient` and the CLI treat all routes as reads
  unless the caller explicitly opts in. Known write routes
  (`extensions.install`, `extensions.remove`, `extensions.reset`) are blocked by
  `InProcessTransport` unless constructed with `allow_write=True`; the CLI also
  requires `--allow-write`, and the UI requires both a checkbox and a
  confirmation checkbox.
- **Explicit capability gate.** Even with a write opt-in, service writes require
  `V3Config.allow_extensions=True` and the `extensions` capability from B00.
- **No secrets in history.** `CallLog` records body *keys* only, never values,
  headers, or response bodies; the developer console displays sanitized
  summaries.
- **Offline only.** No runtime dependencies, no telemetry, no remote requests,
  no external assets.

## 2. SDK layers

| Module | Responsibility |
| --- | --- |
| `models.py` | `SdkRequest`, `SdkResponse`, `PageResult`, `CallRecord` |
| `envelopes.py` | Decode/render B00 `{data, meta}` and `{error, meta}` shapes |
| `errors.py` | SDK errors mapped to B00 `V3ErrorCode` values |
| `transport.py` | `Transport` protocol and `InProcessTransport` over `V3Router` |
| `client.py` | `SdkClient` with history, conditional requests, idempotency |
| `pagination.py` | Page iteration using B00 signed opaque cursors |
| `capabilities.py` | `CapabilityNegotiator` over B00 `Capabilities` / `V3Config` |
| `manifest.py` | Data-only schema, validation report, `ExtensionManifest`, store |
| `service.py` | `ExtensionService` shared by routes and CLI |
| `scripting.py` | JSON `ScriptPlan` / `ScriptStep` / `ScriptRunner` |
| `safety.py` | Static no-code-execution audit |
| `cli.py` | `python -m redscribe.v3.api_sdk.cli` entry point |

No B00 contract is redefined: envelopes, error codes, `PageRequest`, cursors,
`IdempotencyGuard`, `compute_etag`/`etag_matches`, `normalize_request_id`,
`Capabilities`, `V3Config`, `V3Router`, and namespace discovery are imported and
reused directly.

## 3. Quick start

```python
from redscribe.v3.api_sdk import SdkClient, example_manifest

client = SdkClient()  # in-process, read-only
info = client.data("system", "info")
schema = client.data("extensions", "schema")
report = client.data("extensions", "validate", {"manifest": example_manifest()})
assert report["valid"] is True

page = client.list("extensions", "list", size=20)
response = client.call(
    "extensions",
    "get",
    {"id": "example.panel"},
    etag='"previous-etag"',  # 304 when unchanged
    idempotency_key="read-1",  # replay-safe
)
history = client.history.as_dict()["entries"]
```

For a custom router or capability set:

```python
from redscribe.v3.api.router import V3Router, register_system_routes
from redscribe.v3.api_sdk import InProcessTransport, SdkClient
from redscribe.v3.capabilities import Capabilities
from redscribe.v3.api_sdk.capabilities import CapabilityNegotiator
from redscribe.v3.namespaces.extensions import register

router = V3Router()
register_system_routes(router)
register(router)
transport = InProcessTransport(
    router=router,
    negotiator=CapabilityNegotiator(capabilities=Capabilities(enabled=frozenset({"extensions"}))),
)
client = SdkClient(transport=transport)
```

## 4. Manifest schema

A manifest is a JSON object with these fields:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `schema` | string | yes | must be `redscribe-extension/1` |
| `id` | string | yes | `^[a-z][a-z0-9._-]{2,63}$` |
| `version` | string | yes | semantic `MAJOR.MINOR.PATCH` |
| `title` | string | yes | 1–240 characters, whitespace normalized |
| `summary` | string | no | up to 4000 characters |
| `requires` | list of strings | no | capability names from B00 |
| `contributions` | list of objects | yes | 1–32 declarative entries |
| `metadata` | object | no | ≤16 JSON-primitive entries |

Contribution kinds and their fields:

- `panel`: `id`, `title`, `location` (`sidebar`, `inspector`, `dashboard`,
  `console`), optional `description`.
- `command`: `id`, `title`, optional `group`, `description`. A command declares a
  label; it never names a function, module, or command line.
- `theme`: `id`, `title`, optional `tokens` (string-to-string map),
  `description`.
- `shortcut`: `id`, `title`, `binding` (`Ctrl|Alt|Shift|Meta+<key>`), optional
  `description`.
- `view`: `id`, `title`, `route` (a data label such as `extensions/panel`),
  optional `description`.

`extensions.schema` returns the machine-readable descriptor used by the editor,
including the forbidden-key catalog and all size limits. `extensions.example`
returns a valid starting document.

## 5. Capability negotiation

`CapabilityNegotiator` wraps B00 `Capabilities` and `V3Config`:

- `advertise()` returns the capability map used by `system.capabilities`.
- `negotiate(required)` returns one `CapabilityDecision` per capability.
- `require(name)` raises `CapabilityDeniedError` (403) when disabled.
- `allow_write(opt_in=...)` requires the explicit opt-in first, then
  `config.allow_extensions`, then the `extensions` capability.
- API clients may send `X-Capability: <name>` on any call; the transport checks
  it before dispatch.

## 6. API routes

| Action | Access | Purpose |
| --- | --- | --- |
| `extensions.validate` | public | validate a manifest document |
| `extensions.schema` | public | schema descriptor |
| `extensions.example` | public | valid example document |
| `extensions.contracts` | public | SDK wire contracts |
| `extensions.safety` | public | static audit report |
| `extensions.health` | public | service health |
| `extensions.capabilities` | public | negotiate a list of capabilities |
| `extensions.list` | public | paginated installed manifests |
| `extensions.get` | public | one manifest with ETag / conditional read |
| `extensions.install` | write | install a manifest (explicit opt-in) |
| `extensions.remove` | write | remove a manifest (explicit opt-in) |
| `extensions.routes` | public | current router manifest |

All handlers return B00 success envelopes and raise B00 `V3Error` values for
failures. List responses include `meta.page` and `data.next_cursor` from B00
pagination.

## 7. Scripting

A script is JSON, not code. See `docs/v3/cli-reference.md` for the full command
reference. A plan contains `name`, optional `allow_write`, and up to 100 `steps`
with only these keys: `label`, `namespace`, `action`, `body`, `capability`,
`etag`, `idempotency_key`, `write`. Unknown keys are rejected. The runner checks
*all* write steps against the opt-in before executing the first step, so a
blocked script produces zero API calls.

```json
{
  "name": "local-overview",
  "allow_write": false,
  "steps": [
    {"label": "api info", "namespace": "system", "action": "info", "body": {}},
    {"label": "extensions", "namespace": "extensions", "action": "list", "body": {"size": 10}}
  ]
}
```

## 8. Frontend feature

`frontend/src/features/api-explorer/` exports `ApiExplorerPanel`,
`ManifestEditor`, and `DeveloperConsole`, plus pure helpers, a typed client over
the B00 `V3Client`, and a zustand store. Styling is isolated in
`api-explorer.css` using V3 design tokens. The console records bounded,
redacted history and supports filtering by route, request id, or error code.
The editor validates locally and via `extensions.validate`, showing paths and
messages for each issue and a deterministic fingerprint for valid documents.

## 9. Testing

- Python: `tests/v3_api_sdk/` covers models, manifests, client behavior,
  pagination, capabilities, scripting, CLI subprocesses, the static safety
  audit, and namespace routes.
- Frontend: `frontend/scripts/api-sdk-v3.test.ts` (registered via
  `frontend/scripts/test-suites/13.json`) covers pure validation, safety guards,
  history behavior, and the typed client with injected fake `fetch`.

Run `python3 -m redscribe.v3.api_sdk.cli safety` to verify the no-code-execution
invariant at any time.
