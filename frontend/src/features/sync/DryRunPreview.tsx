import {
  changeTone,
  dryRunHeadline,
  resolutionLabel,
  shortChecksum,
  summarizeChanges,
  summarizeConflicts,
} from "./format";
import { dryRunChanges, dryRunConflicts } from "./helpers";
import type { DryRunReport } from "./types";

interface DryRunPreviewProps {
  report: DryRunReport | null;
  title?: string;
}

export function DryRunPreview(props: DryRunPreviewProps) {
  const { report, title = "Dry-run preview" } = props;
  if (!report) {
    return (
      <section className="sync-dry-run empty">
        <h3>{title}</h3>
        <p>Run a preview to inspect changes, conflicts, and compatibility.</p>
      </section>
    );
  }

  const changes = dryRunChanges(report);
  const conflicts = dryRunConflicts(report);
  const changeSummary = summarizeChanges(changes);
  const conflictSummary = summarizeConflicts(conflicts);

  return (
    <section className="sync-dry-run">
      <header className="sync-dry-run-header">
        <div>
          <h3>{title}</h3>
          <p>{dryRunHeadline(report)}</p>
        </div>
        <span
          className={`sync-badge tone-${report.valid ? "success" : "warning"}`}
        >
          {report.valid ? "valid" : "needs review"}
        </span>
      </header>

      <div className="sync-dry-run-stats">
        <div>
          <strong>{changeSummary.total}</strong>
          <span>changes</span>
        </div>
        <div>
          <strong>{changeSummary.create}</strong>
          <span>create</span>
        </div>
        <div>
          <strong>{changeSummary.update}</strong>
          <span>update</span>
        </div>
        <div>
          <strong>{changeSummary.delete}</strong>
          <span>delete</span>
        </div>
        <div>
          <strong>{conflictSummary.total}</strong>
          <span>conflicts</span>
        </div>
        <div>
          <strong>{conflictSummary.unresolved}</strong>
          <span>unresolved</span>
        </div>
      </div>

      {report.warnings.length > 0 ? (
        <div className="sync-warnings">
          <h4>Warnings</h4>
          <ul>
            {report.warnings.map((warning, index) => (
              <li key={`${warning}-${index}`}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="sync-dry-run-columns">
        <section>
          <h4>Changes</h4>
          {changes.length === 0 ? (
            <p className="sync-empty">No actionable changes detected.</p>
          ) : (
            <ul className="sync-change-list">
              {changes.slice(0, 20).map((change) => (
                <li key={change.key} className="sync-change-item">
                  <span
                    className={`sync-badge tone-${changeTone(change.action)}`}
                  >
                    {change.action}
                  </span>
                  <div>
                    <strong>{change.title || change.path || change.key}</strong>
                    <p>
                      {change.path || "—"} · {shortChecksum(change.checksum)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <h4>Conflicts</h4>
          {conflicts.length === 0 ? (
            <p className="sync-empty">No conflicts detected.</p>
          ) : (
            <ul className="sync-conflict-preview">
              {conflicts.slice(0, 20).map((conflict) => (
                <li key={conflict.key}>
                  <strong>{conflict.title || conflict.path}</strong>
                  <span>
                    {conflict.kind.replaceAll("_", " ")} ·{" "}
                    {resolutionLabel(conflict.resolution)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <details className="sync-dry-run-raw">
        <summary>Raw summary</summary>
        <pre>{JSON.stringify(report.summary, null, 2)}</pre>
      </details>
    </section>
  );
}
