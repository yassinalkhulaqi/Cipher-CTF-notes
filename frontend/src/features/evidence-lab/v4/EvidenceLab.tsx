/** v4 evidence inspection lab: list, hex grid, strings, hash badge, custody. */

import { useEffect, useMemo, useReducer } from "react";
import type { ReactElement, ReactNode } from "react";

import { EvidenceLabClientV4 } from "./client";
import {
  badgeLabel,
  canInspect,
  custodyTimeline,
  evidenceLabReducer,
  formatBytes,
  formatOffset,
  formatTimestamp,
  hashBadge,
  hexRows,
  initialEvidenceLabState,
  shortHash,
  statusText,
  visibleRecords,
  visibleStrings,
} from "./state";
import type { LabPanelV4 } from "./state";
import type { HexCellV4 } from "./types";

import "./evidence-lab.css";

export interface EvidenceLabPropsV4 {
  client?: EvidenceLabClientV4;
  title?: string;
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "Unable to load evidence";
}

function isPrintableHex(hex: string): boolean {
  const byte = Number.parseInt(hex, 16);
  return Number.isFinite(byte) && byte >= 32 && byte <= 126;
}

function Panel({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}): ReactElement {
  return (
    <section className="elfv4__panel">
      <h3 className="elfv4__panel-title">{title}</h3>
      {children}
    </section>
  );
}

function HexCellView({ cell }: { cell: HexCellV4 }): ReactElement {
  return (
    <span
      className={isPrintableHex(cell.hex) ? "elfv4__byte" : "elfv4__byte--raw"}
    >
      {cell.hex}
    </span>
  );
}

export function EvidenceLab({
  client,
  title = "Evidence Lab",
}: EvidenceLabPropsV4): ReactElement {
  const api = useMemo(() => client ?? new EvidenceLabClientV4(), [client]);
  const [state, dispatch] = useReducer(
    evidenceLabReducer,
    undefined,
    initialEvidenceLabState,
  );

  useEffect(() => {
    let active = true;
    dispatch({ type: "load-start" });
    api
      .list({ page: 1, pageSize: 50 })
      .then(({ data, meta }) => {
        if (!active) return;
        dispatch({
          type: "records-loaded",
          records: data.items,
          etag: data.etag || meta.etag || "",
          total: data.total,
        });
      })
      .catch((error: unknown) => {
        if (active) dispatch({ type: "error", message: describeError(error) });
      });
    return () => {
      active = false;
    };
  }, [api]);

  useEffect(() => {
    if (!state.selectedId) return;
    let active = true;
    dispatch({ type: "load-start" });
    Promise.all([api.inspect(state.selectedId), api.custody(state.selectedId)])
      .then(([result, chain]) => {
        if (!active) return;
        dispatch({ type: "inspection-loaded", result });
        dispatch({
          type: "custody-loaded",
          entries: chain.entries,
          valid: chain.verification.valid,
        });
      })
      .catch((error: unknown) => {
        if (active) dispatch({ type: "error", message: describeError(error) });
      });
    return () => {
      active = false;
    };
  }, [api, state.selectedId]);

  const records = useMemo(() => visibleRecords(state), [state]);
  const rows = useMemo(() => hexRows(state), [state]);
  const strings = useMemo(() => visibleStrings(state), [state]);
  const badge = useMemo(() => hashBadge(state), [state]);
  const timeline = useMemo(() => custodyTimeline(state), [state]);
  const ready = canInspect(state);

  const selectPanel = (value: LabPanelV4): void => {
    dispatch({ type: "panel", value });
  };

  return (
    <section className="elfv4" aria-label={title}>
      <header className="elfv4__header">
        <div className="elfv4__heading">
          <h2 className="elfv4__title">{title}</h2>
          <span className="elfv4__status">{statusText(state)}</span>
        </div>
        <div className="elfv4__controls">
          <label className="elfv4__search">
            <span className="v4-sr-only">Filter evidence</span>
            <input
              type="search"
              value={state.query}
              placeholder="Filter by name, hash, or tag"
              onChange={(event) =>
                dispatch({ type: "query", value: event.target.value })
              }
            />
          </label>
          <button
            type="button"
            className="v4-btn"
            aria-pressed={state.showAscii}
            onClick={() => dispatch({ type: "toggle-ascii" })}
          >
            ASCII
          </button>
        </div>
      </header>

      {state.error ? (
        <div className="elfv4__error" role="alert">
          {state.error}
          <button
            type="button"
            className="v4-btn"
            onClick={() => dispatch({ type: "clear-error" })}
          >
            Dismiss
          </button>
        </div>
      ) : null}

      <div className="elfv4__layout">
        <aside className="elfv4__sidebar" aria-label="Evidence list">
          {records.length === 0 ? (
            <div className="v4-empty">
              No evidence matches the current filter.
            </div>
          ) : (
            <ul className="elfv4__records">
              {records.map((record) => (
                <li key={record.id}>
                  <button
                    type="button"
                    className={
                      record.id === state.selectedId
                        ? "elfv4__record elfv4__record--active"
                        : "elfv4__record"
                    }
                    aria-current={
                      record.id === state.selectedId ? "true" : undefined
                    }
                    onClick={() => dispatch({ type: "select", id: record.id })}
                  >
                    <span className="elfv4__record-name">{record.name}</span>
                    <span className="elfv4__record-hash">
                      {shortHash(record.sha256)}
                    </span>
                    <span className="elfv4__record-size">
                      {formatBytes(record.size)}
                    </span>
                    <span className="elfv4__record-tags">
                      {record.tags.map((tag) => (
                        <span className="v4-chip" key={tag}>
                          {tag}
                        </span>
                      ))}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <main className="elfv4__detail">
          {!ready ? (
            <div className="v4-empty">
              Select an evidence item to inspect its contents.
            </div>
          ) : (
            <>
              <div className="elfv4__summary">
                <div
                  className={`elfv4__badge elfv4__badge--${badge}`}
                  data-status={badge}
                >
                  <span className="elfv4__badge-dot" aria-hidden="true" />
                  {badgeLabel(badge)}
                </div>
                <span className="v4-chip">
                  {state.inspection?.summary?.cells ?? 0} bytes mapped
                </span>
                <span className="v4-chip">
                  {state.inspection?.summary?.strings ?? strings.length} strings
                </span>
              </div>

              <nav className="elfv4__tabs" aria-label="Inspection panels">
                <button
                  type="button"
                  className={
                    state.panel === "hex" ? "elfv4__tab--active" : "elfv4__tab"
                  }
                  onClick={() => selectPanel("hex")}
                >
                  Hex viewer
                </button>
                <button
                  type="button"
                  className={
                    state.panel === "strings"
                      ? "elfv4__tab--active"
                      : "elfv4__tab"
                  }
                  onClick={() => selectPanel("strings")}
                >
                  Strings
                </button>
                <button
                  type="button"
                  className={
                    state.panel === "custody"
                      ? "elfv4__tab--active"
                      : "elfv4__tab"
                  }
                  onClick={() => selectPanel("custody")}
                >
                  Custody
                </button>
              </nav>

              {state.panel === "hex" ? (
                <Panel title="Hex viewer">
                  <div className="elfv4__hex-scroll v4-scroll">
                    <table className="elfv4__hex">
                      <thead>
                        <tr>
                          <th scope="col">Offset</th>
                          <th scope="col">Hex</th>
                          {state.showAscii ? <th scope="col">ASCII</th> : null}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => (
                          <tr key={row.offset}>
                            <th scope="row">{formatOffset(row.offset)}</th>
                            <td>
                              {row.cells.map((cell) => (
                                <HexCellView cell={cell} key={cell.offset} />
                              ))}
                            </td>
                            {state.showAscii ? (
                              <td className="elfv4__ascii">{row.ascii}</td>
                            ) : null}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {rows.length === 0 ? (
                      <div className="v4-empty">No bytes in this window.</div>
                    ) : null}
                  </div>
                </Panel>
              ) : null}

              {state.panel === "strings" ? (
                <Panel title="Strings">
                  <label className="elfv4__min-length">
                    Minimum length
                    <input
                      type="number"
                      min={1}
                      max={64}
                      value={state.minStringLength}
                      onChange={(event) =>
                        dispatch({
                          type: "min-length",
                          value: Number(event.target.value),
                        })
                      }
                    />
                  </label>
                  <ul className="elfv4__strings v4-scroll">
                    {strings.map((hit) => (
                      <li key={`${hit.offset}-${hit.value}`}>
                        <span className="elfv4__string-offset">
                          {formatOffset(hit.offset)}
                        </span>
                        <code className="elfv4__string-value">{hit.value}</code>
                        <span className="v4-chip">{hit.encoding}</span>
                      </li>
                    ))}
                  </ul>
                  {strings.length === 0 ? (
                    <div className="v4-empty">No printable runs found.</div>
                  ) : null}
                </Panel>
              ) : null}

              {state.panel === "custody" ? (
                <Panel title="Custody timeline">
                  <div
                    className={
                      state.chainValid
                        ? "elfv4__chain--ok"
                        : "elfv4__chain--bad"
                    }
                  >
                    {state.chainValid
                      ? "Chain intact"
                      : "Chain integrity check failed"}
                  </div>
                  <ol className="elfv4__timeline v4-scroll">
                    {timeline.map((entry) => (
                      <li key={`${entry.timestamp}-${entry.actor}`}>
                        <span className="elfv4__time">
                          {formatTimestamp(entry.timestamp)}
                        </span>
                        <strong className="elfv4__actor">{entry.actor}</strong>
                        <span className="v4-chip v4-chip--accent">
                          {entry.action}
                        </span>
                        <code className="elfv4__hash">
                          {shortHash(entry.to_hash)}
                        </code>
                      </li>
                    ))}
                  </ol>
                  {timeline.length === 0 ? (
                    <div className="v4-empty">No custody entries recorded.</div>
                  ) : null}
                </Panel>
              ) : null}

              {state.inspection?.notes.length ? (
                <ul className="elfv4__notes">
                  {state.inspection.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              ) : null}
            </>
          )}
        </main>
      </div>
    </section>
  );
}

export default EvidenceLab;
