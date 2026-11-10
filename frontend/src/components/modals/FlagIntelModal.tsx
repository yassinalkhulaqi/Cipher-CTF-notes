import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  Copy,
  Flag,
  Search,
  ShieldCheck,
} from "lucide-react";
import { api } from "../../lib/api";
import { flagFormat, type FlagFormat } from "../../lib/flags";
import type {
  FlagHit,
  FlagInsights,
  FlagPattern,
  NodeSummary,
} from "../../lib/types";
import { copyText, plural, relativeTime } from "../../lib/utils";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { EmptyState } from "../EmptyState";
import { Skeleton } from "../../motion/Skeleton";
import { Modal } from "./Modal";

type FlagFilter = "all" | "known" | "custom" | "duplicates" | "review";

const FILTERS: Array<{ id: FlagFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "known", label: "Known" },
  { id: "custom", label: "Custom" },
  { id: "duplicates", label: "Duplicates" },
  { id: "review", label: "Review" },
];

interface FlagRecord extends FlagHit {
  prefix: string;
  format: FlagFormat;
  duplicateCount: number;
}

function prefixOf(flag: string): string {
  const match = /^([A-Za-z][A-Za-z0-9_-]{0,31})\{/.exec(flag.trim());
  return match?.[1] ?? "unrecognized";
}

export function FlagIntelModal() {
  const closeModal = useUiStore((state) => state.closeModal);
  const openModal = useUiStore((state) => state.openModal);
  const toast = useUiStore((state) => state.toast);
  const openNewNote = useUiStore((state) => state.openNewNote);
  const openNote = useAppStore((state) => state.openNote);
  const note = useAppStore((state) => state.note);
  const nodes = useAppStore((state) => state.nodes);

  const [flags, setFlags] = useState<FlagHit[]>([]);
  const [insights, setInsights] = useState<FlagInsights | null>(null);
  const [patterns, setPatterns] = useState<FlagPattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FlagFilter>("all");
  const [copied, setCopied] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([api.collectedFlags(), api.flagInsights(), api.flagPatterns()])
      .then(([flagItems, insightData, patternItems]) => {
        if (cancelled) return;
        setFlags(flagItems);
        setInsights(insightData);
        setPatterns(patternItems);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "Could not load flag intelligence",
        );
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  useEffect(() => {
    if (copied === null) return;
    const timer = window.setTimeout(() => setCopied(null), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const records = useMemo<FlagRecord[]>(() => {
    const duplicates = new Map(
      (insights?.duplicates ?? []).map((item) => [item.flag, item.note_count]),
    );
    return flags
      .map((hit) => ({
        ...hit,
        prefix: prefixOf(hit.flag),
        format: flagFormat(hit.flag, patterns),
        duplicateCount: duplicates.get(hit.flag) ?? 1,
      }))
      .sort((a, b) => a.flag.localeCompare(b.flag));
  }, [flags, insights, patterns]);

  const counts = useMemo(
    () => ({
      all: records.length,
      known: records.filter((item) => item.format.tone === "known").length,
      custom: records.filter((item) => item.format.tone === "custom").length,
      duplicates: records.filter((item) => item.duplicateCount > 1).length,
      review: records.filter((item) => item.format.tone === "invalid").length,
    }),
    [records],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return records.filter((item) => {
      if (filter === "known" && item.format.tone !== "known") return false;
      if (filter === "custom" && item.format.tone !== "custom") return false;
      if (filter === "duplicates" && item.duplicateCount < 2) return false;
      if (filter === "review" && item.format.tone !== "invalid") return false;
      if (!needle) return true;
      return `${item.flag} ${item.title} ${item.path} ${item.format.platform ?? ""}`
        .toLowerCase()
        .includes(needle);
    });
  }, [records, filter, query]);

  const doneWithoutFlag = useMemo(
    () =>
      Array.from(nodes.values())
        .filter(
          (node) =>
            node.kind === "note" &&
            !node.trashed &&
            node.status === "done" &&
            !node.flag,
        )
        .sort(
          (a, b) =>
            new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
        ),
    [nodes],
  );

  const copyFlag = (value: string) => {
    void copyText(value).then(
      () => {
        setCopied(value);
        toast("Flag copied", "success");
      },
      () => toast("Could not copy the flag", "error"),
    );
  };

  const openNode = (nodeId: number) => {
    closeModal();
    void openNote(nodeId).catch((err: unknown) =>
      toast(
        err instanceof Error ? err.message : "Could not open note",
        "error",
      ),
    );
  };

  const openMissing = (node: NodeSummary) => {
    openNode(node.id);
  };

  return (
    <Modal
      title="Flag intelligence"
      subtitle="Captured values, formats, and gaps"
      icon={<Flag />}
      className="flag-intel-modal"
      bodyClassName="flag-intel-body"
      label="Flag intelligence"
      size="wide"
      footer={
        <>
          <span className="modal-hint">
            Format labels describe shape, not validation.
          </span>
          <span className="grow" />
          <button type="button" className="btn primary" onClick={closeModal}>
            Done
          </button>
        </>
      }
    >
      {error ? (
        <div className="flag-intel-error" role="alert">
          <AlertTriangle />
          <div>
            <strong>Flag intelligence is unavailable</strong>
            <p>{error}</p>
          </div>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => setReloadKey((value) => value + 1)}
          >
            Retry
          </button>
        </div>
      ) : (
        <>
          <div className="flag-intel-stats">
            <div className="flag-intel-stat">
              <span>Unique flags</span>
              <strong>{loading ? "—" : insights?.unique_flags ?? records.length}</strong>
            </div>
            <div className="flag-intel-stat">
              <span>Known formats</span>
              <strong className="green">{loading ? "—" : counts.known}</strong>
            </div>
            <div className="flag-intel-stat">
              <span>Duplicates</span>
              <strong className={counts.duplicates > 0 ? "yellow" : ""}>
                {loading ? "—" : counts.duplicates}
              </strong>
            </div>
            <div className="flag-intel-stat">
              <span>Without a detected flag</span>
              <strong className={insights?.missing_flag_notes ? "red" : ""}>
                {loading ? "—" : insights?.missing_flag_notes ?? 0}
              </strong>
            </div>
          </div>

          <div className="flag-intel-layout">
            <div className="flag-intel-main">
              <div className="flag-intel-toolbar">
                <div className="sidebar-search flag-intel-search">
                  <Search />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search flags, notes, or platforms…"
                    spellCheck={false}
                    autoComplete="off"
                    aria-label="Search captured flags"
                  />
                </div>
                <div
                  className="flag-intel-filters"
                  role="group"
                  aria-label="Filter captured flags"
                >
                  {FILTERS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={filter === item.id ? "active" : ""}
                      aria-pressed={filter === item.id}
                      onClick={() => setFilter(item.id)}
                    >
                      {item.label}
                      <span>{counts[item.id]}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="flag-intel-list">
                {loading ? (
                  <Skeleton lines={7} />
                ) : filtered.length ? (
                  filtered.map((item) => (
                    <div
                      className="flag-intel-row"
                      key={`${item.node_id}-${item.flag}`}
                    >
                      <span
                        className={`flag-format-dot ${item.format.tone}`}
                        aria-hidden="true"
                      />
                      <div className="flag-intel-copy">
                        <code>{item.flag}</code>
                        <button
                          type="button"
                          className="flag-intel-note"
                          onClick={() => openNode(item.node_id)}
                          title={item.path || item.title}
                        >
                          {item.title}
                          <span>{item.path || "Vault root"}</span>
                        </button>
                      </div>
                      <div className="flag-intel-meta">
                        <span className={`flag-badge ${item.format.tone}`}>
                          {item.format.label}
                        </span>
                        {item.duplicateCount > 1 ? (
                          <span className="flag-badge duplicate">
                            <Copy /> ×{item.duplicateCount}
                          </span>
                        ) : null}
                        <span className="flag-intel-origin">
                          {item.manual ? "Manual" : "Detected"}
                        </span>
                      </div>
                      <div className="flag-intel-actions">
                        <button
                          type="button"
                          className="icon-btn sm"
                          onClick={() => copyFlag(item.flag)}
                          title="Copy flag"
                          aria-label={`Copy ${item.flag}`}
                        >
                          {copied === item.flag ? <Check /> : <Copy />}
                        </button>
                        <button
                          type="button"
                          className="icon-btn sm"
                          onClick={() => openNode(item.node_id)}
                          title="Open note"
                          aria-label={`Open ${item.title}`}
                        >
                          <ArrowUpRight />
                        </button>
                      </div>
                    </div>
                  ))
                ) : (
                  <EmptyState
                    icon={Flag}
                    title={
                      records.length
                        ? "No flags match this view"
                        : "No flags captured yet"
                    }
                    description={
                      records.length
                        ? "Try a different search or filter."
                        : "Set a flag in note properties or capture one in the note body."
                    }
                    compact
                    actions={
                      records.length
                        ? [
                            {
                              label: "Clear filters",
                              onClick: () => {
                                setQuery("");
                                setFilter("all");
                              },
                            },
                          ]
                        : note
                          ? [
                              {
                                label: "Open properties",
                                onClick: () => {
                                  closeModal();
                                  openModal("properties");
                                },
                                variant: "primary",
                              },
                            ]
                          : [
                              {
                                label: "New note",
                                onClick: () => {
                                  closeModal();
                                  openNewNote();
                                },
                                variant: "primary",
                              },
                            ]
                    }
                  />
                )}
              </div>
            </div>

            <aside className="flag-intel-side">
              <section className="flag-intel-side-panel">
                <div className="flag-intel-side-head">
                  <span>
                    <ShieldCheck /> Needs attention
                  </span>
                </div>
                {loading ? (
                  <Skeleton lines={4} compact />
                ) : (
                  <>
                    <div className="flag-intel-callout">
                      <span>
                        {plural(insights?.missing_flag_notes ?? 0, "done note")}{" "}
                        without any detected flag.
                      </span>
                      <span>
                        {plural(insights?.duplicates.length ?? 0, "duplicate")} on
                        record.
                      </span>
                    </div>
                    {doneWithoutFlag.length ? (
                      <div className="flag-intel-missing">
                        <span className="flag-intel-side-label">
                          Done notes with no flag field
                        </span>
                        {doneWithoutFlag.slice(0, 6).map((node) => (
                          <button
                            key={node.id}
                            type="button"
                            className="flag-intel-missing-row"
                            onClick={() => openMissing(node)}
                            title={node.path || node.title}
                          >
                            <Flag />
                            <span>{node.title}</span>
                            <span className="flag-intel-missing-time">
                              {relativeTime(node.updated_at)}
                            </span>
                          </button>
                        ))}
                        <p className="flag-intel-caveat">
                          Flags found only in note content still count toward the
                          total above.
                        </p>
                      </div>
                    ) : (
                      <p className="flag-intel-caveat">
                        No done notes are missing a flag field.
                      </p>
                    )}
                  </>
                )}
              </section>

              <section className="flag-intel-side-panel">
                <div className="flag-intel-side-head">
                  <span>
                    <Flag /> Source mix
                  </span>
                </div>
                {loading ? (
                  <Skeleton lines={4} compact />
                ) : insights && insights.by_source.length ? (
                  <div className="flag-source-list">
                    {insights.by_source.slice(0, 8).map((source) => {
                      const max = Math.max(
                        ...insights.by_source.map((item) => item.count),
                        1,
                      );
                      return (
                        <div className="flag-source-row" key={source.prefix}>
                          <span className="flag-source-name">
                            {source.platform}
                          </span>
                          <span className="flag-source-bar" aria-hidden="true">
                            <span
                              style={{
                                width: `${Math.max(
                                  Math.round((source.count / max) * 100),
                                  8,
                                )}%`,
                              }}
                            />
                          </span>
                          <span className="flag-source-count">
                            {source.count}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="flag-intel-caveat">
                    Flag sources appear after flags are captured.
                  </p>
                )}
              </section>
            </aside>
          </div>
        </>
      )}
    </Modal>
  );
}
