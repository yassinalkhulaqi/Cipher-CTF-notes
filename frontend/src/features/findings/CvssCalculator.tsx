import { useEffect, useMemo } from "react";

import {
  BASE_METRIC_CODES,
  CVSS_METRICS,
  ENVIRONMENTAL_METRICS,
  THREAT_METRIC,
  formatScore,
  missingBaseMetrics,
  parseVector,
  scoreBand,
  setMetric,
  severityTone,
} from "./logic";
import type { ScorePreview } from "./types";

export interface CvssCalculatorProps {
  vector: string;
  preview: ScorePreview | null;
  onChange: (vector: string) => void;
  onPreview: (vector: string) => Promise<void>;
  disabled?: boolean;
}

function MetricGroup({
  title,
  metrics,
  values,
  onSelect,
  disabled,
}: {
  title: string;
  metrics: Array<{
    code: string;
    label: string;
    values: Array<{ code: string; label: string }>;
  }>;
  values: Record<string, string>;
  onSelect: (code: string, value: string) => void;
  disabled: boolean;
}) {
  return (
    <fieldset className="cvss-group" data-testid={`cvss-group-${title}`}>
      <legend>{title}</legend>
      {metrics.map((metric) => (
        <div
          className="cvss-metric"
          key={metric.code}
          data-metric={metric.code}
        >
          <span className="cvss-metric__label" title={metric.label}>
            {metric.code}
          </span>
          <div
            className="cvss-metric__options"
            role="group"
            aria-label={metric.label}
          >
            {metric.values.map((option) => (
              <button
                type="button"
                key={option.code}
                className="cvss-option"
                data-selected={values[metric.code] === option.code}
                aria-pressed={values[metric.code] === option.code}
                aria-label={`${metric.label}: ${option.label}`}
                disabled={disabled}
                onClick={() => onSelect(metric.code, option.code)}
              >
                {option.code}
              </button>
            ))}
          </div>
        </div>
      ))}
    </fieldset>
  );
}

export function CvssCalculator({
  vector,
  preview,
  onChange,
  onPreview,
  disabled = false,
}: CvssCalculatorProps) {
  const values = useMemo(() => {
    try {
      return parseVector(vector);
    } catch {
      return {};
    }
  }, [vector]);
  const missing = useMemo(() => missingBaseMetrics(vector), [vector]);

  useEffect(() => {
    if (missing.length > 0) return;
    const timer = window.setTimeout(() => {
      void onPreview(vector).catch(() => undefined);
    }, 120);
    return () => window.clearTimeout(timer);
  }, [vector, missing.length, onPreview]);

  const select = (code: string, value: string) => {
    const next = setMetric(vector, code, value);
    onChange(next);
  };

  const liveScore = preview?.final ?? 0;
  const liveBand = preview?.severity ?? scoreBand(liveScore);

  return (
    <section
      className="cvss-calculator"
      data-testid="cvss-calculator"
      data-complete={missing.length === 0}
    >
      <header className="cvss-calculator__header">
        <div>
          <h3>CVSS v4.0 calculator</h3>
          <p className="cvss-calculator__vector" aria-live="polite">
            {vector || "No vector selected"}
          </p>
        </div>
        <div
          className="cvss-calculator__score"
          data-tone={severityTone(liveBand)}
        >
          <strong>{formatScore(liveScore)}</strong>
          <span>{liveBand}</span>
        </div>
      </header>

      {missing.length > 0 && (
        <p className="cvss-calculator__hint" role="status">
          Select {missing.join(", ")} to compute a score.
        </p>
      )}

      <div className="cvss-calculator__groups">
        <MetricGroup
          title="Exploitability and impact"
          metrics={CVSS_METRICS}
          values={values}
          onSelect={select}
          disabled={disabled}
        />
        <MetricGroup
          title="Threat"
          metrics={[THREAT_METRIC]}
          values={values}
          onSelect={select}
          disabled={disabled}
        />
        <MetricGroup
          title="Environmental"
          metrics={ENVIRONMENTAL_METRICS}
          values={values}
          onSelect={select}
          disabled={disabled}
        />
      </div>

      <footer className="cvss-calculator__footer">
        <span data-testid="cvss-nomenclature">
          {preview?.nomenclature ?? "CVSS-B"}
        </span>
        <span data-testid="cvss-macro">{preview?.macro_vector ?? "—"}</span>
        <span>{BASE_METRIC_CODES.length} base metrics</span>
      </footer>
    </section>
  );
}
