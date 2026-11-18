import { useMemo, useState } from "react";
import { BackupDialog, RestoreDialog } from "./BackupRestoreDialog";
import { ImportExportWizard } from "./ImportExportWizard";
import { ProgressDisplay } from "./ProgressDisplay";
import { DryRunPreview } from "./DryRunPreview";
import { createSyncClient } from "./client";
import { initialSyncState, syncReducer } from "./state";
import { formatCount, toErrorMessage } from "./format";
import type { SyncHealth } from "./types";

type Panel = "overview" | "backup" | "restore" | "import" | "export";

export function SyncFeature() {
  const client = useMemo(() => createSyncClient(), []);
  const [panel, setPanel] = useState<Panel>("overview");
  const [health, setHealth] = useState<SyncHealth | null>(null);
  const [state, setState] = useState(initialSyncState("overview"));
  const [loading, setLoading] = useState(false);

  function dispatch(action: import("./state").SyncFeatureAction) {
    setState((current) => syncReducer(current, action));
  }

  async function refresh() {
    try {
      setLoading(true);
      const data = await client.health();
      setHealth(data);
      dispatch({
        type: "notice",
        value: {
          tone: "success",
          title: "Sync ready",
          message: `${formatCount(data.records)} records available`,
        },
      });
    } catch (error) {
      dispatch({
        type: "notice",
        value: {
          tone: "danger",
          title: "Health check failed",
          message: toErrorMessage(error),
        },
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="sync-feature">
      <header className="sync-feature-header">
        <div>
          <h1>Sync and portability</h1>
          <p>
            Backup, restore, export, import, and resolve conflicts without
            leaving the vault.
          </p>
        </div>
        <div className="sync-feature-actions">
          <button type="button" onClick={refresh} disabled={loading}>
            Refresh
          </button>
        </div>
      </header>

      <nav className="sync-tabs" aria-label="Sync panels">
        {(["overview", "backup", "restore", "import", "export"] as Panel[]).map(
          (item) => (
            <button
              key={item}
              type="button"
              className={panel === item ? "active" : ""}
              onClick={() => setPanel(item)}
            >
              {item[0].toUpperCase() + item.slice(1)}
            </button>
          ),
        )}
      </nav>

      {state.notice ? (
        <div className={`sync-banner tone-${state.notice.tone}`} role="status">
          <strong>{state.notice.title}</strong>
          <span>{state.notice.message}</span>
        </div>
      ) : null}

      {panel === "overview" ? (
        <section className="sync-overview">
          <div className="sync-cards">
            <article>
              <h2>Vault</h2>
              <p>
                {health
                  ? health.vault
                  : "Load health to inspect current vault."}
              </p>
            </article>
            <article>
              <h2>Records</h2>
              <p>{health ? formatCount(health.records) : "—"}</p>
            </article>
            <article>
              <h2>Formats</h2>
              <p>
                {health
                  ? health.formats.join(", ")
                  : "json, markdown, html, sqlite"}
              </p>
            </article>
            <article>
              <h2>Strategies</h2>
              <p>
                {health
                  ? health.strategies.join(", ")
                  : "merge, skip, prefer_local, prefer_remote"}
              </p>
            </article>
          </div>
          <ProgressDisplay
            reports={state.progress}
            title="Recent progress"
            compact
          />
          <DryRunPreview report={state.dryRun} title="Last dry run" />
        </section>
      ) : null}

      {panel === "backup" ? <BackupDialog /> : null}
      {panel === "restore" ? <RestoreDialog /> : null}
      {panel === "import" ? <ImportExportWizard mode="import" /> : null}
      {panel === "export" ? <ImportExportWizard mode="export" /> : null}
    </div>
  );
}

export default SyncFeature;
