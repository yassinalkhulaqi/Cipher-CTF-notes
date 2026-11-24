/** Audit viewer with filters and redacted, locked states. */

import { useState } from "react";

import { V3Panel } from "../../v3/components/V3Panel";
import { auditCounts, filterAudit, formatTimestamp } from "./pure";
import type { AuditEntry, AuditFilterState } from "./types";

export interface AuditViewerProps {
  entries: AuditEntry[];
  busy: boolean;
  onFilter: (filter: AuditFilterState) => void;
  onExport: (format: "json" | "jsonl") => void;
}

const DEFAULT_FILTER: AuditFilterState = {
  action: "",
  outcome: "",
  actor: "",
  limit: 50,
};

export function AuditViewer({ entries, busy, onFilter, onExport }: AuditViewerProps) {
  const [filter, setFilter] = useState<AuditFilterState>(DEFAULT_FILTER);
  const shown = filterAudit(entries, filter);
  const counts = auditCounts({ entries, total: entries.length, filter: {}, stats: {
    total: entries.length,
    by_outcome: {},
    by_action: {},
  } });

  const patch = (update: Partial<AuditFilterState>) => {
    const next = { ...filter, ...update };
    setFilter(next);
    onFilter(next);
  };

  return (
    <V3Panel
      title="Audit trail"
      subtitle={`${entries.length} recorded security actions`}
      kind="activity"
      actions={
        <div className="vs-audit__exports">
          <button type="button" onClick={() => onExport("json")} disabled={busy}>
            Export JSON
          </button>
          <button type="button" onClick={() => onExport("jsonl")} disabled={busy}>
            Export JSONL
          </button>
        </div>
      }
    >
      <div className="vs-audit__filters">
        <input
          aria-label="Filter by action"
          placeholder="Action"
          value={filter.action}
          onChange={(event) => patch({ action: event.target.value })}
        />
        <select
          aria-label="Filter by outcome"
          value={filter.outcome}
          onChange={(event) => patch({ outcome: event.target.value })}
        >
          <option value="">all outcomes</option>
          <option value="success">success</option>
          <option value="denied">denied</option>
          <option value="failure">failure</option>
        </select>
        <input
          aria-label="Filter by actor"
          placeholder="Actor"
          value={filter.actor}
          onChange={(event) => patch({ actor: event.target.value })}
        />
        <select
          aria-label="Result limit"
          value={filter.limit}
          onChange={(event) => patch({ limit: Number(event.target.value) })}
        >
          {[10, 50, 100].map((limit) => (
            <option value={limit} key={limit}>
              {limit} rows
            </option>
          ))}
        </select>
      </div>
      <div className="vs-audit__counts">
        <span data-tone="good">{counts.success} succeeded</span>
        <span data-tone="bad">{counts.denied} denied</span>
        <span>{counts.other} other</span>
      </div>
      {shown.length === 0 ? (
        <p className="vs-locked">No audit entries match these filters.</p>
      ) : (
        <table className="vs-audit__table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Action</th>
              <th>Outcome</th>
              <th>Actor</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((entry) => (
              <tr key={entry.entry_id}>
                <td>{formatTimestamp(entry.timestamp)}</td>
                <td>{entry.action}</td>
                <td data-tone={entry.outcome}>{entry.outcome}</td>
                <td>{entry.actor}</td>
                <td>
                  <code>{JSON.stringify(entry.detail)}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="vs-locked">Details are redacted before display and export.</p>
    </V3Panel>
  );
}
