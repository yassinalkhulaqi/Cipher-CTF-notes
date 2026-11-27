# Playbook automation (v4)

Playbook automation models security-workflow playbooks as **data**. A playbook
is a directed acyclic graph (DAG) of declarative nodes; a run is a deterministic
trace of simulated steps. The v4 slice never executes shell commands, evaluates
user expressions, or opens network connections from the domain layer.

## Scope and guarantees

- **Data only.** Node parameters are inert strings. `simulate_failure` and
  `delay_ms` influence the simulated trace; they never reach an interpreter.
- **Deterministic.** Topological order, trace digests, durations and schedule
  occurrences derive only from input data and an injected clock.
- **Composable.** The slice reuses the v4 kernel: `ApiError` envelopes,
  `CapabilitySet`, `FeatureGate`, `EventBus`, `PageMeta`, `paginate` and `Clock`.
- **Additive.** All files are new; the kernel and v3 automation feature are
  untouched.

## Layout

| Path | Responsibility |
| --- | --- |
| `src/redscribe/v4/automation_v4/types.py` | Immutable, validated contracts with dict round-trips |
| `.../service.py` | `DagValidator`, `DryRunExecutor`, `ScheduleEvaluator`, `RunManager` |
| `.../storage.py` | `RunStore` CRUD, indexes, snapshot export/import, pruning |
| `.../api.py` | Action dispatcher, v4 envelopes, pagination, capability checks, events |
| `frontend/src/features/playbook-automation/` | Typed client, reducer, `DagCanvas`, token-driven CSS |
| `frontend/scripts/v4-playbook-automation.test.ts` | Frontend unit tests |
| `tests/v4_automation_v4/` | Python contract, service and API tests |

## Domain contracts

### `DagNode`, `DagEdge`, `PlaybookDag`

`DagNode` has `id`, `label`, `kind`, `depends_on` and `params`. Validation
rejects empty ids and labels, self-dependencies, duplicate dependencies and
empty parameter keys. `signature` is a stable fingerprint of the inert config.

`DagEdge` records an explicit `source -> target` relationship. `PlaybookDag`
validates duplicate node ids, unknown dependencies, dangling edges and duplicate
edges at construction time. `with_node` replaces or adds a node by id;
`without_node` removes a node together with every dependency and edge that
mentions it.

`RunStatus` is `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED` or `CANCELLED`.
`TraceStatus` describes per-node outcomes: `PLANNED`, `SUCCEEDED`, `FAILED`,
`SKIPPED`. `RunRecord` captures a run snapshot with a tuple of `TraceStep`s;
terminal states require a finish timestamp.

`Schedule` carries a `Frequency` (`INTERVAL`, `DAILY`, `WEEKLY`, `MONTHLY`),
cron-like fields (`minute`, `hour`, `day_of_week`, `day_of_month`), an interval
in minutes, a `next_run` timestamp and an `enabled` flag.

## Services

### `DagValidator`

- Merges `depends_on` declarations with explicit edges into one adjacency map.
- Detects cycles via a colouring DFS and returns canonical, deduplicated cycles.
- Reports duplicate ids, missing dependencies, dangling edges and self-loops.
- Computes a Kahn topological order with **lexicographic tie-breaking** at each
  wave, parallel layers, longest-path depths and a deterministic critical path.
- `require_valid` raises `DagValidationError` with stable error codes.

### `DryRunExecutor`

Walks the validated order. A node is `SKIPPED` when any incoming dependency did
not succeed, `FAILED` when named in `fail_nodes` or when its inert
`simulate_failure` parameter is `"true"`, otherwise `SUCCEEDED`. Durations come
from the node kind plus a SHA-256-derived jitter and an optional capped
`delay_ms`. The result carries a 24-character digest of the canonical trace.

### `ScheduleEvaluator`

Computes the first occurrence strictly after a reference instant (UTC):
interval addition, daily time-of-day, weekly weekday selection and monthly
day-of-month with clamping for short months. `upcoming` previews several
occurrences, `refresh` advances `next_run`, and `due` compares against the
injected clock.

### `RunManager`

`start` persists a `RUNNING` record and emits `RUN_STARTED`; `finish` records a
dry-run result and emits `RUN_FINISHED`; `cancel` moves a non-terminal run to
`CANCELLED` and also emits `RUN_FINISHED`. Illegal transitions raise
`RunStateError`. Schedule planning persists refreshed schedules and
`due_schedules` returns those whose next run has passed.

## Storage

`RunStore` keeps runs, playbook definitions and schedules in memory with
secondary indexes by playbook and status. It supports `history`, `recent`,
`prune`, `stats`, and a versioned `export`/`import_snapshot` round trip that
preserves all indexes.

## API

Routes are registered on the v4 `RouteRegistry` under
`/api/v4/automation[/validate|/playbooks|/dry-run|/runs|/schedules]`.
Actions are dispatched through envelopes:

| Action | Method | Capabilities |
| --- | --- | --- |
| `describe`, `validate`, `playbooks`, `dry-run`, `runs`, `run`, `schedules`, `due`, `stats` | GET/POST | `read` |
| `start`, `complete`, `plan-schedule` | POST | `read`, `automate` |
| `cancel` | POST | `read`, `automate`, `delete` |

Every response has `data` + `meta` (request id, version, page, page size, etag,
next cursor). Errors are `{"error": {"code", "message", "details"}}` with stable
codes `not_found`, `invalid_input`, `conflict`, `forbidden`, `unavailable` and
`internal`. Collection actions use cursor pagination.

## Frontend

`DagCanvas` renders four token-styled panels:

1. **Dependency canvas** — cards placed by `(column, row)` in a CSS grid,
   dependency connectors drawn with CSS repeating gradients and arrow heads.
   Selecting a card reveals an inspector for label, kind and dependencies.
2. **Dry-run trace** — ordered rows with status tones, duration bars and
   detail text.
3. **Schedule editor** — frequency, interval, hour, minute and month-day
   inputs with a human-readable preview and a saved-schedule list.
4. **Run history** — status filter and a list of recorded runs.

`reducer` actions are pure and immutable; layout and edge placement derive from
the DAG. All colours, spacing, radii, typography and motion come from
`var(--v4-*)` tokens imported from `styles/tokens-v4.css`.

## Testing

`pytest` covers contract validation and round-trips, cycle detection, missing
dependencies and deterministic order, dry-run trace ordering and failure
propagation, recurrence (including month-end clamping), run lifecycle and
events, storage filters, API envelopes and capability errors. `npm test` covers
the reducer, selectors, layout helpers and typed API client (including
structured errors).
