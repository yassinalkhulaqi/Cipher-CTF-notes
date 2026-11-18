import { formatPercent, progressLabel } from "./format";
import type { ProgressReport } from "./types";

interface ProgressDisplayProps {
  reports: ProgressReport[];
  title?: string;
  compact?: boolean;
}

export function ProgressDisplay(props: ProgressDisplayProps) {
  const { reports, title = "Progress", compact = false } = props;
  const latest = reports[reports.length - 1];
  const percent = latest ? latest.percent : 0;

  return (
    <section className={compact ? "sync-progress compact" : "sync-progress"}>
      <header className="sync-progress-header">
        <strong>{title}</strong>
        <span>{formatPercent(percent)}</span>
      </header>
      <div
        className="sync-progress-bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(percent)}
      >
        <div className="sync-progress-fill" style={{ width: `${percent}%` }} />
      </div>
      <p className="sync-progress-label">{progressLabel(latest)}</p>
      {!compact && reports.length > 0 ? (
        <ol className="sync-progress-list">
          {reports.map((report, index) => (
            <li
              key={`${report.stage}-${index}`}
              data-done={report.done ? "true" : "false"}
            >
              <span className="sync-progress-stage">{report.stage}</span>
              <span className="sync-progress-message">
                {report.message || "—"}
              </span>
              <span className="sync-progress-value">
                {formatPercent(report.percent)}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}

export function ProgressSummary(props: { report: ProgressReport | null }) {
  const { report } = props;
  if (!report) return <p className="sync-progress-empty">No progress yet.</p>;
  return (
    <div className="sync-progress-summary">
      <span className="sync-progress-stage">{report.stage}</span>
      <span>{report.message || "Working"}</span>
      <span>{formatPercent(report.percent)}</span>
    </div>
  );
}
