/** The v4 playbook automation surface: DAG canvas, trace, schedules and runs. */

import { useMemo, useState } from "react";
import type { CSSProperties } from "react";

import type {
  DagNodeV4,
  PlaybookDagV4,
  RunRecordV4,
  ScheduleV4,
  TraceStepV4,
} from "./client";
import {
  canDryRun,
  edgeSegments,
  layoutDag,
  scheduleLabel,
  selectedNode,
  statusTone,
  traceSummary,
  topologicalOrder,
  visibleRuns,
  type PlaybookAutomationAction,
  type PlaybookAutomationState,
} from "./state";
import "./playbook-automation.css";

const NODE_KINDS = [
  "setup",
  "collect",
  "analyze",
  "enrich",
  "report",
  "notify",
] as const;

export interface DagCanvasProps {
  state: PlaybookAutomationState;
  dispatch: (action: PlaybookAutomationAction) => void;
  onDryRun: () => void;
  onRefresh: () => void;
  onScheduleChange?: (schedule: ScheduleV4) => void;
}

export function canvasSummary(state: PlaybookAutomationState): {
  nodes: number;
  edges: number;
  steps: number;
  runs: number;
  order: string;
} {
  return {
    nodes: state.dag.nodes.length,
    edges: state.dag.edges.length,
    steps: state.trace.length,
    runs: state.runs.length,
    order: topologicalOrder(state.dag).join(" -> "),
  };
}

export function traceRows(trace: TraceStepV4[]): Array<{
  id: string;
  label: string;
  tone: string;
  detail: string;
  percent: number;
  durationMs: number;
}> {
  const summary = traceSummary(trace);
  return trace.map((step) => ({
    id: step.node_id,
    label: step.node_id,
    tone: statusTone(step.status),
    detail: step.detail,
    percent: summary.maxDurationMs
      ? Math.round((step.duration_ms / summary.maxDurationMs) * 100)
      : 0,
    durationMs: step.duration_ms,
  }));
}

function defaultSchedule(dag: PlaybookDagV4): ScheduleV4 {
  return {
    id: `schedule-${dag.id}`,
    playbook_id: dag.id,
    frequency: "daily",
    interval_minutes: 60,
    minute: 0,
    hour: 9,
    day_of_week: [],
    day_of_month: 1,
    next_run: "",
    enabled: true,
  };
}

function nodeStyle(column: number, row: number): CSSProperties {
  return {
    gridColumn: String(column + 1),
    gridRow: String(row + 1),
  };
}

function edgeStyle(column: number, row: number, span: number): CSSProperties {
  return {
    gridColumn: `${column + 1} / span ${span}`,
    gridRow: String(row + 1),
  } as CSSProperties;
}

/** Render one dependency edge as a CSS-drawn connector between two cards. */
export function DagCanvas({
  state,
  dispatch,
  onDryRun,
  onRefresh,
  onScheduleChange,
}: DagCanvasProps) {
  const [scheduleDraft, setScheduleDraft] = useState<ScheduleV4>(() => {
    const existing = state.schedules[0];
    return existing ? { ...existing } : defaultSchedule(state.dag);
  });
  const cells = useMemo(() => layoutDag(state.dag), [state.dag]);
  const segments = useMemo(
    () => edgeSegments(state.dag, cells),
    [state.dag, cells],
  );
  const summary = useMemo(() => traceSummary(state.trace), [state.trace]);
  const rows = useMemo(() => traceRows(state.trace), [state.trace]);
  const runs = useMemo(() => visibleRuns(state), [state]);
  const active = selectedNode(state);
  const overview = canvasSummary(state);
  const errors =
    state.validation?.issues.filter((issue) => issue.severity === "error") ??
    [];

  const updateDraft = (patch: Partial<ScheduleV4>) => {
    setScheduleDraft((current) => ({ ...current, ...patch }));
  };

  const commitSchedule = () => {
    dispatch({ type: "update-schedule", schedule: scheduleDraft });
    onScheduleChange?.(scheduleDraft);
  };

  const addNode = () => {
    const nextIndex = state.dag.nodes.length + 1;
    const node: DagNodeV4 = {
      id: `node-${nextIndex}`,
      label: `Step ${nextIndex}`,
      kind: "collect",
      depends_on: [],
      params: {},
    };
    dispatch({ type: "add-node", node });
  };

  return (
    <section
      className="pa"
      data-automation="surface"
      aria-label="Playbook automation"
    >
      <header className="pa__header">
        <div>
          <h1 className="pa__title">Playbook automation</h1>
          <p className="pa__lede">
            Declarative DAGs, deterministic dry runs, and schedules. No commands
            are executed.
          </p>
        </div>
        <div className="pa__stats" aria-label="Automation summary">
          <span className="pa__stat" data-stat="nodes">
            Nodes <strong>{overview.nodes}</strong>
          </span>
          <span className="pa__stat" data-stat="edges">
            Edges <strong>{overview.edges}</strong>
          </span>
          <span className="pa__stat" data-stat="steps">
            Trace <strong>{overview.steps}</strong>
          </span>
          <span className="pa__stat" data-stat="runs">
            Runs <strong>{overview.runs}</strong>
          </span>
        </div>
      </header>

      {state.error && (
        <p
          className="pa__banner pa__banner--bad"
          role="alert"
          data-automation="error"
        >
          {state.error}
        </p>
      )}
      {errors.length > 0 && (
        <ul
          className="pa__banner pa__banner--warn"
          data-automation="validation-issues"
        >
          {errors.map((issue) => (
            <li key={issue.code}>{issue.message}</li>
          ))}
        </ul>
      )}

      <div className="pa__grid">
        <div className="pa__panel pa__panel--canvas">
          <div className="pa__panel-head">
            <h2>Dependency canvas</h2>
            <button type="button" data-action="add-node" onClick={addNode}>
              Add node
            </button>
          </div>
          <div className="pa__canvas" data-automation="dag-canvas">
            {segments.map((segment) => (
              <div
                key={segment.id}
                className="pa__edge"
                style={edgeStyle(segment.column, segment.row, segment.span)}
                data-edge={segment.id}
                aria-label={segment.label}
                role="presentation"
              />
            ))}
            {cells.map((cell) => (
              <button
                key={cell.id}
                type="button"
                className={`pa__node${state.selectedNodeId === cell.id ? " pa__node--selected" : ""}`}
                style={nodeStyle(cell.column, cell.row)}
                data-node={cell.id}
                aria-pressed={state.selectedNodeId === cell.id}
                onClick={() => dispatch({ type: "select-node", id: cell.id })}
              >
                <span className="pa__node-kind" data-kind={cell.kind}>
                  {cell.kind}
                </span>
                <span className="pa__node-label">{cell.label}</span>
                <span className="pa__node-id">{cell.id}</span>
              </button>
            ))}
            {cells.length === 0 && (
              <p className="pa__empty">
                Add a node to begin drafting a playbook.
              </p>
            )}
          </div>
          {active && (
            <div className="pa__inspector" data-automation="node-inspector">
              <h3>{active.label}</h3>
              <label htmlFor="pa-node-label">Label</label>
              <input
                id="pa-node-label"
                value={active.label}
                onChange={(event) =>
                  dispatch({
                    type: "add-node",
                    node: { ...active, label: event.target.value },
                  })
                }
              />
              <label htmlFor="pa-node-kind">Kind</label>
              <select
                id="pa-node-kind"
                value={active.kind}
                onChange={(event) =>
                  dispatch({
                    type: "add-node",
                    node: {
                      ...active,
                      kind: event.target.value as DagNodeV4["kind"],
                    },
                  })
                }
              >
                {NODE_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
              <fieldset className="pa__dependencies">
                <legend>Depends on</legend>
                {state.dag.nodes
                  .filter((node) => node.id !== active.id)
                  .map((node) => (
                    <label key={node.id}>
                      <input
                        type="checkbox"
                        checked={active.depends_on.includes(node.id)}
                        onChange={() =>
                          dispatch({
                            type: "toggle-dependency",
                            from: node.id,
                            to: active.id,
                          })
                        }
                      />
                      {node.label}
                    </label>
                  ))}
              </fieldset>
              <button
                type="button"
                data-action="remove-node"
                onClick={() => dispatch({ type: "remove-node", id: active.id })}
              >
                Remove node
              </button>
            </div>
          )}
          <div className="pa__actions">
            <button
              type="button"
              data-action="dry-run"
              disabled={!canDryRun(state)}
              onClick={onDryRun}
            >
              Dry run
            </button>
            <button type="button" data-action="refresh" onClick={onRefresh}>
              Refresh runs
            </button>
          </div>
        </div>

        <div className="pa__panel pa__panel--trace">
          <div className="pa__panel-head">
            <h2>Dry-run trace</h2>
            <span className="pa__digest" data-automation="trace-digest">
              {state.trace.length
                ? `${summary.succeeded}/${summary.total} ok`
                : "not run"}
            </span>
          </div>
          <ol className="pa__trace" data-automation="trace-viewer">
            {rows.map((row, index) => (
              <li
                key={`${row.id}-${index}`}
                className={`pa__trace-row pa__trace-row--${row.tone}`}
              >
                <span className="pa__trace-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="pa__trace-node">{row.label}</span>
                <span className="pa__trace-bar">
                  <span style={{ width: `${row.percent}%` }} />
                </span>
                <span className="pa__trace-duration">{row.durationMs}ms</span>
                <span className="pa__trace-detail">{row.detail}</span>
              </li>
            ))}
            {rows.length === 0 && (
              <li className="pa__empty">Run a dry run to inspect the plan.</li>
            )}
          </ol>
        </div>

        <div className="pa__panel pa__panel--schedule">
          <div className="pa__panel-head">
            <h2>Schedule editor</h2>
            <span className="pa__schedule-label">
              {scheduleLabel(scheduleDraft)}
            </span>
          </div>
          <div className="pa__form-grid">
            <label htmlFor="pa-frequency">Frequency</label>
            <select
              id="pa-frequency"
              value={scheduleDraft.frequency}
              onChange={(event) =>
                updateDraft({
                  frequency: event.target.value as ScheduleV4["frequency"],
                })
              }
            >
              <option value="interval">Interval</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
            <label htmlFor="pa-interval">Interval (minutes)</label>
            <input
              id="pa-interval"
              type="number"
              min={1}
              value={scheduleDraft.interval_minutes}
              onChange={(event) =>
                updateDraft({ interval_minutes: Number(event.target.value) })
              }
            />
            <label htmlFor="pa-hour">Hour (UTC)</label>
            <input
              id="pa-hour"
              type="number"
              min={0}
              max={23}
              value={scheduleDraft.hour}
              onChange={(event) =>
                updateDraft({ hour: Number(event.target.value) })
              }
            />
            <label htmlFor="pa-minute">Minute</label>
            <input
              id="pa-minute"
              type="number"
              min={0}
              max={59}
              value={scheduleDraft.minute}
              onChange={(event) =>
                updateDraft({ minute: Number(event.target.value) })
              }
            />
            <label htmlFor="pa-month-day">Month day</label>
            <input
              id="pa-month-day"
              type="number"
              min={1}
              max={31}
              value={scheduleDraft.day_of_month}
              onChange={(event) =>
                updateDraft({ day_of_month: Number(event.target.value) })
              }
            />
          </div>
          <div className="pa__actions">
            <button
              type="button"
              data-action="save-schedule"
              onClick={commitSchedule}
            >
              Save schedule
            </button>
          </div>
          <ul className="pa__schedule-list" data-automation="schedule-list">
            {state.schedules.map((schedule) => (
              <li key={schedule.id} data-schedule={schedule.id}>
                <strong>{scheduleLabel(schedule)}</strong>
                <span>{schedule.next_run || "no next run"}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="pa__panel pa__panel--runs">
          <div className="pa__panel-head">
            <h2>Run history</h2>
            <label htmlFor="pa-status-filter">
              <span className="pa__visually-hidden">Status filter</span>
              <select
                id="pa-status-filter"
                value={state.statusFilter}
                onChange={(event) =>
                  dispatch({ type: "set-filter", status: event.target.value })
                }
              >
                <option value="">All statuses</option>
                <option value="running">Running</option>
                <option value="succeeded">Succeeded</option>
                <option value="failed">Failed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </label>
          </div>
          <ul className="pa__runs" data-automation="run-history">
            {runs.map((run: RunRecordV4) => (
              <li
                key={run.id}
                className={`pa__run pa__run--${statusTone(run.status)}`}
              >
                <span className="pa__run-status">{run.status}</span>
                <span className="pa__run-id">{run.id}</span>
                <span className="pa__run-time">{run.started_at}</span>
              </li>
            ))}
            {runs.length === 0 && (
              <li className="pa__empty">No runs recorded yet.</li>
            )}
          </ul>
        </div>
      </div>
    </section>
  );
}

export default DagCanvas;
