import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  BookOpen,
  Briefcase,
  Bug,
  Check,
  ChevronRight,
  CircleDot,
  Code2,
  Copy,
  Crosshair,
  FileText,
  Flag,
  Globe,
  Keyboard,
  LayoutDashboard,
  Plus,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Tag,
  Target,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { api } from "../lib/api";
import { STATUS_LABEL } from "../lib/constants";
import type { FlagHit, NodeSummary, Template } from "../lib/types";
import { copyText, modLabel, plural, relativeTime } from "../lib/utils";
import { AnimatedNumber } from "../motion/AnimatedNumber";
import { Confetti } from "../motion/Confetti";
import { Skeleton } from "../motion/Skeleton";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";
import { StatusIcon } from "./StatusIcon";

const TEMPLATE_ICONS: Record<string, LucideIcon> = {
  blank: FileText,
  ctf: Crosshair,
  host: Server,
  web: Globe,
  finding: Bug,
  engagement: Briefcase,
  cheatsheet: BookOpen,
};

function byUpdated(a: NodeSummary, b: NodeSummary): number {
  return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
}

export function Dashboard() {
  const nodes = useAppStore((state) => state.nodes);
  const boot = useAppStore((state) => state.boot);
  const openNote = useAppStore((state) => state.openNote);
  const quickNote = useAppStore((state) => state.quickNote);
  const loadDemo = useAppStore((state) => state.loadDemo);
  const setFilter = useAppStore((state) => state.setFilter);

  const openModal = useUiStore((state) => state.openModal);
  const openNewNote = useUiStore((state) => state.openNewNote);
  const askConfirm = useUiStore((state) => state.askConfirm);
  const toast = useUiStore((state) => state.toast);

  const [flags, setFlags] = useState<FlagHit[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [copiedFlag, setCopiedFlag] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [burst, setBurst] = useState(0);
  const [flagsLoading, setFlagsLoading] = useState(true);

  const notes = useMemo(
    () =>
      Array.from(nodes.values())
        .filter((node) => node.kind === "note" && !node.trashed)
        .sort(byUpdated),
    [nodes],
  );

  const stats = useMemo(() => {
    const targets = new Map<string, number>();
    const tags = new Map<string, number>();
    const statuses = { todo: 0, active: 0, done: 0, blocked: 0 };
    let pinned = 0;
    let flagged = 0;
    for (const note of notes) {
      statuses[note.status] += 1;
      if (note.pinned) pinned += 1;
      if (note.flag) flagged += 1;
      if (note.target) {
        const key = note.target.toLowerCase();
        targets.set(key, (targets.get(key) ?? 0) + 1);
      }
      for (const tag of note.tag_list) {
        const key = tag.toLowerCase();
        tags.set(key, (tags.get(key) ?? 0) + 1);
      }
    }
    return {
      notes: notes.length,
      pinned,
      flagged,
      statuses,
      targets: Array.from(targets.entries()).sort((a, b) => b[1] - a[1]),
      tags: Array.from(tags.entries()).sort((a, b) => b[1] - a[1]),
    };
  }, [notes]);

  const recent = notes.slice(0, 6);
  const active = notes
    .filter((note) => note.status === "active" && !note.pinned)
    .slice(0, 4);
  const pinned = notes.filter((note) => note.pinned).slice(0, 4);

  useEffect(() => {
    let cancelled = false;
    api
      .templates()
      .then((items) => {
        if (!cancelled) setTemplates(items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (stats.notes === 0) {
      setFlags([]);
      setFlagsLoading(false);
      return;
    }
    let cancelled = false;
    setFlagsLoading(true);
    api
      .collectedFlags()
      .then((items) => {
        if (cancelled) return;
        setFlags(items);
        setFlagsLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setFlags([]);
        setFlagsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stats.notes, nodes]);

  useEffect(() => {
    if (copiedFlag === null) return;
    const timer = window.setTimeout(() => setCopiedFlag(null), 1600);
    return () => window.clearTimeout(timer);
  }, [copiedFlag]);

  const open = (id: number) => {
    void openNote(id).catch((error: unknown) =>
      toast(
        error instanceof Error ? error.message : "Could not open note",
        "error",
      ),
    );
  };

  const handleQuickNote = () => {
    setBusy(true);
    void quickNote()
      .then(
        (node) => toast(`Created “${node.title}”`, "success"),
        (error: unknown) =>
          toast(
            error instanceof Error ? error.message : "Could not create note",
            "error",
          ),
      )
      .finally(() => setBusy(false));
  };

  const handleDemo = () => {
    askConfirm({
      title: "Add the sample workspace",
      message:
        "Adds a small set of demonstration challenges, folders, and flags to this vault. Existing notes are left untouched.",
      confirmLabel: "Add samples",
      danger: false,
      action: async () => {
        try {
          await loadDemo();
          toast("Sample workspace added", "success");
        } catch (error) {
          toast(
            error instanceof Error ? error.message : "Could not load the demo",
            "error",
          );
        }
      },
    });
  };

  const copyFlag = (value: string) => {
    void copyText(value).then(
      () => {
        setCopiedFlag(value);
        setBurst((current) => current + 1);
      },
      () => toast("Could not copy the flag", "error"),
    );
  };

  const filterByTarget = (value: string) => {
    setFilter(value);
    window.dispatchEvent(new CustomEvent("redscribe:focus-filter"));
  };

  const lastTouched = recent[0] ? relativeTime(recent[0].updated_at) : null;
  const visibleFlags = flags.length
    ? flags.slice(0, 5)
    : notes
        .filter((note) => note.flag)
        .map((note) => ({
          flag: note.flag,
          node_id: note.id,
          title: note.title,
          path: note.path,
          manual: true,
        }))
        .slice(0, 5);

  if (stats.notes === 0) {
    return (
      <section className="dashboard dashboard-empty">
        <div className="dashboard-inner">
          <header className="dash-head">
            <div className="dash-title">
              <span className="eyebrow">
                <ShieldCheck /> Private workspace
              </span>
              <h1>Start the trail here.</h1>
              <p>
                A local notebook for CTF challenges, engagements, and the
                details that turn a hunch into a finding. Nothing leaves this
                machine.
              </p>
            </div>
            <div className="dash-actions">
              <button
                className="btn primary"
                type="button"
                onClick={() => openNewNote()}
              >
                <Plus /> New note
              </button>
              <button className="btn ghost" type="button" onClick={handleDemo}>
                <Sparkles /> Add samples
              </button>
            </div>
          </header>

          <div className="empty-start-grid">
            {(templates.length
              ? templates.slice(0, 3)
              : [
                  {
                    key: "blank",
                    name: "Blank note",
                    description: "A clean page for anything",
                  } as Template,
                  {
                    key: "ctf",
                    name: "CTF challenge",
                    description: "Recon, exploit, and flag sections",
                  } as Template,
                  {
                    key: "host",
                    name: "Host recon",
                    description: "Scan notes and service inventory",
                  } as Template,
                ]
            ).map((template) => {
              const Icon = TEMPLATE_ICONS[template.key] ?? FileText;
              return (
                <button
                  key={template.key}
                  type="button"
                  className="start-card"
                  onClick={() => openNewNote(null, template.key)}
                >
                  <span className="start-icon">
                    <Icon />
                  </span>
                  <span className="start-copy">
                    <strong>{template.name}</strong>
                    <span>{template.description}</span>
                  </span>
                  <ArrowUpRight />
                </button>
              );
            })}
          </div>

          <div className="empty-workspace">
            <div className="empty-signal">
              <span className="empty-signal-icon">
                <LayoutDashboard />
              </span>
              <div>
                <strong>Your dashboard fills itself</strong>
                <p>
                  Recent work, captured flags, targets, tags, and note status
                  appear here as soon as the first note exists.
                </p>
              </div>
            </div>
            <div className="empty-shortcuts">
              <span>
                <kbd>{modLabel()}</kbd>
                <kbd>N</kbd> quick note
              </span>
              <span>
                <kbd>{modLabel()}</kbd>
                <kbd>P</kbd> jump anywhere
              </span>
              <button
                type="button"
                className="link-btn"
                onClick={() => openModal("help")}
              >
                <Keyboard /> All shortcuts
              </button>
            </div>
          </div>

          <footer className="dash-foot">
            <ShieldCheck />
            SQLite vault · {boot?.vault_path ?? "local storage"} · no accounts,
            no telemetry
          </footer>
        </div>
      </section>
    );
  }

  return (
    <section className="dashboard">
      <div className="dashboard-inner">
        <header className="dash-head">
          <div className="dash-title">
            <span className="eyebrow">Workspace</span>
            <h1>Research desk</h1>
            <p>
              {plural(stats.notes, "note")} in the vault
              {lastTouched ? ` · last touched ${lastTouched}` : ""}
            </p>
          </div>
          <div className="dash-actions">
            <button
              className="btn subtle"
              type="button"
              onClick={handleQuickNote}
              disabled={busy}
              title={`${modLabel()}+N`}
            >
              <Zap /> Quick note
            </button>
            <button
              className="btn primary"
              type="button"
              onClick={() => openNewNote()}
            >
              <Plus /> New note
            </button>
          </div>
        </header>

        <div className="pulse-strip" aria-label="Vault statistics" data-reveal>
          <button
            type="button"
            className="pulse-cell"
            onClick={() => setFilter("")}
          >
            <span className="pulse-label">Notes</span>
            <strong>
              <AnimatedNumber value={stats.notes} />
            </strong>
            <span className="pulse-note">
              <CircleDot /> {stats.statuses.active} active
            </span>
          </button>
          <button
            type="button"
            className="pulse-cell"
            onClick={() => openModal("dashboard")}
          >
            <span className="pulse-label">Captured</span>
            <strong className="green">
              <AnimatedNumber value={flags.length} />
            </strong>
            <span className="pulse-note">
              <Flag /> {stats.statuses.done} completed
            </span>
          </button>
          <button
            type="button"
            className="pulse-cell"
            onClick={() => {
              const target = stats.targets[0]?.[0];
              if (target) filterByTarget(target);
            }}
          >
            <span className="pulse-label">Targets</span>
            <strong>
              <AnimatedNumber value={stats.targets.length} />
            </strong>
            <span className="pulse-note">
              <Target /> {stats.targets[0]?.[0] ?? "none yet"}
            </span>
          </button>
          <button
            type="button"
            className="pulse-cell"
            onClick={() => {
              const tag = stats.tags[0]?.[0];
              if (tag) filterByTarget(tag);
            }}
          >
            <span className="pulse-label">Tags</span>
            <strong>
              <AnimatedNumber value={stats.tags.length} />
            </strong>
            <span className="pulse-note">
              <Tag /> {stats.tags[0]?.[0] ?? "untagged"}
            </span>
          </button>
        </div>

        <div className="desk-grid">
          <div className="desk-main">
            <section className="dash-panel" data-tilt data-reveal>
              <div className="dash-panel-head">
                <div>
                  <h2>Continue working</h2>
                  <span>Recently updated notes</span>
                </div>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => openModal("palette")}
                >
                  Jump to <ArrowUpRight />
                </button>
              </div>
              <div className="work-list">
                {recent.map((note, index) => (
                  <button
                    key={note.id}
                    type="button"
                    className="work-row"
                    onClick={() => open(note.id)}
                  >
                    <span className="work-index">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="work-state">
                      <StatusIcon
                        status={note.status}
                        label={STATUS_LABEL[note.status]}
                      />
                    </span>
                    <span className="work-copy">
                      <span className="work-title">{note.title}</span>
                      <span className="work-meta">
                        {note.path || "Vault root"}
                        {note.target ? ` · ${note.target}` : ""}
                      </span>
                    </span>
                    {note.flag ? (
                      <span className="work-flag">
                        <Flag />
                      </span>
                    ) : null}
                    {note.pinned ? (
                      <span className="work-pin">Pinned</span>
                    ) : null}
                    <span className="work-time">
                      {relativeTime(note.updated_at)}
                    </span>
                    <ChevronRight className="work-arrow" />
                  </button>
                ))}
              </div>
            </section>

            <div className="dash-split">
              <section className="dash-panel compact" data-tilt data-reveal>
                <div className="dash-panel-head">
                  <div>
                    <h2>In progress</h2>
                    <span>{active.length || "No"} active notes</span>
                  </div>
                  <button
                    type="button"
                    className="icon-btn sm"
                    onClick={() => setFilter("")}
                    aria-label="View all notes"
                    title="View all notes"
                  >
                    <ArrowUpRight />
                  </button>
                </div>
                <div className="mini-list">
                  {active.length ? (
                    active.map((note) => (
                      <button
                        key={note.id}
                        type="button"
                        className="mini-row"
                        onClick={() => open(note.id)}
                      >
                        <StatusIcon status={note.status} />
                        <span>{note.title}</span>
                        <span className="mini-time">
                          {relativeTime(note.updated_at)}
                        </span>
                      </button>
                    ))
                  ) : (
                    <p className="mini-empty">
                      Nothing is marked active. Open a note and set its status
                      to start tracking it.
                    </p>
                  )}
                </div>
              </section>

              <section className="dash-panel compact" data-tilt data-reveal>
                <div className="dash-panel-head">
                  <div>
                    <h2>Pinned</h2>
                    <span>Always within reach</span>
                  </div>
                  <button
                    type="button"
                    className="icon-btn sm"
                    onClick={() => openModal("palette")}
                    aria-label="Open command palette"
                    title="Jump to a note"
                  >
                    <Search />
                  </button>
                </div>
                <div className="mini-list">
                  {pinned.length ? (
                    pinned.map((note) => (
                      <button
                        key={note.id}
                        type="button"
                        className="mini-row"
                        onClick={() => open(note.id)}
                      >
                        <FileText />
                        <span>{note.title}</span>
                        <span className="mini-time">
                          {relativeTime(note.updated_at)}
                        </span>
                      </button>
                    ))
                  ) : (
                    <p className="mini-empty">
                      Pin a note to keep it at the top of the sidebar and in
                      this list.
                    </p>
                  )}
                </div>
              </section>
            </div>
          </div>

          <aside className="desk-side">
            <section className="dash-panel flags-panel" data-tilt data-reveal>
              <div className="dash-panel-head">
                <div>
                  <h2>Captured flags</h2>
                  <span>{plural(flags.length, "flag")} on record</span>
                </div>
                <button
                  type="button"
                  className="icon-btn sm"
                  onClick={() => {
                    const first = visibleFlags[0];
                    if (first) copyFlag(first.flag);
                  }}
                  aria-label="Copy first flag"
                  title="Copy first flag"
                  disabled={!visibleFlags.length}
                >
                  <Copy />
                </button>
              </div>
              <div className="flag-list">
                {flagsLoading ? (
                  <Skeleton lines={4} compact />
                ) : visibleFlags.length ? (
                  visibleFlags.map((hit) => (
                    <button
                      key={`${hit.node_id}-${hit.flag}`}
                      type="button"
                      className="flag-row"
                      data-copied={copiedFlag === hit.flag ? "true" : "false"}
                      onClick={() => copyFlag(hit.flag)}
                      title={`Copy ${hit.flag}`}
                    >
                      <span className="flag-mark">
                        {copiedFlag === hit.flag ? <Check /> : <Flag />}
                      </span>
                      <span className="flag-copy">
                        <code>{hit.flag}</code>
                        <span>{hit.title}</span>
                      </span>
                    </button>
                  ))
                ) : (
                  <div className="flag-empty">
                    <Flag />
                    <span>
                      Flags detected in note content or set in properties will
                      collect here.
                    </span>
                  </div>
                )}
              </div>
            </section>

            <section className="dash-panel compact" data-tilt data-reveal>
              <div className="dash-panel-head">
                <div>
                  <h2>Targets</h2>
                  <span>Hosts and scopes</span>
                </div>
                <Target className="panel-glyph" />
              </div>
              <div className="target-cloud">
                {stats.targets.length ? (
                  stats.targets.slice(0, 6).map(([target, count]) => (
                    <button
                      key={target}
                      type="button"
                      className="target-pill"
                      onClick={() => filterByTarget(target)}
                      title={`Filter vault by ${target}`}
                    >
                      <span>{target}</span>
                      <span className="count">{count}</span>
                    </button>
                  ))
                ) : (
                  <p className="mini-empty">
                    Add a target in note properties to group related work.
                  </p>
                )}
              </div>
            </section>

            <section className="dash-panel compact" data-tilt data-reveal>
              <div className="dash-panel-head">
                <div>
                  <h2>Tags</h2>
                  <span>Working vocabulary</span>
                </div>
                <Tag className="panel-glyph" />
              </div>
              <div className="tag-cloud">
                {stats.tags.length ? (
                  stats.tags.slice(0, 10).map(([tag, count]) => (
                    <button
                      key={tag}
                      type="button"
                      className="tag-chip"
                      onClick={() => filterByTarget(tag)}
                      title={`Filter vault by #${tag}`}
                    >
                      #{tag}
                      <span>{count}</span>
                    </button>
                  ))
                ) : (
                  <p className="mini-empty">
                    Tags keep a growing vault navigable. Add them from note
                    properties.
                  </p>
                )}
              </div>
            </section>
          </aside>
        </div>

        <section className="dash-panel template-panel" data-tilt data-reveal>
          <div className="dash-panel-head">
            <div>
              <h2>Start from a template</h2>
              <span>Structured notes with starter commands</span>
            </div>
            <button
              type="button"
              className="link-btn"
              onClick={() => openNewNote()}
            >
              Browse all <ChevronRight />
            </button>
          </div>
          <div className="template-rail">
            {templates.slice(0, 6).map((template) => {
              const Icon = TEMPLATE_ICONS[template.key] ?? FileText;
              return (
                <button
                  key={template.key}
                  type="button"
                  className="template-tile"
                  onClick={() => openNewNote(null, template.key)}
                >
                  <span className="tile-icon">
                    <Icon />
                  </span>
                  <strong>{template.name}</strong>
                  <span>{template.description}</span>
                </button>
              );
            })}
          </div>
        </section>

        <footer className="dash-foot">
          <span>
            <ShieldCheck /> Local only
          </span>
          <span className="dash-foot-sep">·</span>
          <span className="dash-path" title={boot?.vault_path}>
            {boot?.vault_path}
          </span>
          <span className="grow" />
          <button
            type="button"
            className="link-btn"
            onClick={() => openModal("snippets")}
          >
            <Code2 /> Snippets
          </button>
          <button
            type="button"
            className="link-btn"
            onClick={() => openModal("dashboard")}
          >
            <LayoutDashboard /> Insights
          </button>
        </footer>
      </div>
      <Confetti fire={burst} />
    </section>
  );
}
