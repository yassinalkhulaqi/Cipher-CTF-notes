import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import type { FormEvent, KeyboardEvent as ReactKeyboardEvent } from "react";

import {
  CAPTURE_SOURCES,
  InboxClient,
  QUICK_TAGS,
  TRIAGE_STATES,
  inboxClient,
} from "./client";
import type { CaptureItemV4, CaptureSourceV4, TriageStateV4 } from "./client";
import {
  capturePreview,
  initialInboxState,
  isLegalTransition,
  legalTargets,
  reduceInbox,
  selectedItem,
  sourceCounts,
  stateCounts,
  visibleItems,
} from "./state";
import type { SourceFilter, StateFilter } from "./state";
import "./capture-inbox.css";

export interface InboxPanelProps {
  api?: InboxClient;
  className?: string;
  onCapture?: (item: CaptureItemV4) => void;
  onTriage?: (item: CaptureItemV4) => void;
}

const SOURCE_LABELS: Record<CaptureSourceV4, string> = {
  manual: "Manual",
  link: "Link",
  snippet: "Snippet",
  flag: "Flag",
  clipboard: "Clipboard",
};

const STATE_LABELS: Record<TriageStateV4, string> = {
  untriaged: "Untriaged",
  accepted: "Accepted",
  rejected: "Rejected",
  archived: "Archived",
};

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Inbox request failed";
}

export function InboxPanel({
  api: suppliedApi,
  className = "",
  onCapture,
  onTriage,
}: InboxPanelProps) {
  const [state, dispatch] = useReducer(reduceInbox, undefined, () =>
    initialInboxState(),
  );
  const api = useMemo(() => suppliedApi ?? inboxClient, [suppliedApi]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const items = useMemo(() => visibleItems(state), [state]);
  const counts = useMemo(() => stateCounts(state), [state]);
  const sources = useMemo(() => sourceCounts(state), [state]);
  const active = selectedItem(state);

  const refresh = useCallback(async () => {
    dispatch({ type: "loading" });
    try {
      const page = await api.list({
        state: state.filter === "all" ? undefined : state.filter,
        source: state.sourceFilter === "all" ? undefined : state.sourceFilter,
        query: state.query || undefined,
        pageSize: 50,
      });
      dispatch({
        type: "loaded",
        items: page.data.items,
        total: page.data.total,
        page: page.meta.page,
        nextCursor: page.data.next_cursor,
        requestId: page.meta.request_id,
      });
    } catch (error: unknown) {
      dispatch({ type: "failed", message: errorText(error) });
    }
  }, [api, state.filter, state.sourceFilter, state.query]);

  useEffect(() => {
    let activeRequest = true;
    dispatch({ type: "loading" });
    api
      .list({ pageSize: 50 })
      .then((page) => {
        if (!activeRequest) return;
        dispatch({
          type: "loaded",
          items: page.data.items,
          total: page.data.total,
          page: page.meta.page,
          nextCursor: page.data.next_cursor,
          requestId: page.meta.request_id,
        });
      })
      .catch((error: unknown) => {
        if (activeRequest)
          dispatch({ type: "failed", message: errorText(error) });
      });
    return () => {
      activeRequest = false;
    };
  }, [api]);

  const submitCapture = useCallback(
    async (event?: FormEvent<HTMLFormElement>) => {
      event?.preventDefault();
      const raw = state.draft.trim();
      if (!raw || state.submitting) return;
      dispatch({ type: "submitting" });
      try {
        const result = await api.capture(raw, state.source, state.tags);
        dispatch({
          type: "captured",
          item: result.capture,
          created: result.created ?? true,
          duplicate: result.duplicate ?? false,
        });
        onCapture?.(result.capture);
      } catch (error: unknown) {
        dispatch({ type: "failed", message: errorText(error) });
      }
    },
    [api, onCapture, state.draft, state.source, state.submitting, state.tags],
  );

  const triage = useCallback(
    async (item: CaptureItemV4, target: TriageStateV4) => {
      if (!isLegalTransition(item.state, target)) {
        dispatch({
          type: "notice",
          message: `Cannot move ${STATE_LABELS[item.state]} to ${STATE_LABELS[target]}`,
        });
        return;
      }
      dispatch({ type: "submitting" });
      try {
        const result = await api.triage(item.id, target);
        dispatch({ type: "triaged", item: result.capture });
        onTriage?.(result.capture);
      } catch (error: unknown) {
        dispatch({ type: "failed", message: errorText(error) });
      }
    },
    [api, onTriage],
  );

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target?.tagName === "TEXTAREA" ||
        target?.tagName === "INPUT" ||
        target?.isContentEditable;
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        void submitCapture();
        return;
      }
      if (typing || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        dispatch({ type: "move", delta: 1 });
      } else if (event.key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        dispatch({ type: "move", delta: -1 });
      } else if (event.key === "a" && active) {
        void triage(active, "accepted");
      } else if (event.key === "r" && active) {
        void triage(active, "rejected");
      } else if (event.key === "/") {
        event.preventDefault();
        textareaRef.current?.focus();
      }
    },
    [active, submitCapture, triage],
  );

  return (
    <div
      className={`capture-inbox ${className}`.trim()}
      data-state={state.filter}
      onKeyDown={onKeyDown}
    >
      <header className="capture-inbox__header">
        <div>
          <p className="capture-inbox__eyebrow">V4 / Universal capture</p>
          <h2 className="capture-inbox__title">Capture inbox</h2>
          <p className="capture-inbox__subtitle">
            {state.total} captured · {counts.untriaged} awaiting triage
          </p>
        </div>
        <button
          type="button"
          className="capture-inbox__refresh"
          onClick={() => void refresh()}
          disabled={state.loading}
        >
          {state.loading ? "Loading…" : "Refresh"}
        </button>
      </header>

      <div className="capture-inbox__shortcuts" aria-label="Keyboard hints">
        <span>
          <kbd>Ctrl</kbd>+<kbd>Enter</kbd> capture
        </span>
        <span>
          <kbd>J</kbd>/<kbd>K</kbd> move
        </span>
        <span>
          <kbd>A</kbd> accept
        </span>
        <span>
          <kbd>R</kbd> reject
        </span>
        <span>
          <kbd>/</kbd> focus composer
        </span>
      </div>

      <form
        className="capture-inbox__composer"
        onSubmit={(event) => void submitCapture(event)}
      >
        <label className="capture-inbox__label" htmlFor="capture-inbox-draft">
          Quick capture
        </label>
        <textarea
          id="capture-inbox-draft"
          ref={textareaRef}
          className="capture-inbox__textarea"
          value={state.draft}
          onChange={(event) =>
            dispatch({ type: "draft", value: event.target.value })
          }
          placeholder="Paste a link, code snippet, or flag…"
          rows={4}
        />
        <div
          className="capture-inbox__chips"
          role="group"
          aria-label="Capture source"
        >
          {CAPTURE_SOURCES.map((source) => (
            <button
              type="button"
              key={source}
              className={`capture-inbox__chip${state.source === source ? " is-active" : ""}`}
              aria-pressed={state.source === source}
              onClick={() => dispatch({ type: "source", value: source })}
            >
              {SOURCE_LABELS[source]}
            </button>
          ))}
        </div>
        <div
          className="capture-inbox__chips"
          role="group"
          aria-label="Capture tags"
        >
          {QUICK_TAGS.map((tag) => (
            <button
              type="button"
              key={tag}
              className={`capture-inbox__chip capture-inbox__chip--tag${
                state.tags.includes(tag) ? " is-active" : ""
              }`}
              aria-pressed={state.tags.includes(tag)}
              onClick={() => dispatch({ type: "toggle-tag", value: tag })}
            >
              #{tag}
            </button>
          ))}
        </div>
        <div className="capture-inbox__composer-actions">
          <span className="capture-inbox__hint">
            {state.tags.length} tag(s) · {SOURCE_LABELS[state.source]}
          </span>
          <button
            type="submit"
            className="capture-inbox__primary"
            disabled={!state.draft.trim() || state.submitting}
          >
            {state.submitting ? "Saving…" : "Capture"}
          </button>
        </div>
      </form>

      <div className="capture-inbox__toolbar">
        <div
          className="capture-inbox__filters"
          role="group"
          aria-label="Filter by state"
        >
          {(["all", ...TRIAGE_STATES] as StateFilter[]).map((filter) => (
            <button
              type="button"
              key={filter}
              className={`capture-inbox__filter${
                state.filter === filter ? " is-active" : ""
              }`}
              aria-pressed={state.filter === filter}
              onClick={() => dispatch({ type: "filter", value: filter })}
            >
              {filter === "all" ? "All" : STATE_LABELS[filter]}
              <span className="capture-inbox__count">{counts[filter]}</span>
            </button>
          ))}
        </div>
        <label className="capture-inbox__source-filter">
          <span>Source</span>
          <select
            value={state.sourceFilter}
            onChange={(event) =>
              dispatch({
                type: "source-filter",
                value: event.target.value as SourceFilter,
              })
            }
          >
            <option value="all">All ({sources.all})</option>
            {CAPTURE_SOURCES.map((source) => (
              <option key={source} value={source}>
                {SOURCE_LABELS[source]} ({sources[source]})
              </option>
            ))}
          </select>
        </label>
        <input
          className="capture-inbox__search"
          type="search"
          value={state.query}
          onChange={(event) =>
            dispatch({ type: "query", value: event.target.value })
          }
          placeholder="Filter text or tags"
          aria-label="Filter captures"
        />
      </div>

      <div className="capture-inbox__status" role="status" aria-live="polite">
        {state.error ? (
          <span className="capture-inbox__error" role="alert">
            {state.error}
          </span>
        ) : (
          <span>{state.notice}</span>
        )}
      </div>

      <ul className="capture-inbox__list" aria-label="Captured items">
        {items.map((item) => {
          const targets = legalTargets(item.state);
          const isSelected = item.id === state.selectedId;
          return (
            <li
              key={item.id}
              className={`capture-inbox__item${isSelected ? " is-selected" : ""}`}
              onClick={() => dispatch({ type: "select", id: item.id })}
            >
              <div className="capture-inbox__item-top">
                <span
                  className={`capture-inbox__badge capture-inbox__badge--${item.source}`}
                >
                  {SOURCE_LABELS[item.source]}
                </span>
                <span
                  className={`capture-inbox__badge capture-inbox__badge--state-${item.state}`}
                >
                  {STATE_LABELS[item.state]}
                </span>
                <span className="capture-inbox__confidence">
                  {Math.round(item.confidence * 100)}%
                </span>
              </div>
              <p className="capture-inbox__raw">{capturePreview(item.raw)}</p>
              <div className="capture-inbox__item-bottom">
                <span className="capture-inbox__tags">
                  {item.tags.map((tag) => (
                    <span key={tag} className="capture-inbox__tag">
                      #{tag}
                    </span>
                  ))}
                </span>
                <span className="capture-inbox__actions">
                  <button
                    type="button"
                    disabled={!targets.includes("accepted")}
                    onClick={(event) => {
                      event.stopPropagation();
                      void triage(item, "accepted");
                    }}
                  >
                    Accept
                  </button>
                  <button
                    type="button"
                    disabled={!targets.includes("rejected")}
                    onClick={(event) => {
                      event.stopPropagation();
                      void triage(item, "rejected");
                    }}
                  >
                    Reject
                  </button>
                  <button
                    type="button"
                    disabled={!targets.includes("archived")}
                    onClick={(event) => {
                      event.stopPropagation();
                      void triage(item, "archived");
                    }}
                  >
                    Archive
                  </button>
                </span>
              </div>
            </li>
          );
        })}
        {items.length === 0 && (
          <li className="capture-inbox__empty">
            No captures match this view. Paste something above to get started.
          </li>
        )}
      </ul>
    </div>
  );
}

export default InboxPanel;
