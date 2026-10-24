import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Code2,
  Crosshair,
  FilePlus2,
  FileText,
  Flag,
  FolderPlus,
  Keyboard,
  LayoutDashboard,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Tag,
} from "lucide-react";
import { api } from "../lib/api";
import type { NodeSummary } from "../lib/types";
import { modLabel, plural, relativeTime } from "../lib/utils";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";

export function Welcome() {
  const nodes = useAppStore((state) => state.nodes);
  const openNote = useAppStore((state) => state.openNote);
  const quickNote = useAppStore((state) => state.quickNote);
  const loadDemo = useAppStore((state) => state.loadDemo);

  const openModal = useUiStore((state) => state.openModal);
  const openNewNote = useUiStore((state) => state.openNewNote);
  const openNewFolder = useUiStore((state) => state.openNewFolder);
  const askConfirm = useUiStore((state) => state.askConfirm);
  const toast = useUiStore((state) => state.toast);

  const [recent, setRecent] = useState<NodeSummary[]>([]);
  const [recentLoading, setRecentLoading] = useState(true);

  const counts = useMemo(() => {
    let notes = 0;
    let flags = 0;
    const targets = new Set<string>();
    const tags = new Set<string>();
    for (const node of nodes.values()) {
      if (node.kind !== "note") continue;
      notes += 1;
      if (node.flag) flags += 1;
      if (node.target) targets.add(node.target.toLowerCase());
      for (const tag of node.tag_list) tags.add(tag.toLowerCase());
    }
    return { notes, flags, targets: targets.size, tags: tags.size };
  }, [nodes]);

  useEffect(() => {
    let cancelled = false;
    setRecentLoading(true);
    api
      .recentNotes(6)
      .then((items) => {
        if (!cancelled) setRecent(items);
      })
      .catch(() => {
        if (!cancelled) setRecent([]);
      })
      .finally(() => {
        if (!cancelled) setRecentLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [nodes]);

  const handleOpen = (id: number) => {
    void openNote(id).catch((error: unknown) =>
      toast(
        error instanceof Error ? error.message : "Could not open note",
        "error",
      ),
    );
  };

  const handleQuickNote = () => {
    void quickNote().then(
      (node) => toast(`Created “${node.title}”`, "success"),
      (error: unknown) =>
        toast(
          error instanceof Error ? error.message : "Could not create note",
          "error",
        ),
    );
  };

  const handleDemo = () => {
    askConfirm({
      title: "Load the demo vault",
      message:
        "This adds a small set of sample challenges, folders, and flags so you can explore RedScribe.",
      confirmLabel: "Load demo",
      danger: false,
      action: async () => {
        try {
          await loadDemo();
          toast("Demo vault loaded", "success");
        } catch (error) {
          toast(
            error instanceof Error ? error.message : "Could not load the demo",
            "error",
          );
        }
      },
    });
  };

  const quickActions = [
    {
      icon: FilePlus2,
      title: "Quick note",
      detail: "Start with your last template",
      key: `${modLabel()} N`,
      run: handleQuickNote,
    },
    {
      icon: Search,
      title: "Search every note",
      detail: "Full-text search across the vault",
      key: `${modLabel()} Shift F`,
      run: () => openModal("search"),
    },
    {
      icon: Code2,
      title: "Snippet library",
      detail: "Reusable commands with placeholders",
      key: `${modLabel()} Shift S`,
      run: () => openModal("snippets"),
    },
    {
      icon: LayoutDashboard,
      title: "Open dashboard",
      detail: "Flags, tags, and vault statistics",
      key: `${modLabel()} Shift D`,
      run: () => openModal("dashboard"),
    },
    {
      icon: Keyboard,
      title: "Keyboard shortcuts",
      detail: "Everything you can do without the mouse",
      key: "F1",
      run: () => openModal("help"),
    },
  ];

  return (
    <section className="welcome">
      <div className="welcome-inner">
        <div className="hero">
          <span className="hero-badge">
            <span className="dot" />
            Local-first security notebook
          </span>
          <h1>
            Write the trail.
            <br />
            <em>Keep the flag.</em>
          </h1>
          <p className="hero-lede">
            A private workspace for CTF challenges, pentest engagements, and the
            notes that turn scattered clues into a clean write-up. One SQLite
            vault. No accounts, no telemetry.
          </p>
          <div className="hero-actions">
            <button
              className="btn primary"
              type="button"
              onClick={() => openNewNote()}
            >
              <Plus />
              New note
            </button>
            <button
              className="btn ghost"
              type="button"
              onClick={() => openModal("palette")}
            >
              <Search />
              Jump to a note
            </button>
            {counts.notes === 0 ? (
              <button className="btn subtle" type="button" onClick={handleDemo}>
                <Sparkles />
                Explore the demo
              </button>
            ) : null}
            <span className="hero-hint">
              <kbd>{modLabel()}</kbd>
              <kbd>P</kbd>
              anywhere
            </span>
          </div>
        </div>

        <div className="stat-strip">
          <div className="stat-card accent">
            <span className="stat-icon">
              <FileText />
            </span>
            <strong>{counts.notes}</strong>
            <span>
              {counts.notes === 1 ? "Note in the vault" : "Notes in the vault"}
            </span>
          </div>
          <div className="stat-card green">
            <span className="stat-icon">
              <Flag />
            </span>
            <strong>{counts.flags}</strong>
            <span>Flags captured</span>
          </div>
          <div className="stat-card blue">
            <span className="stat-icon">
              <Crosshair />
            </span>
            <strong>{counts.targets}</strong>
            <span>Unique targets</span>
          </div>
          <div className="stat-card">
            <span className="stat-icon">
              <Tag />
            </span>
            <strong>{counts.tags}</strong>
            <span>Tags in use</span>
          </div>
        </div>

        <div className="welcome-grid">
          <div className="panel">
            <div className="panel-head">
              <h2>Pick up where you left off</h2>
              <span className="eyebrow">{plural(recent.length, "recent")}</span>
            </div>
            <div className="panel-body">
              {recentLoading ? (
                <div className="tree-skeleton">
                  <span style={{ width: "68%" }} />
                  <span style={{ width: "52%" }} />
                  <span style={{ width: "61%" }} />
                </div>
              ) : recent.length > 0 ? (
                <div className="recent-list">
                  {recent.map((node) => (
                    <button
                      key={node.id}
                      type="button"
                      className="recent-row"
                      onClick={() => handleOpen(node.id)}
                    >
                      <span className="recent-icon">
                        <FileText />
                      </span>
                      <span className="recent-copy">
                        <span className="recent-title">{node.title}</span>
                        <span className="recent-path">
                          {node.path || "Vault root"}
                        </span>
                      </span>
                      <span className="recent-time">
                        {relativeTime(node.updated_at)}
                      </span>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty">
                  <FileText />
                  <div>
                    <strong>No recent notes yet</strong>
                    <br />
                    Create a challenge note to get started.
                  </div>
                  <button
                    type="button"
                    className="btn ghost tiny"
                    onClick={() => openNewNote(null)}
                  >
                    <Plus /> New note
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h2>Quick actions</h2>
              <span className="eyebrow">Workflow</span>
            </div>
            <div className="panel-body">
              <div className="quick-actions">
                {quickActions.map((action) => {
                  const Icon = action.icon;
                  return (
                    <button
                      key={action.title}
                      type="button"
                      className="quick-action"
                      onClick={action.run}
                    >
                      <span className="qa-icon">
                        <Icon />
                      </span>
                      <span className="qa-copy">
                        <span className="qa-title">{action.title}</span>
                        <span className="qa-detail">{action.detail}</span>
                      </span>
                      <kbd className="qa-key">{action.key}</kbd>
                    </button>
                  );
                })}
              </div>
              <div className="quick-actions" style={{ marginTop: 4 }}>
                <button
                  type="button"
                  className="quick-action"
                  onClick={() => openNewFolder()}
                >
                  <span className="qa-icon">
                    <FolderPlus />
                  </span>
                  <span className="qa-copy">
                    <span className="qa-title">New folder</span>
                    <span className="qa-detail">
                      Organize notes by engagement or category
                    </span>
                  </span>
                  <kbd className="qa-key">{modLabel()} Shift N</kbd>
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="welcome-foot">
          <ShieldCheck />
          Everything stays on this machine · SQLite vault · Authorized testing
          only
          <ArrowRight />
        </div>
      </div>
    </section>
  );
}
