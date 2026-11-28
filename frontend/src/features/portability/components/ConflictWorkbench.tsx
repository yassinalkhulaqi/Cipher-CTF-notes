import { useState } from "react";

import type { ConflictView, Resolution } from "../types";
import {
  REASON_CODES,
  RESOLUTIONS,
  conflictCounts,
  diffRows,
  filterConflicts,
  reasonHelp,
  reasonLabel,
  reasonTone,
  renderValue,
  resolutionLabel,
  resolutionTone,
  suggestResolution,
  unresolvedCount,
} from "../pure";

interface Props {
  conflicts: ConflictView[];
  strategy: string;
  onStrategy: (strategy: string) => void;
  onResolve: (ref: string, resolution: Resolution) => void;
  onApply: () => void;
}

export function ConflictWorkbench({
  conflicts,
  strategy,
  onStrategy,
  onResolve,
  onApply,
}: Props) {
  const [query, setQuery] = useState("");
  const [reason, setReason] = useState("");
  const visible = filterConflicts(conflicts, { query, reason });
  const counts = conflictCounts(conflicts);

  return (
    <section
      className="portability-card portability-workbench"
      aria-label="Conflict workbench"
    >
      <header className="portability-card__header">
        <div>
          <h3>Conflict workbench</h3>
          <p className="portability-card__subtitle">
            {unresolvedCount(conflicts)} of {conflicts.length} differences need
            a decision.
          </p>
        </div>
        <span
          className="portability-badge"
          data-tone={unresolvedCount(conflicts) ? "warn" : "good"}
        >
          {unresolvedCount(conflicts) ? "Review required" : "Ready to merge"}
        </span>
      </header>

      <div className="portability-workbench__filters">
        <input
          type="search"
          aria-label="Filter conflicts"
          placeholder="Filter by reference or reason"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select
          aria-label="Filter by reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        >
          <option value="">All reasons</option>
          {REASON_CODES.map((code) => (
            <option key={code} value={code}>
              {reasonLabel(code)} {counts[code] ? `(${counts[code]})` : ""}
            </option>
          ))}
        </select>
        <select
          aria-label="Default strategy"
          value={strategy}
          onChange={(event) => onStrategy(event.target.value)}
        >
          {["manual", "keep_local", "keep_remote", "merge_fields", "skip"].map(
            (choice) => (
              <option key={choice} value={choice}>
                Default: {resolutionLabel(choice)}
              </option>
            ),
          )}
        </select>
      </div>

      <div className="portability-conflicts">
        {visible.map((conflict) => {
          const rows = diffRows(conflict);
          const suggestion = suggestResolution(conflict, strategy);
          return (
            <article
              key={conflict.ref}
              className="portability-conflict"
              data-reason={conflict.reason}
              data-severity={conflict.severity}
            >
              <header className="portability-conflict__header">
                <div>
                  <h4>{conflict.ref}</h4>
                  <span
                    className="portability-badge"
                    data-tone={reasonTone(conflict.reason)}
                  >
                    {reasonLabel(conflict.reason)}
                  </span>
                </div>
                <span
                  className="portability-badge"
                  data-tone={resolutionTone(conflict.resolution)}
                >
                  {resolutionLabel(conflict.resolution)}
                </span>
              </header>
              <p className="portability-conflict__help">
                {reasonHelp(conflict.reason)}
              </p>
              {conflict.detail && (
                <p className="portability-conflict__detail">
                  {conflict.detail}
                </p>
              )}

              <div
                className="portability-diff"
                role="table"
                aria-label={`Diff for ${conflict.ref}`}
              >
                <div className="portability-diff__head" role="row">
                  <span role="columnheader">Field</span>
                  <span role="columnheader">Common ancestor</span>
                  <span role="columnheader">Local</span>
                  <span role="columnheader">Incoming</span>
                </div>
                {rows.map((row) => (
                  <div
                    key={row.field}
                    className="portability-diff__row"
                    data-overlap={row.overlap}
                    role="row"
                  >
                    <span role="cell">{row.field}</span>
                    <span role="cell">{renderValue(row.base)}</span>
                    <span role="cell" data-changed={row.localChanged}>
                      {renderValue(row.local)}
                    </span>
                    <span role="cell" data-changed={row.remoteChanged}>
                      {renderValue(row.remote)}
                    </span>
                  </div>
                ))}
                {!rows.length && (
                  <p className="portability-empty">
                    No field-level diff available.
                  </p>
                )}
              </div>

              <footer className="portability-conflict__footer">
                <span>Suggested: {resolutionLabel(suggestion)}</span>
                <div className="portability-choices">
                  {RESOLUTIONS.filter((choice) => choice !== "unresolved").map(
                    (choice) => (
                      <button
                        key={choice}
                        type="button"
                        className="portability-button portability-button--small"
                        data-active={conflict.resolution === choice}
                        onClick={() => onResolve(conflict.ref, choice)}
                      >
                        {resolutionLabel(choice)}
                      </button>
                    ),
                  )}
                </div>
              </footer>
            </article>
          );
        })}
        {!visible.length && (
          <p className="portability-empty">No conflicts match this filter.</p>
        )}
      </div>

      <footer className="portability-card__footer">
        <button type="button" className="portability-button" onClick={onApply}>
          Apply decisions
        </button>
      </footer>
    </section>
  );
}
