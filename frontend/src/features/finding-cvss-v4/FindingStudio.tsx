import { useMemo, useReducer } from "react";
import type { ReactNode } from "react";

import { FindingClient } from "./client";
import type { FindingV4, RetestVerdictV4 } from "./client";
import {
  LIFECYCLE_STATES,
  METRIC_DEFINITIONS,
  estimateScore,
  formatVector,
  initialFindingStudioState,
  legalTransitions,
  reduceFindingStudio,
  scorePercent,
  selectedFinding,
  severityFromScore,
  severityTone,
} from "./state";
import type { MetricCode, MetricDefinition } from "./state";

export interface FindingStudioProps {
  client?: FindingClient;
  heading?: string;
}

function Panel({
  title,
  children,
  subtitle,
}: {
  title: string;
  children: ReactNode;
  subtitle?: string;
}) {
  return (
    <section className="studio-panel v4-panel" data-panel={title}>
      <header className="studio-panel__header">
        <h3>{title}</h3>
        {subtitle ? (
          <span className="studio-panel__subtitle">{subtitle}</span>
        ) : null}
      </header>
      <div className="studio-panel__body">{children}</div>
    </section>
  );
}

function MetricSelect({
  definition,
  value,
  onChange,
}: {
  definition: MetricDefinition;
  value: string;
  onChange: (code: MetricCode, value: string) => void;
}) {
  return (
    <label className="studio-metric" data-metric={definition.code}>
      <span className="studio-metric__code">{definition.code}</span>
      <span className="studio-metric__label">{definition.label}</span>
      <select
        className="studio-metric__select v4-focus-ring"
        value={value}
        aria-label={definition.label}
        onChange={(event) => onChange(definition.code, event.target.value)}
      >
        {definition.options.map((option) => (
          <option key={option.code} value={option.code}>
            {option.code} — {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function ScoreGauge({ score, severity }: { score: number; severity: string }) {
  const tone = severityTone(severity as Parameters<typeof severityTone>[0]);
  const dash = `${scorePercent(score) * 1.57} 157`;
  return (
    <div
      className="studio-gauge"
      data-severity={severity}
      data-testid="score-gauge"
    >
      <svg
        viewBox="0 0 120 72"
        role="img"
        aria-label={`Score ${score.toFixed(1)}`}
      >
        <path className="studio-gauge__track" d="M10 62 A50 50 0 0 1 110 62" />
        <path
          className="studio-gauge__value"
          d="M10 62 A50 50 0 0 1 110 62"
          style={{ stroke: tone, strokeDasharray: dash }}
        />
      </svg>
      <div className="studio-gauge__readout">
        <strong style={{ color: tone }}>{score.toFixed(1)}</strong>
        <span>{severity}</span>
      </div>
    </div>
  );
}

export function FindingStudio({
  client,
  heading = "Finding studio",
}: FindingStudioProps) {
  const [state, dispatch] = useReducer(
    reduceFindingStudio,
    undefined,
    initialFindingStudioState,
  );

  const vector = useMemo(() => formatVector(state.metrics), [state.metrics]);
  const liveScore = useMemo(
    () => estimateScore(state.metrics),
    [state.metrics],
  );
  const liveSeverity = severityFromScore(liveScore);
  const active = selectedFinding(state);
  const targets = active ? legalTransitions(active.lifecycle_state) : [];
  const displayScore = state.score ? state.score.final : liveScore;
  const displaySeverity = state.score ? state.score.severity : liveSeverity;

  const reportError = (error: unknown, fallback: string) => {
    const message = error instanceof Error ? error.message : fallback;
    dispatch({ type: "set-error", value: message });
    dispatch({ type: "log", message: `Error: ${message}` });
  };

  const refresh = async () => {
    if (!client) return;
    dispatch({ type: "set-busy", value: true });
    try {
      const page = await client.list();
      dispatch({ type: "load-findings", findings: page.data.items });
      dispatch({ type: "log", message: `Loaded ${page.data.total} findings` });
      dispatch({ type: "set-error", value: null });
    } catch (error) {
      reportError(error, "refresh failed");
    } finally {
      dispatch({ type: "set-busy", value: false });
    }
  };

  const create = async () => {
    if (!client || !state.title.trim()) return;
    dispatch({ type: "set-busy", value: true });
    try {
      const result = await client.create({
        title: state.title,
        description: state.description,
        vector,
      });
      dispatch({ type: "apply-finding", finding: result.finding });
      dispatch({ type: "set-score", score: result.score ?? null });
      dispatch({ type: "log", message: `Created ${result.finding.title}` });
      dispatch({ type: "set-error", value: null });
    } catch (error) {
      reportError(error, "create failed");
    } finally {
      dispatch({ type: "set-busy", value: false });
    }
  };

  const scoreSelected = async () => {
    if (!client || !active) return;
    try {
      const result = await client.score(active.id);
      dispatch({ type: "apply-finding", finding: result.finding });
      dispatch({ type: "set-score", score: result.score ?? null });
      dispatch({ type: "log", message: `Scored ${active.id}` });
    } catch (error) {
      reportError(error, "score failed");
    }
  };

  const moveTo = async (stateName: FindingV4["lifecycle_state"]) => {
    if (!client || !active) return;
    try {
      const result = await client.transition(active.id, stateName);
      dispatch({ type: "apply-finding", finding: result.finding });
      dispatch({ type: "log", message: `${active.id} → ${stateName}` });
    } catch (error) {
      reportError(error, "transition failed");
    }
  };

  const saveRemediation = async () => {
    if (!client || !active) return;
    try {
      const result = await client.assignRemediation(
        active.id,
        state.remediationDue,
        state.remediationNotes,
      );
      dispatch({ type: "apply-finding", finding: result.finding });
      dispatch({
        type: "log",
        message: `Remediation assigned for ${active.id}`,
      });
    } catch (error) {
      reportError(error, "remediation failed");
    }
  };

  const retest = async () => {
    if (!client || !active) return;
    try {
      const result = await client.retest(
        active.id,
        state.verdict,
        state.retestNote,
      );
      dispatch({ type: "apply-finding", finding: result.finding });
      dispatch({
        type: "log",
        message: `Retest ${state.verdict} for ${active.id}`,
      });
    } catch (error) {
      reportError(error, "retest failed");
    }
  };

  return (
    <div className="finding-studio" data-testid="finding-studio">
      <header className="finding-studio__header">
        <div>
          <h2>{heading}</h2>
          <p className="finding-studio__vector" aria-live="polite">
            {vector}
          </p>
        </div>
        <button
          type="button"
          className="v4-btn v4-focus-ring"
          disabled={state.busy}
          onClick={() => void refresh()}
        >
          Refresh
        </button>
      </header>

      {state.error ? (
        <p className="finding-studio__error" role="alert">
          {state.error}
        </p>
      ) : null}

      <div className="finding-studio__layout">
        <div className="finding-studio__column">
          <Panel
            title="Score"
            subtitle={state.score?.nomenclature ?? "live estimate"}
          >
            <ScoreGauge score={displayScore} severity={displaySeverity} />
            <dl className="studio-score-breakdown">
              <div>
                <dt>Base</dt>
                <dd>{(state.score?.base ?? liveScore).toFixed(1)}</dd>
              </div>
              <div>
                <dt>Threat</dt>
                <dd>{(state.score?.threat ?? liveScore).toFixed(1)}</dd>
              </div>
              <div>
                <dt>Environmental</dt>
                <dd>{(state.score?.environmental ?? liveScore).toFixed(1)}</dd>
              </div>
            </dl>
          </Panel>

          <Panel title="Vector editor" subtitle="CVSS v4.0">
            <div className="studio-metrics">
              {METRIC_DEFINITIONS.map((definition) => (
                <MetricSelect
                  key={definition.code}
                  definition={definition}
                  value={state.metrics[definition.code]}
                  onChange={(code, value) =>
                    dispatch({ type: "set-metric", code, value })
                  }
                />
              ))}
            </div>
          </Panel>
        </div>

        <div className="finding-studio__column">
          <Panel title="New finding">
            <label className="studio-field">
              <span>Title</span>
              <input
                className="v4-focus-ring"
                value={state.title}
                onChange={(event) =>
                  dispatch({ type: "set-title", value: event.target.value })
                }
              />
            </label>
            <label className="studio-field">
              <span>Description</span>
              <textarea
                className="v4-focus-ring"
                rows={3}
                value={state.description}
                onChange={(event) =>
                  dispatch({
                    type: "set-description",
                    value: event.target.value,
                  })
                }
              />
            </label>
            <button
              type="button"
              className="v4-btn v4-btn--primary v4-focus-ring"
              disabled={state.busy || !state.title.trim()}
              onClick={() => void create()}
            >
              Create finding
            </button>
          </Panel>

          <Panel title="Lifecycle">
            {active ? (
              <>
                <div className="studio-chips" aria-label="Lifecycle states">
                  {LIFECYCLE_STATES.map((stateName) => (
                    <span
                      key={stateName}
                      className="studio-chip v4-chip"
                      data-active={stateName === active.lifecycle_state}
                    >
                      {stateName.replace("_", " ")}
                    </span>
                  ))}
                </div>
                <div className="studio-transitions">
                  {targets.length === 0 ? (
                    <span className="studio-hint">
                      No transitions available.
                    </span>
                  ) : (
                    targets.map((stateName) => (
                      <button
                        type="button"
                        key={stateName}
                        className="v4-btn v4-focus-ring"
                        onClick={() => void moveTo(stateName)}
                      >
                        Move to {stateName.replace("_", " ")}
                      </button>
                    ))
                  )}
                </div>
                <button
                  type="button"
                  className="v4-btn v4-focus-ring"
                  onClick={() => void scoreSelected()}
                >
                  Recalculate score
                </button>
              </>
            ) : (
              <p className="studio-hint">
                Select a finding to manage its lifecycle.
              </p>
            )}
          </Panel>

          <Panel title="Remediation">
            <label className="studio-field">
              <span>Due date</span>
              <input
                type="date"
                className="v4-focus-ring"
                value={state.remediationDue}
                onChange={(event) =>
                  dispatch({ type: "set-due", value: event.target.value })
                }
              />
            </label>
            <label className="studio-field">
              <span>Notes</span>
              <textarea
                className="v4-focus-ring"
                rows={3}
                value={state.remediationNotes}
                onChange={(event) =>
                  dispatch({ type: "set-notes", value: event.target.value })
                }
              />
            </label>
            <button
              type="button"
              className="v4-btn v4-focus-ring"
              disabled={!active}
              onClick={() => void saveRemediation()}
            >
              Save remediation
            </button>
          </Panel>

          <Panel title="Retest">
            <label className="studio-field">
              <span>Verdict</span>
              <select
                className="v4-focus-ring"
                value={state.verdict}
                onChange={(event) =>
                  dispatch({
                    type: "set-verdict",
                    value: event.target.value as RetestVerdictV4,
                  })
                }
              >
                <option value="pass">pass</option>
                <option value="fail">fail</option>
                <option value="partial">partial</option>
              </select>
            </label>
            <label className="studio-field">
              <span>Retest note</span>
              <textarea
                className="v4-focus-ring"
                rows={2}
                value={state.retestNote}
                onChange={(event) =>
                  dispatch({
                    type: "set-retest-note",
                    value: event.target.value,
                  })
                }
              />
            </label>
            <button
              type="button"
              className="v4-btn v4-focus-ring"
              disabled={!active}
              onClick={() => void retest()}
            >
              Record retest
            </button>
          </Panel>
        </div>

        <div className="finding-studio__column">
          <Panel title="Findings" subtitle={`${state.findings.length} total`}>
            {state.findings.length === 0 ? (
              <p className="studio-hint">No findings yet.</p>
            ) : (
              <ul className="studio-findings">
                {state.findings.map((finding) => (
                  <li key={finding.id}>
                    <button
                      type="button"
                      className="studio-finding v4-focus-ring"
                      data-active={finding.id === state.selectedId}
                      onClick={() =>
                        dispatch({ type: "select", id: finding.id })
                      }
                    >
                      <span className="studio-finding__title">
                        {finding.title}
                      </span>
                      <span className="studio-finding__meta">
                        {finding.severity} ·{" "}
                        {finding.lifecycle_state.replace("_", " ")} ·{" "}
                        {finding.retest_count} retests
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Activity log" subtitle={`${state.log.length} entries`}>
            {state.log.length === 0 ? (
              <p className="studio-hint">No activity recorded.</p>
            ) : (
              <ol className="studio-log">
                {state.log.map((entry, index) => (
                  <li key={`${index}-${entry}`}>{entry}</li>
                ))}
              </ol>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
