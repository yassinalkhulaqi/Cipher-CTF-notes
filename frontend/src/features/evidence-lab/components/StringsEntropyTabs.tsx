/** Strings and entropy tabs with searchable hit list and histogram bars. */

import { useMemo } from "react";

import {
  entropyBars,
  entropySummary,
  entropyTone,
  filterHits,
  stringTabs,
} from "../stringsModel";
import { formatBytes, formatOffset, formatEntropy, percent } from "../format";
import type { LabTab } from "../state";
import type { EntropyReportData, EvidenceReportData } from "../types";

export interface StringsEntropyProps {
  tab: LabTab;
  report: EvidenceReportData | null;
  query: string;
  kind: string;
  onTab: (tab: LabTab) => void;
  onQuery: (value: string) => void;
  onKind: (value: string) => void;
  onHitClick: (offset: number) => void;
}

export function StringsEntropyTabs({
  tab,
  report,
  query,
  kind,
  onTab,
  onQuery,
  onKind,
  onHitClick,
}: StringsEntropyProps) {
  const scan = report?.strings ?? null;
  const entropy: EntropyReportData | null = report?.entropy ?? null;
  const tabs = useMemo(() => stringTabs(scan), [scan]);
  const hits = useMemo(
    () => (scan ? filterHits(scan.hits, query, kind) : []),
    [scan, query, kind],
  );
  const bars = useMemo(() => entropyBars(entropy?.buckets ?? []), [entropy]);

  return (
    <div className="elf-tabs" data-testid="strings-entropy-tabs">
      <div
        className="elf-tabs__header"
        role="tablist"
        aria-label="Inspection views"
      >
        {(["hex", "strings", "entropy"] as LabTab[]).map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            data-testid={`tab-${id}`}
            className="elf-tabs__tab"
            data-active={tab === id}
            onClick={() => onTab(id)}
          >
            {id.charAt(0).toUpperCase() + id.slice(1)}
          </button>
        ))}
      </div>
      {tab === "strings" && (
        <div
          className="elf-strings"
          role="tabpanel"
          data-testid="strings-panel"
        >
          <div className="elf-strings__controls">
            <input
              aria-label="Filter strings"
              data-testid="string-filter"
              placeholder="Filter strings"
              value={query}
              onChange={(event) => onQuery(event.target.value)}
            />
            <select
              aria-label="String kind"
              data-testid="string-kind"
              value={kind}
              onChange={(event) => onKind(event.target.value)}
            >
              {tabs.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label} ({item.count})
                </option>
              ))}
            </select>
          </div>
          <div className="elf-strings__list" data-testid="string-hits">
            {hits.map((hit) => (
              <button
                key={`${hit.offset}-${hit.kind}`}
                type="button"
                className="elf-string-hit"
                data-testid="string-hit"
                data-kind={hit.kind}
                onClick={() => onHitClick(hit.offset)}
              >
                <span className="elf-string-hit__offset">
                  0x{formatOffset(hit.offset)}
                </span>
                <span className="elf-string-hit__kind">{hit.kind}</span>
                <span className="elf-string-hit__text">{hit.text}</span>
                <span className="elf-string-hit__len">
                  {formatBytes(hit.length)}
                </span>
              </button>
            ))}
            {hits.length === 0 && (
              <p className="elf-empty" data-testid="strings-empty">
                No printable strings match this filter.
              </p>
            )}
          </div>
        </div>
      )}
      {tab === "entropy" && (
        <div
          className="elf-entropy"
          role="tabpanel"
          data-testid="entropy-panel"
        >
          <div
            className="elf-entropy__headline"
            data-tone={entropyTone(entropy)}
          >
            <strong>
              {entropy ? formatEntropy(entropy.entropy) : "No sample"}
            </strong>
            <span>{entropySummary(entropy)}</span>
          </div>
          <div className="elf-entropy__bars" data-testid="entropy-bars">
            {bars.map((bar) => (
              <div
                key={bar.label}
                className="elf-entropy__bar-row"
                data-label={bar.label}
              >
                <span className="elf-entropy__bar-label">{bar.label}</span>
                <div className="elf-entropy__bar-track">
                  <div
                    className="elf-entropy__bar-fill"
                    style={{ width: percent(bar.ratio) }}
                    data-testid="entropy-bar"
                  />
                </div>
                <span className="elf-entropy__bar-count">{bar.count}</span>
              </div>
            ))}
          </div>
          <dl className="elf-entropy__stats">
            <div>
              <dt>Sampled</dt>
              <dd>{entropy ? formatBytes(entropy.sample_bytes) : "-"}</dd>
            </div>
            <div>
              <dt>Total</dt>
              <dd>{entropy ? formatBytes(entropy.total_bytes) : "-"}</dd>
            </div>
            <div>
              <dt>Normalized</dt>
              <dd>{entropy ? entropy.normalized.toFixed(3) : "-"}</dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  );
}
