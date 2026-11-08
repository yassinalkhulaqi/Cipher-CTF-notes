import { useEffect, useMemo, useState } from "react";
import { CalendarClock, Flag, Folder, Search, StickyNote } from "lucide-react";
import { api } from "../../lib/api";
import type { TimelineEvent } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

function formatWhen(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function TimelineModal() {
  const closeModal = useUiStore((state) => state.closeModal);
  const openNote = useAppStore((state) => state.openNote);
  const toast = useUiStore((state) => state.toast);

  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .timeline(null, 100)
      .then((data) => {
        if (!cancelled) setEvents(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load the timeline",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return events;
    return events.filter(
      (event) =>
        event.title.toLowerCase().includes(needle) ||
        event.path.toLowerCase().includes(needle) ||
        event.target.toLowerCase().includes(needle),
    );
  }, [events, query]);

  const open = (event: TimelineEvent) => {
    if (event.kind !== "note") return;
    closeModal();
    void openNote(event.node_id).catch((err: unknown) =>
      toast(
        err instanceof Error ? err.message : "Could not open note",
        "error",
      ),
    );
  };

  return (
    <Modal
      title="Timeline"
      subtitle="Recent vault activity"
      icon={<CalendarClock />}
      className="timeline-modal"
      bodyClassName="timeline-body"
      label="Vault timeline"
    >
      {error ? (
        <div className="graph-empty timeline-empty">
          <p>{error}</p>
          <button type="button" className="btn" onClick={closeModal}>
            Close
          </button>
        </div>
      ) : (
        <>
          <div className="timeline-toolbar">
            <div className="sidebar-search timeline-search">
              <Search />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Filter activity…"
                spellCheck={false}
                autoComplete="off"
                aria-label="Filter the timeline"
              />
            </div>
            <span className="graph-meta">
              {visible.length} {visible.length === 1 ? "event" : "events"}
            </span>
          </div>
          <div className="timeline-list">
            {visible.length === 0 ? (
              <div className="timeline-empty graph-empty">
                <CalendarClock />
                <p>
                  {events.length === 0
                    ? "No activity yet. Create a note to start the timeline."
                    : "No activity matches the current filter."}
                </p>
              </div>
            ) : (
              visible.map((event) => (
                <button
                  key={`${event.node_id}-${event.at}`}
                  type="button"
                  className="timeline-row"
                  onClick={() => open(event)}
                  disabled={event.kind !== "note"}
                >
                  <span className="timeline-icon">
                    {event.kind === "folder" ? <Folder /> : <StickyNote />}
                  </span>
                  <span className="timeline-copy">
                    <span className="timeline-title">{event.title}</span>
                    <span className="timeline-meta">
                      {event.activity === "created" ? "Created" : "Edited"}
                      {event.path ? ` · ${event.path}` : ""}
                      {event.target ? ` · ${event.target}` : ""}
                    </span>
                  </span>
                  {event.flag ? (
                    <span className="timeline-flag" title={event.flag}>
                      <Flag />
                    </span>
                  ) : null}
                  <time className="timeline-when">{formatWhen(event.at)}</time>
                </button>
              ))
            )}
          </div>
        </>
      )}
    </Modal>
  );
}
