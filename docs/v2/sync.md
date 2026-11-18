# Sync and Portability V2

The sync and portability feature provides backup, restore, import/export, dry-run
planning, conflict detection and resolution, merge previews, change journaling,
version-vector comparison, migration compatibility checks, and progress
reporting. It is implemented as an additive V2 capability: the backend lives in
`redscribe.v2.sync`, the API namespace lives in
`redscribe.ui.web.v2.namespaces.sync`, and the UI feature lives in
`frontend/src/features/sync`. No shared route tables or storage modules are
edited.

## Capabilities

- Capture vault snapshots with manifests and checksums.
- Plan and create backup artifacts (SQLite/portable bundle flows as supported).
- Inspect and restore backups or portable snapshots with compatibility checks.
- Plan and run export/import pipelines with selectable formats and strategies.
- Run dry-run planners for backup, restore, export, import, and migration.
- Verify checksums for files/directories or expected/actual digest maps.
- Detect and resolve conflicts between local and remote record sets.
- Create, inspect, list, update, and discard conflict resolution sessions.
- Preview merges and inspect journal diffs/change summaries.
- Compare and merge version vectors.
- Check manifest migration compatibility and report supported versions.
- Aggregate progress reports for multi-step operations.
- Inspect portability profiles, format matrix, and detected bundle metadata.

## Backend layout

| Module | Responsibility |
| --- | --- |
| `models.py` | Core sync/portability data models and JSON serialization. |
| `errors.py` | Sync-specific validation and operation errors. |
| `checksums.py` | Digest helpers, canonicalization, and checksum verification. |
| `manifest.py` | Snapshot manifests and metadata. |
| `progress.py` | Progress tracking and summaries. |
| `version_vectors.py` | Version vectors, comparison, bump/merge helpers. |
| `change_journal.py` | Vault/record normalization, journaling, and diffs. |
| `conflicts.py` | Conflict detection and resolution application. |
| `merge.py` | Merge engine and preview/record merge logic. |
| `migration.py` | Migration compatibility checks and plans. |
| `backup.py` | Backup planning and artifact creation/inspection. |
| `restore.py` | Restore planning, inspection, and application. |
| `exporter.py` | Export pipeline planning and execution. |
| `importer.py` | Import planning, preview, loading, and execution. |
| `dry_run.py` | Dry-run planning for sync operations. |
| `portable.py` | Portability profiles, format matrix, bundle detection/record loading. |
| `state.py` | In-memory sync state store (sessions, operations, stats). |
| `reports.py` | Health/change/conflict/merge/dry-run summary helpers. |
| `service.py` | `SyncService` facade used by API handlers. |

## API namespace

Register routes on an existing V2 API registry:

```python
from redscribe.ui.web.v2.namespaces import sync as sync_namespace

sync_namespace.register(api)
```

Routes are exposed with the `sync.*` prefix. Handlers return standard V2 route
results and map sync validation/operation errors to V2 error envelopes.

### Route reference

| Route | Purpose | Required fields |
| --- | --- | --- |
| `sync.health` | Availability, formats, strategies, vault stats | — |
| `sync.snapshot` | Portable snapshot manifest and records | — |
| `sync.backup.plan` | Build backup plan and description | `destination` |
| `sync.backup.create` | Create backup artifact and manifest | `destination` |
| `sync.backup.inspect` | Inspect backup file/manifest | `path` |
| `sync.restore.plan` | Inspect restore source and compatibility | `source` |
| `sync.restore.apply` | Restore backup or portable snapshot | `source` |
| `sync.export.plan` | Plan export and summarize impact | `destination` |
| `sync.export.run` | Run export pipeline and write manifest | `destination` |
| `sync.import.plan` | Preview import merge/conflict impact | `source` |
| `sync.import.run` | Import snapshot with strategy/resolutions | `source` |
| `sync.dry_run` | Dry-run planner for sync operations | `operation` |
| `sync.checksums.verify` | Compare/compute checksums | — |
| `sync.conflicts.detect` | Detect changes/conflicts vs remote/source | — |
| `sync.conflicts.resolve` | Resolve conflicts by strategy/resolutions | — |
| `sync.conflicts.session.create` | Create conflict resolution session | `operation` |
| `sync.conflicts.session.get` | Get stored conflict session | `session_id` |
| `sync.conflicts.session.list` | List stored conflict sessions | — |
| `sync.conflicts.session.resolve` | Update session resolutions | `session_id`, `resolutions` |
| `sync.conflicts.session.discard` | Discard conflict session | `session_id` |
| `sync.merge.preview` | Preview merge outcome | — |
| `sync.journal.diff` | Build journal diff against remote/source | — |
| `sync.journal.report` | Change summary report | — |
| `sync.vectors.compare` | Compare/merge version vectors | — |
| `sync.migration.check` | Check manifest migration compatibility | `manifest` |
| `sync.progress.report` | Aggregate step progress into summary | `steps` |
| `sync.portability.profiles` | List portability profiles | — |
| `sync.portability.profile` | Return one portability profile | `name` |
| `sync.portability.detect` | Detect portable bundle format/metadata | `path` |
| `sync.portability.records` | Read portable records from source | `path` |
| `sync.portability.matrix` | Export/import format compatibility matrix | — |
| `sync.state.stats` | Sync state/session/operation stats | — |
| `sync.state.operations` | Recent tracked sync operations | — |

## Frontend feature

`frontend/src/features/sync/` contains the sync UI and pure helpers:

- `types.ts`: shared sync types and payload contracts.
- `format.ts`: formatting helpers (bytes, percent, counts, labels, tones).
- `helpers.ts`: selection/validation, wizard flow, request builders, summaries.
- `state.ts`: reducer, initial state, selectors, and notices.
- `client.ts`: `SyncClient`/`createSyncClient` wrapper over `V2Client`.
- `ProgressDisplay.tsx`: progress bars and step summaries.
- `ConflictResolver.tsx`: conflict review and resolution controls.
- `DryRunPreview.tsx`: dry-run/change/conflict preview panel.
- `BackupRestoreDialog.tsx`: backup and restore dialogs.
- `ImportExportWizard.tsx`: import/export wizard flow.
- `SyncFeature.tsx`: composed sync workspace/feature entry component.
- `index.ts`: public exports for the feature module.

`frontend/scripts/sync.test.ts` covers pure helpers, state, and client request
construction; it is included in `frontend/scripts/test.mjs`.

## Conflict and merge model

- Changes are journaled as portable record diffs (create/update/delete/unchanged).
- Conflicts are detected from local vs remote/source record divergence.
- Supported strategies include merge and preference/skip-oriented strategies as
  exposed by `sync.health`/helpers.
- Manual resolutions can be supplied per conflict/session and previewed before
  apply/import.
- Merge previews and dry-run reports summarize actions, conflicts, and warnings.

## Portability and migration

- Portable bundles carry manifests, checksums, and metadata for verification.
- Format detection and profiles guide backup/export/import choices.
- Migration compatibility checks report supported versions and planned steps for
  manifests before restore/import operations.

## Testing

- Python: `tests/v2_sync/` (`test_sync_models.py`, `test_sync_service.py`,
  `test_sync_api.py`) validate models/service behavior and namespace routes via
  `ApiV2` + `V2Router`.
- Frontend: `frontend/scripts/sync.test.ts` validates pure helpers, reducers, and
  `SyncClient` request mapping.
