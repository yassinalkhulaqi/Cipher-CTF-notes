import { useMemo, useState } from "react";
import { createSyncClient } from "./client";
import { ConflictResolver } from "./ConflictResolver";
import { DryRunPreview } from "./DryRunPreview";
import { ProgressDisplay } from "./ProgressDisplay";
import {
  activeWizardIndex,
  buildWizardSteps,
  defaultSelection,
  dryRunConflicts,
  resolutionMap,
  validateExportSelection,
  validateImportSelection,
} from "./helpers";
import { initialSyncState, syncReducer } from "./state";
import { summarizeMerge, toErrorMessage } from "./format";
import type { ConflictRecord, SyncSelection } from "./types";

interface ImportExportWizardProps {
  mode: "import" | "export";
  initialSelection?: Partial<SyncSelection>;
}

export function ImportExportWizard(props: ImportExportWizardProps) {
  const { mode, initialSelection } = props;
  const client = useMemo(() => createSyncClient(), []);
  const [state, setState] = useState<ReturnType<typeof initialSyncState>>(
    () => ({
      ...initialSyncState(mode),
      wizard: buildWizardSteps(mode),
      selection: {
        ...defaultSelection(),
        format: "json" as SyncSelection["format"],
        ...(initialSelection ?? {}),
      },
    }),
  );
  const [report, setReport] = useState<import("./types").DryRunReport | null>(
    null,
  );
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  function dispatch(action: import("./state").SyncFeatureAction) {
    setState((current) => syncReducer(current, action));
  }

  const errors =
    mode === "import"
      ? validateImportSelection(state.selection)
      : validateExportSelection(state.selection);
  const conflicts = state.conflicts.length
    ? state.conflicts
    : dryRunConflicts(report);
  const stepIndex = activeWizardIndex(state.wizard);

  async function preview() {
    try {
      dispatch({ type: "busy", value: true });
      const payload =
        mode === "import"
          ? {
              source: state.selection.sourcePath,
              format:
                state.selection.format === "markdown" ? "markdown" : "json",
              strategy: state.selection.strategy,
              verify_checksums: state.selection.verifyChecksums,
            }
          : {
              destination: state.selection.destinationPath,
              format:
                state.selection.format === "sqlite"
                  ? "json"
                  : state.selection.format,
              include_deleted: state.selection.includeDeleted,
              include_settings: state.selection.includeSettings,
            };
      const next = await client.dryRun(mode, payload);
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

  async function run() {
    try {
      dispatch({ type: "busy", value: true });
      const data =
        mode === "import"
          ? await client.importData(
              { ...state.selection, dryRun: false },
              resolutionMap(conflicts),
            )
          : await client.exportData({ ...state.selection, dryRun: false });
      setResult(data as unknown as Record<string, unknown>);
      dispatch({ type: "wizard", index: 3, status: "complete" });
      dispatch({
        type: "log",
        value: {
          operation: mode,
          status: "completed",
          summary:
            mode === "import"
              ? summarizeMerge(
                  (data as { merge?: Record<string, unknown> }).merge ?? {},
                )
              : `Exported to ${state.selection.destinationPath}`,
        },
      });
    } catch (error) {
      dispatch({
        type: "notice",
        value: {
          tone: "danger",
          title: "Run failed",
          message: toErrorMessage(error),
        },
      });
    } finally {
      dispatch({ type: "busy", value: false });
    }
  }

  return (
    <section className="sync-wizard">
      <header>
        <h2>{mode === "import" ? "Import wizard" : "Export wizard"}</h2>
        <ol className="sync-stepper">
          {state.wizard.map((step, index) => (
            <li
              key={step.id}
              data-status={step.status}
              aria-current={index === stepIndex ? "step" : undefined}
            >
              <strong>{step.title}</strong>
              <span>{step.description}</span>
            </li>
          ))}
        </ol>
      </header>

      <div className="sync-form-grid">
        <label>
          <span>{mode === "import" ? "Source path" : "Destination path"}</span>
          <input
            value={
              mode === "import"
                ? state.selection.sourcePath
                : state.selection.destinationPath
            }
            onChange={(event) =>
              dispatch({
                type: "selection",
                value:
                  mode === "import"
                    ? { sourcePath: event.target.value }
                    : { destinationPath: event.target.value },
              })
            }
            placeholder={
              mode === "import"
                ? "/path/to/snapshot.json"
                : "/path/to/export.json"
            }
          />
        </label>
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
            {mode === "import" ? (
              <>
                <option value="json">JSON</option>
                <option value="markdown">Markdown</option>
              </>
            ) : (
              <>
                <option value="json">JSON</option>
                <option value="markdown">Markdown</option>
                <option value="html">HTML</option>
              </>
            )}
          </select>
        </label>
        {mode === "import" ? (
          <label>
            <span>Merge strategy</span>
            <select
              value={state.selection.strategy}
              onChange={(event) =>
                dispatch({
                  type: "selection",
                  value: {
                    strategy: event.target.value as SyncSelection["strategy"],
                  },
                })
              }
            >
              <option value="merge">Merge</option>
              <option value="prefer_local">Prefer local</option>
              <option value="prefer_remote">Prefer remote</option>
              <option value="skip">Skip conflicts</option>
            </select>
          </label>
        ) : (
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
        )}
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
          onClick={preview}
          disabled={state.busy || errors.length > 0}
        >
          Run dry-run
        </button>
        <button
          type="button"
          onClick={run}
          disabled={state.busy || errors.length > 0}
        >
          {mode === "import" ? "Import" : "Export"}
        </button>
      </div>

      <DryRunPreview report={report} />
      {mode === "import" ? (
        <ConflictResolver
          conflicts={conflicts as ConflictRecord[]}
          onChange={(value) => dispatch({ type: "conflicts", value })}
        />
      ) : null}
      <ProgressDisplay
        reports={state.progress}
        title="Wizard progress"
        compact
      />
      {result ? (
        <section className="sync-result">
          <h3>Result</h3>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </section>
      ) : null}
    </section>
  );
}
