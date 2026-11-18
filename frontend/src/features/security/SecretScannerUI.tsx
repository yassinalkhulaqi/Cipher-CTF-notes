import { useMemo, useState } from "react";
import type { SecretFinding, SecretScanResult, Severity } from "./types";
import {
  filterFindings,
  formatConfidence,
  formatCount,
  groupFindingsByName,
  scanSummary,
  severityLabel,
  sortFindings,
} from "./helpers";

interface Props {
  text: string;
  result: SecretScanResult | null;
  loading?: boolean;
  onChangeText: (value: string) => void;
  onScan: () => void;
  onRevealFinding?: (finding: SecretFinding, reveal: boolean) => void;
}

const SEVERITIES: Severity[] = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
  "none",
];

export function SecretScannerUI({
  text,
  result,
  loading = false,
  onChangeText,
  onScan,
  onRevealFinding,
}: Props) {
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});

  const findings = useMemo(() => {
    const base = sortFindings(result?.findings || []);
    return filterFindings(base, {
      query,
      severities: severity === "all" ? undefined : [severity],
    });
  }, [result, query, severity]);

  const groups = useMemo(
    () => groupFindingsByName(result?.findings || []),
    [result],
  );

  function toggleReveal(finding: SecretFinding) {
    const key = `${finding.name}:${finding.start}:${finding.end}`;
    const next = !revealed[key];
    setRevealed((current) => ({ ...current, [key]: next }));
    onRevealFinding?.(finding, next);
  }

  return (
    <section
      className="security-panel secret-scanner"
      aria-label="Secret scanner"
    >
      <header className="security-panel__header">
        <div>
          <h2>Secret Scanner</h2>
          <p className="security-panel__subtitle">{scanSummary(result)}</p>
        </div>
        <button
          type="button"
          className="button"
          onClick={onScan}
          disabled={loading}
        >
          {loading ? "Scanning…" : "Scan for secrets"}
        </button>
      </header>

      <div className="security-grid">
        <label className="field field--stacked">
          <span className="field__label">Text to scan</span>
          <textarea
            className="input"
            rows={10}
            value={text}
            onChange={(event) => onChangeText(event.target.value)}
            placeholder="Paste notes, commands, or export content"
          />
        </label>

        <div className="security-stats" aria-label="Scan statistics">
          <div className="stat-card">
            <span className="stat-card__label">Findings</span>
            <strong>{result?.count ?? 0}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-card__label">Highest</span>
            <strong>{severityLabel(result?.highest_severity)}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-card__label">Characters</span>
            <strong>{result?.scanned_characters ?? text.length}</strong>
          </div>
          <div className="stat-card">
            <span className="stat-card__label">Patterns</span>
            <strong>{result?.pattern_count ?? 0}</strong>
          </div>
        </div>
      </div>

      <div className="toolbar" role="group" aria-label="Finding filters">
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
              No findings match the current filters.
            </p>
          ) : (
            <ul className="finding-list">
              {findings.map((finding) => {
                const key = `${finding.name}:${finding.start}:${finding.end}`;
                const isRevealed = Boolean(revealed[key]);
                return (
                  <li
                    key={key}
                    className={`finding-item finding-item--${finding.severity}`}
                  >
                    <div className="finding-item__header">
                      <strong>{finding.name}</strong>
                      <span className={`badge badge--${finding.severity}`}>
                        {severityLabel(finding.severity)}
                      </span>
                    </div>
                    <div className="finding-item__meta">
                      <span>
                        Line {finding.line}:{finding.column}
                      </span>
                      <span>
                        {formatConfidence(finding.confidence)} confidence
                      </span>
                    </div>
                    <code className="finding-item__value">
                      {isRevealed ? finding.value : finding.masked}
                    </code>
                    {finding.context ? (
                      <p className="finding-item__context">{finding.context}</p>
                    ) : null}
                    <div className="finding-item__actions">
                      <button
                        type="button"
                        className="button button--ghost"
                        onClick={() => toggleReveal(finding)}
                      >
                        {isRevealed ? "Hide value" : "Reveal value"}
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="security-column">
          <h3>Detector summary</h3>
          {groups.length === 0 ? (
            <p className="empty-state">Run a scan to see detector coverage.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Detector</th>
                  <th>Count</th>
                  <th>Highest severity</th>
                </tr>
              </thead>
              <tbody>
                {groups.map((group) => (
                  <tr key={group.name}>
                    <td>{group.name}</td>
                    <td>{formatCount(group.count, "hit")}</td>
                    <td>{severityLabel(group.severity)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
}
