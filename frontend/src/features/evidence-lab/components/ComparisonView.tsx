/** Evidence bundle comparison view. */

import { useMemo, useState } from "react";

import {
  compareHeadline,
  compareRows,
  fingerprintPair,
  sizeDeltaTotal,
} from "../compareModel";
import { formatSignedBytes } from "../format";
import type { BundleDiffData } from "../types";

export interface ComparisonViewProps {
  diff: BundleDiffData | null;
  onCompare?: (left: string, right: string) => void;
}

export function ComparisonView({ diff, onCompare }: ComparisonViewProps) {
  const [kind, setKind] = useState("all");
  const rows = useMemo(() => compareRows(diff), [diff]);
  const visible = useMemo(
    () => rows.filter((row) => kind === "all" || row.kind === kind),
    [rows, kind],
  );
  const fingerprints = fingerprintPair(diff);

  if (!diff) {
    return (
      <div className="elf-compare__empty" data-testid="compare-empty">
        Compare two evidence bundles to see hash-level changes.
      </div>
    );
  }

  return (
    <div className="elf-compare" data-testid="comparison-view">
      <header className="elf-compare__header">
        <div>
          <h3>{compareHeadline(diff)}</h3>
          <p>
            {diff.left_id} <span aria-hidden="true">→</span> {diff.right_id} ·{" "}
            {formatSignedBytes(sizeDeltaTotal(diff))} net
          </p>
        </div>
        <span className="elf-pill" data-tone={diff.identical ? "good" : "warn"}>
          {diff.identical ? "IDENTICAL" : "CHANGED"}
        </span>
      </header>
      <div
        className="elf-compare__filters"
        role="group"
        aria-label="Filter differences"
      >
        {["all", "added", "removed", "modified", "unchanged"].map((value) => (
          <button
            key={value}
            type="button"
            className="elf-button elf-button--small"
            data-active={kind === value}
            data-testid={`compare-filter-${value}`}
            onClick={() => setKind(value)}
          >
            {value} ({diff.counts[value] ?? 0})
          </button>
        ))}
        {onCompare && (
          <button
            type="button"
            className="elf-button"
            data-testid="compare-refresh"
            onClick={() => onCompare(diff.left_id, diff.right_id)}
          >
            Refresh
          </button>
        )}
      </div>
      <div
        className="elf-compare__table"
        role="table"
        data-testid="compare-table"
      >
        <div className="elf-compare__tr elf-compare__tr--head" role="row">
          <span role="columnheader">Key</span>
          <span role="columnheader">Change</span>
          <span role="columnheader">Left SHA-256</span>
          <span role="columnheader">Right SHA-256</span>
          <span role="columnheader">Δ size</span>
        </div>
        {visible.map((row) => (
          <div
            key={row.key}
            className="elf-compare__tr"
            role="row"
            data-testid="compare-row"
            data-kind={row.kind}
            data-tone={row.tone}
          >
            <span role="cell" title={row.key}>
              {row.key}
            </span>
            <span role="cell">{row.kind}</span>
            <span role="cell">
              <code>{row.leftHash}</code>
            </span>
            <span role="cell">
              <code>{row.rightHash}</code>
            </span>
            <span role="cell">{row.sizeLabel}</span>
          </div>
        ))}
        {visible.length === 0 && (
          <p className="elf-empty" data-testid="compare-empty-filter">
            No entries of this change type.
          </p>
        )}
      </div>
      <footer className="elf-compare__footer">
        <span>
          Left fingerprint{" "}
          <code title={diff.fingerprint_left}>{fingerprints[0]}</code>
        </span>
        <span>
          Right fingerprint{" "}
          <code title={diff.fingerprint_right}>{fingerprints[1]}</code>
        </span>
        <span>{diff.deltas.length} entries compared</span>
      </footer>
    </div>
  );
}
