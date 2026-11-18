import { useMemo, useState } from "react";
import type { RedactionRule, RedactionSummary } from "./types";
import {
  redactPreviewLabel,
  redactionSummaryText,
  uniqueStrings,
} from "./helpers";

interface Props {
  text: string;
  rules: RedactionRule[];
  summary: RedactionSummary | null;
  loading?: boolean;
  onChangeText: (value: string) => void;
  onToggleRule: (name: string, enabled: boolean) => void;
  onApply: () => void;
  onCopy?: (value: string) => void;
}

export function RedactionControls({
  text,
  rules,
  summary,
  loading = false,
  onChangeText,
  onToggleRule,
  onApply,
  onCopy,
}: Props) {
  const [scopeFilter, setScopeFilter] = useState("all");
  const [showOriginal, setShowOriginal] = useState(false);

  const scopes = useMemo(
    () =>
      uniqueStrings([
        "all",
        ...rules.map((rule) => String(rule.scope || "all")),
      ]),
    [rules],
  );

  const visibleRules = useMemo(() => {
    if (scopeFilter === "all") return rules;
    return rules.filter((rule) => (rule.scope || "all") === scopeFilter);
  }, [rules, scopeFilter]);

  const previewText = showOriginal ? text : summary?.text || text;

  return (
    <section
      className="security-panel redaction-controls"
      aria-label="Redaction controls"
    >
      <header className="security-panel__header">
        <div>
          <h2>Redaction Controls</h2>
          <p className="security-panel__subtitle">
            {redactionSummaryText(summary)}
          </p>
        </div>
        <div className="button-group">
          <button
            type="button"
            className="button"
            onClick={onApply}
            disabled={loading}
          >
            {loading ? "Applying…" : "Apply redactions"}
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={() => onCopy?.(previewText)}
            disabled={!previewText}
          >
            Copy output
          </button>
        </div>
      </header>

      <div className="security-grid">
        <label className="field field--stacked">
          <span className="field__label">Source text</span>
          <textarea
            className="input"
            rows={10}
            value={text}
            onChange={(event) => onChangeText(event.target.value)}
          />
        </label>
        <label className="field field--stacked">
          <span className="field__label">
            Preview ({redactPreviewLabel(summary)})
          </span>
          <textarea className="input" rows={10} value={previewText} readOnly />
        </label>
      </div>

      <div className="toolbar">
        <label className="field">
          <span className="field__label">Scope</span>
          <select
            className="input"
            value={scopeFilter}
            onChange={(event) => setScopeFilter(event.target.value)}
          >
            {scopes.map((scope) => (
              <option key={scope} value={scope}>
                {scope}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={showOriginal}
            onChange={(event) => setShowOriginal(event.target.checked)}
          />
          <span>Show original in preview pane</span>
        </label>
      </div>

      <div className="security-columns">
        <div className="security-column">
          <h3>Rules</h3>
          {visibleRules.length === 0 ? (
            <p className="empty-state">No redaction rules available.</p>
          ) : (
            <ul className="rule-list">
              {visibleRules.map((rule) => {
                const enabled = rule.enabled !== false;
                return (
                  <li key={rule.name} className="rule-item">
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(event) =>
                          onToggleRule(rule.name, event.target.checked)
                        }
                      />
                      <span>
                        <strong>{rule.name}</strong>
                        <small>
                          {rule.description || rule.regex || rule.pattern || ""}
                        </small>
                      </span>
                    </label>
                    <div className="rule-item__meta">
                      <span>Scope: {rule.scope || "all"}</span>
                      <span>Replacement: {rule.replacement}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <div className="security-column">
          <h3>Applied replacements</h3>
          {!summary || summary.total_replacements === 0 ? (
            <p className="empty-state">No replacements yet.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Rule</th>
                  <th>Count</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(summary.counts).map(([name, count]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>{count}</td>
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
