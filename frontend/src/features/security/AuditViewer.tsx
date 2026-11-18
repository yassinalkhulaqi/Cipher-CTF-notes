import { useMemo, useState } from "react";
import type { AuditReport, Severity } from "./types";
import {
  auditSeverityCounts,
  formatCount,
  severityLabel,
  sortAuditFindings,
  timelineMaxCount,
} from "./helpers";

interface Props {
  report: AuditReport | null;
  loading?: boolean;
  onRefresh?: () => void;
}

const SEVERITIES: Severity[] = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
  "none",
];

export function AuditViewer({ report, loading = false, onRefresh }: Props) {
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [query, setQuery] = useState("");

  const findings = useMemo(() => {
    const sorted = sortAuditFindings(report?.findings || []);
    return sorted.filter((finding) => {
      if (severity !== "all" && finding.severity !== severity) return false;
      if (!query.trim()) return true;
      const needle = query.toLowerCase();
      return (
        finding.code.toLowerCase().includes(needle) ||
        finding.message.toLowerCase().includes(needle)
      );
    });
  }, [report, severity, query]);

  const counts = auditSeverityCounts(report);
  const timelineMax = timelineMaxCount(report);

  return (
    <section className="security-panel audit-viewer" aria-label="Audit viewer">
      <header className="security-panel__header">
        <div>
          <h2>Audit Viewer</h2>
          <p className="security-panel__subtitle">
            {report
              ? `${formatCount(report.total_events, "event")} analyzed`
              : "No audit data"}
          </p>
        </div>
        <button
          type="button"
          className="button"
          onClick={onRefresh}
          disabled={loading || !onRefresh}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      <div className="security-stats">
        <div className="stat-card">
          <span className="stat-card__label">Total events</span>
          <strong>{report?.total_events ?? 0}</strong>
        </div>
        <div className="stat-card">
          <span className="stat-card__label">Highest severity</span>
          <strong>{severityLabel(report?.highest_severity)}</strong>
        </div>
        <div className="stat-card">
          <span className="stat-card__label">Findings</span>
          <strong>{report?.findings.length ?? 0}</strong>
        </div>
        <div className="stat-card">
          <span className="stat-card__label">Critical</span>
          <strong>{counts.critical}</strong>
        </div>
      </div>

      <div className="toolbar">
        <label className="field">
          <span className="field__label">Search</span>
          <input
            className="input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter findings"
          />
        </label>
        <label className="field">
          <span className="field__label">Severity</span>
          <select
            className="input"
            value={severity}
            onChange={(event) =>
              setSeverity(event.target.value as Severity | "all")
            }
          >
            <option value="all">All</option>
            {SEVERITIES.map((item) => (
              <option key={item} value={item}>
                {severityLabel(item)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="security-columns">
        <div className="security-column">
          <h3>Findings</h3>
          {findings.length === 0 ? (
            <p className="empty-state">
              No audit findings match the current filters.
            </p>
          ) : (
            <ul className="finding-list">
              {findings.map((finding) => (
                <li
                  key={`${finding.code}:${finding.message}`}
                  className={`finding-item finding-item--${finding.severity}`}
                >
                  <div className="finding-item__header">
                    <strong>{finding.code}</strong>
                    <span className={`badge badge--${finding.severity}`}>
                      {severityLabel(finding.severity)}
                    </span>
                  </div>
                  <p>{finding.message}</p>
                  <div className="finding-item__meta">
                    <span>{formatCount(finding.count, "occurrence")}</span>
                    {finding.event_ids.length ? (
                      <span>{finding.event_ids.length} event IDs</span>
                    ) : null}
                  </div>
                  {Object.keys(finding.details || {}).length ? (
                    <pre className="finding-item__details">
                      {JSON.stringify(finding.details, null, 2)}
                    </pre>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="security-column">
          <h3>Event breakdown</h3>
          <div className="breakdown-grid">
            <div>
              <h4>By type</h4>
              {Object.keys(report?.counts_by_type || {}).length === 0 ? (
                <p className="empty-state">No type data.</p>
              ) : (
                <ul className="kv-list">
                  {Object.entries(report?.counts_by_type || {}).map(
                    ([key, value]) => (
                      <li key={key}>
                        <span>{key}</span>
                        <strong>{value}</strong>
                      </li>
                    ),
                  )}
                </ul>
              )}
            </div>
            <div>
              <h4>By outcome</h4>
              {Object.keys(report?.counts_by_outcome || {}).length === 0 ? (
                <p className="empty-state">No outcome data.</p>
              ) : (
                <ul className="kv-list">
                  {Object.entries(report?.counts_by_outcome || {}).map(
                    ([key, value]) => (
                      <li key={key}>
                        <span>{key}</span>
                        <strong>{value}</strong>
                      </li>
                    ),
                  )}
                </ul>
              )}
            </div>
          </div>

          <h3>Timeline</h3>
          {!report?.timeline?.length ? (
            <p className="empty-state">No timeline buckets available.</p>
          ) : (
            <ul className="timeline-list">
              {report.timeline.map((bucket) => {
                const total = Object.entries(bucket).reduce(
                  (sum, [key, value]) => {
                    if (key === "bucket" || typeof value !== "number")
                      return sum;
                    return sum + value;
                  },
                  0,
                );
                const width =
                  timelineMax > 0
                    ? Math.max(4, Math.round((total / timelineMax) * 100))
                    : 4;
                return (
                  <li key={String(bucket.bucket)} className="timeline-item">
                    <div className="timeline-item__header">
                      <strong>{String(bucket.bucket)}</strong>
                      <span>{total}</span>
                    </div>
                    <div className="timeline-item__bar">
                      <div style={{ width: `${width}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
