/** Redaction and consent policy editor. */

import { useState } from "react";

import { V3Panel } from "../../v3/components/V3Panel";
import {
  CONSENT_SCOPES,
  consentLabel,
  effectiveRules,
  redactionNotice,
} from "./pure";
import type { PolicyPreview, PolicyRule, PolicySnapshot } from "./types";

export interface PolicyEditorProps {
  snapshot: PolicySnapshot;
  preview: PolicyPreview | null;
  busy: boolean;
  onSave: (rules: PolicyRule[]) => void;
  onPreview: (text: string, scope: string) => void;
}

const EMPTY_RULE: PolicyRule = {
  rule_id: "",
  pattern: "*",
  mode: "mask",
  priority: 0,
  enabled: true,
  reason: "",
};

export function PolicyEditor({
  snapshot,
  preview,
  busy,
  onSave,
  onPreview,
}: PolicyEditorProps) {
  const [draft, setDraft] = useState<PolicyRule[]>(snapshot.rules);
  const [sample, setSample] = useState("");
  const [scope, setScope] = useState("log_content");
  const rules = effectiveRules({ ...snapshot, rules: draft });
  const granted = new Set(snapshot.consents.granted);

  const updateRule = (index: number, patch: Partial<PolicyRule>) => {
    setDraft((current) =>
      current.map((rule, position) =>
        position === index ? { ...rule, ...patch } : rule,
      ),
    );
  };

  return (
    <V3Panel
      title="Redaction policy"
      subtitle="Rules are ordered by priority; higher values win."
      kind="finding"
    >
      <div className="vs-policy__patterns">
        <h3>Detectors</h3>
        <ul>
          {snapshot.patterns.map((pattern) => (
            <li key={pattern.name} data-enabled={pattern.enabled}>
              <strong>{pattern.name}</strong>
              <span>{pattern.kind}</span>
              <span>{pattern.severity}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="vs-policy__rules">
        <h3>Rules</h3>
        {rules.map((rule, index) => (
          <div className="vs-rule" key={rule.rule_id}>
            <input
              aria-label="Rule id"
              value={rule.rule_id}
              onChange={(event) =>
                updateRule(index, { rule_id: event.target.value })
              }
            />
            <select
              aria-label="Pattern"
              value={rule.pattern}
              onChange={(event) =>
                updateRule(index, { pattern: event.target.value })
              }
            >
              <option value="*">all patterns</option>
              {snapshot.patterns.map((pattern) => (
                <option value={pattern.name} key={pattern.name}>
                  {pattern.name}
                </option>
              ))}
            </select>
            <select
              aria-label="Mode"
              value={rule.mode}
              onChange={(event) =>
                updateRule(index, {
                  mode: event.target.value as PolicyRule["mode"],
                })
              }
            >
              <option value="mask">mask</option>
              <option value="hash">hash</option>
              <option value="remove">remove</option>
            </select>
            <input
              aria-label="Priority"
              type="number"
              value={rule.priority}
              onChange={(event) =>
                updateRule(index, { priority: Number(event.target.value) })
              }
            />
            <label className="vs-checkbox">
              <input
                type="checkbox"
                checked={rule.enabled}
                onChange={(event) =>
                  updateRule(index, { enabled: event.target.checked })
                }
              />
              <span>enabled</span>
            </label>
            {!rule.effective && (
              <span className="vs-locked">Pattern unavailable</span>
            )}
          </div>
        ))}
        <button
          type="button"
          onClick={() => setDraft((current) => [...current, { ...EMPTY_RULE }])}
        >
          Add rule
        </button>
      </div>
      <div className="vs-policy__consents">
        <h3>Consent gates</h3>
        {CONSENT_SCOPES.map((item) => (
          <span data-granted={granted.has(item.value)} key={item.value}>
            {consentLabel(item, granted.has(item.value))}
          </span>
        ))}
      </div>
      <div className="vs-policy__preview">
        <label className="vs-field">
          <span>Preview sample</span>
          <textarea
            value={sample}
            onChange={(event) => setSample(event.target.value)}
            rows={3}
          />
        </label>
        <select
          value={scope}
          onChange={(event) => setScope(event.target.value)}
        >
          {CONSENT_SCOPES.map((item) => (
            <option value={item.value} key={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => onPreview(sample, scope)}
          disabled={busy || sample.length === 0}
        >
          Preview redaction
        </button>
        {preview && (
          <div className="vs-policy__result">
            <pre>{preview.preview.text}</pre>
            <span>{redactionNotice(preview.preview.redactions)}</span>
            <span>Allowed: {String(preview.decision.allowed)}</span>
          </div>
        )}
      </div>
      <button type="button" onClick={() => onSave(draft)} disabled={busy}>
        Save policy
      </button>
    </V3Panel>
  );
}
