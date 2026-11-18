import { useMemo, useState } from "react";
import { createSyncClient } from "./client";
import { ProgressDisplay } from "./ProgressDisplay";
import { DryRunPreview } from "./DryRunPreview";
import {
  defaultSelection,
  validateBackupSelection,
  validateRestoreSelection,
} from "./helpers";
import { initialSyncState, syncReducer } from "./state";
import { formatBytes, toErrorMessage } from "./format";
import type { SyncSelection } from "./types";

interface BackupRestoreDialogProps {
  mode: "backup" | "restore";
  initialSelection?: Partial<SyncSelection>;
  onClose?: () => void;
}

export function BackupRestoreDialog(props: BackupRestoreDialogProps) {
  const { mode, initialSelection, onClose } = props;
  const client = useMemo(() => createSyncClient(), []);
  const [state, setState] = useState<ReturnType<typeof initialSyncState>>(
    () => ({
      ...initialSyncState(mode),
      selection: {
        ...defaultSelection(),
        format: "sqlite" as SyncSelection["format"],
        ...(initialSelection ?? {}),
      },
    }),
  );
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [report, setReport] = useState<import("./types").DryRunReport | null>(
    null,
  );

  const errors =
    mode === "backup"
      ? validateBackupSelection(state.selection)
      : validateRestoreSelection(state.selection);

  function dispatch(action: import("./state").SyncFeatureAction) {
    setState((current) => syncReducer(current, action));
  }

  async function runPreview() {
    try {
      dispatch({ type: "busy", value: true });
      const next = await client.dryRun(
        mode,
        mode === "backup"
          ? {
              destination: state.selection.destinationPath,
              format: state.selection.format === "json" ? "json" : "sqlite",
              include_deleted: state.selection.includeDeleted,
              include_settings: state.selection.includeSettings,
            }
          : {
              source: state.selection.sourcePath,
              verify_checksums: state.selection.verifyChecksums,
              mode: "replace",
            },
      );
      setReport(next);
      dispatch({ type: "dry-run", value: next });
      dispatch({ type: "wizard", index: 1, status: "complete" });
    } catch (error) {
      dispatch({
        type: "notice",
        value: {
          tone: "danger",
          title: "Preview failed",
          message: toErrorMessage(error),
        },
      });
    } finally {
      dispatch({ type: "busy", value: false });
    }
  }

  async function runAction() {
    try {
      dispatch({ type: "busy", value: true });
      const data =
        mode === "backup"
          ? await client.backup({ ...state.selection, dryRun: false })
          : await client.restore({ ...state.selection, dryRun: false });
      setResult(data as unknown as Record<string, unknown>);
      dispatch({ type: "wizard", index: 3, status: "complete" });
      dispatch({
        type: "log",
        value: {
          operation: mode,
          status: "completed",
          summary:
            mode === "backup"
              ? `Backup written to ${state.selection.destinationPath}`
              : `Restore applied from ${state.selection.sourcePath}`,
        },
      });
    } catch (error) {
      dispatch({
        type: "notice",
        value: {
          tone: "danger",
          title: "Operation failed",
          message: toErrorMessage(error),
        },
      });
    } finally {
      dispatch({ type: "busy", value: false });
    }
  }

  return (
    <section className="sync-dialog">
      <header className="sync-dialog-header">
        <div>
          <h2>{mode === "backup" ? "Backup vault" : "Restore vault"}</h2>
          <p>
            {mode === "backup"
              ? "Create a portable backup with checksum manifest."
              : "Inspect and restore a backup snapshot."}
          </p>
        </div>
        {onClose ? (
          <button type="button" onClick={onClose}>
            Close
          </button>
        ) : null}
      </header>

      <div className="sync-form-grid">
        {mode === "backup" ? (
          <label>
            <span>Destination</span>
            <input
              value={state.selection.destinationPath}
              onChange={(event) =>
                dispatch({
                  type: "selection",
                  value: { destinationPath: event.target.value },
                })
              }
              placeholder="/path/to/backup.db"
            />
          </label>
        ) : (
          <label>
            <span>Source</span>
            <input
              value={state.selection.sourcePath}
              onChange={(event) =>
                dispatch({
                  type: "selection",
                  value: { sourcePath: event.target.value },
                })
              }
              placeholder="/path/to/backup.db"
            />
          </label>
        )}

        {mode === "backup" ? (
          <label>
            <span>Format</span>
            <select
              value={state.selection.format}
              onChange={(event) =>
                dispatch({
                  type: "selection",
                  value: {
                    format: event.target.value as SyncSelection["format"],
                  },
                })
              }
            >
              <option value="sqlite">SQLite</option>
              <option value="json">Portable JSON</option>
            </select>
          </label>
        ) : (
          <label className="sync-checkbox">
            <input
              type="checkbox"
              checked={state.selection.verifyChecksums}
              onChange={(event) =>
                dispatch({
                  type: "selection",
                  value: { verifyChecksums: event.target.checked },
                })
              }
            />
            <span>Verify checksums</span>
          </label>
        )}

        {mode === "backup" ? (
          <>
            <label className="sync-checkbox">
              <input
                type="checkbox"
                checked={state.selection.includeSettings}
                onChange={(event) =>
                  dispatch({
                    type: "selection",
                    value: { includeSettings: event.target.checked },
                  })
                }
              />
              <span>Include settings</span>
            </label>
            <label className="sync-checkbox">
              <input
                type="checkbox"
                checked={state.selection.includeDeleted}
                onChange={(event) =>
                  dispatch({
                    type: "selection",
                    value: { includeDeleted: event.target.checked },
                  })
                }
              />
              <span>Include deleted records</span>
            </label>
          </>
        ) : null}
      </div>

      {errors.length ? (
        <ul className="sync-errors">
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      ) : null}

      <div className="sync-actions">
        <button
          type="button"
          onClick={runPreview}
          disabled={state.busy || errors.length > 0}
        >
          Preview
        </button>
        <button
          type="button"
          onClick={runAction}
          disabled={state.busy || errors.length > 0}
        >
          {mode === "backup" ? "Create backup" : "Restore"}
        </button>
      </div>

      <DryRunPreview report={report} />
      <ProgressDisplay
        reports={state.progress}
        title="Operation progress"
        compact
      />

      {result ? (
        <section className="sync-result">
          <h3>Result</h3>
          <dl>
            <div>
              <dt>Path</dt>
              <dd>{String(result.path ?? result.restored_path ?? "—")}</dd>
            </div>
            <div>
              <dt>Bytes</dt>
              <dd>{formatBytes(Number(result.bytes_written ?? 0))}</dd>
            </div>
            <div>
              <dt>Checksum</dt>
              <dd>{String(result.checksum ?? "—")}</dd>
            </div>
          </dl>
        </section>
      ) : null}
    </section>
  );
}

export function BackupDialog(props: Omit<BackupRestoreDialogProps, "mode">) {
  return <BackupRestoreDialog {...props} mode="backup" />;
}

export function RestoreDialog(props: Omit<BackupRestoreDialogProps, "mode">) {
  return <BackupRestoreDialog {...props} mode="restore" />;
}
