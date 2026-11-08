import { useEffect, useMemo, useState, type KeyboardEvent } from "react";
import {
  Activity,
  Code2,
  Command,
  Copy,
  FilePlus2,
  FileText,
  Flag,
  FolderPlus,
  Focus,
  Keyboard,
  LayoutDashboard,
  Moon,
  Network,
  Pin,
  Plus,
  Save,
  Search,
  Settings,
  SlidersHorizontal,
  Sun,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { api } from "../../lib/api";
import type { NodeSummary, Snippet } from "../../lib/types";
import { copyText, modLabel } from "../../lib/utils";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

interface PaletteCommand {
  label: string;
  detail: string;
  icon: LucideIcon;
  shortcut?: string;
  run: () => void;
}

type Entry =
  | { kind: "command"; command: PaletteCommand }
  | { kind: "note"; node: NodeSummary }
  | { kind: "snippet"; snippet: Snippet };

export function CommandPalette() {
  const theme = useAppStore((state) => state.theme);
  const setTheme = useAppStore((state) => state.setTheme);
  const toggleFocusMode = useAppStore((state) => state.toggleFocusMode);
  const openNote = useAppStore((state) => state.openNote);
  const note = useAppStore((state) => state.note);
  const saveNow = useAppStore((state) => state.saveNow);

  const openModal = useUiStore((state) => state.openModal);
  const openFind = useUiStore((state) => state.openFind);
  const openNewNote = useUiStore((state) => state.openNewNote);
  const openNewFolder = useUiStore((state) => state.openNewFolder);
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);

  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<NodeSummary[]>([]);
  const [jumps, setJumps] = useState<NodeSummary[]>([]);
  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(true);

  const commands = useMemo<PaletteCommand[]>(
    () => [
      {
        label: "New note",
        detail: "Open the template picker",
        icon: FilePlus2,
        shortcut: `${modLabel()} N`,
        run: () => openNewNote(),
      },
      {
        label: "Quick capture",
        detail: "Start a note from raw text",
        icon: Zap,
        shortcut: `${modLabel()} Shift Q`,
        run: () => openModal("quick-capture"),
      },
      {
        label: "New folder",
        detail: "Organize the vault",
        icon: FolderPlus,
        shortcut: `${modLabel()} Shift N`,
        run: () => openNewFolder(),
      },
      {
        label: "Full-text search",
        detail: "Search the body of every note",
        icon: Search,
        shortcut: `${modLabel()} Shift F`,
        run: () => openModal("search"),
      },
      {
        label: "Snippet library",
        detail: "Commands with target placeholders",
        icon: Code2,
        shortcut: `${modLabel()} Shift S`,
        run: () => openModal("snippets"),
      },
      {
        label: "Dashboard",
        detail: "Flags, tags, and vault statistics",
        icon: LayoutDashboard,
        shortcut: `${modLabel()} Shift D`,
        run: () => openModal("dashboard"),
      },
      {
        label: "Vault graph",
        detail: "Map notes and their wikilinks",
        icon: Network,
        shortcut: `${modLabel()} Shift G`,
        run: () => openModal("graph"),
      },
      {
        label: "Find in note",
        detail: "Search the open note or replace text",
        icon: Search,
        shortcut: `${modLabel()} F`,
        run: () =>
          note ? openFind("find") : toast("Open a note first", "default"),
      },
      {
        label: "Save note now",
        detail: "Flush pending changes to the vault",
        icon: Save,
        shortcut: `${modLabel()} S`,
        run: () => {
          if (!note) {
            toast("Open a note first", "default");
            return;
          }
          void saveNow().then(
            () => toast("Note saved", "success"),
            (error: unknown) =>
              toast(
                error instanceof Error ? error.message : "Could not save note",
                "error",
              ),
          );
        },
      },
      {
        label: "Note properties",
        detail: "Status, difficulty, target, tags, and flag",
        icon: SlidersHorizontal,
        shortcut: "F2",
        run: () =>
          note
            ? openModal("properties")
            : toast("Open a note first", "default"),
      },
      {
        label: "Settings",
        detail: "Theme, font size, and scroll sync",
        icon: Settings,
        shortcut: `${modLabel()} ,`,
        run: () => openModal("settings"),
      },
      {
        label: "Motion lab",
        detail: "Preview springs, stagger, and reduced motion",
        icon: Activity,
        run: () => openModal("motion"),
      },
      {
        label:
          theme === "dark" ? "Switch to light theme" : "Switch to dark theme",
        detail: "Toggle the interface theme",
        icon: theme === "dark" ? Sun : Moon,
        run: () => setTheme(theme === "dark" ? "light" : "dark"),
      },
      {
        label: "Toggle focus mode",
        detail: "Hide the sidebar and chrome",
        icon: Focus,
        shortcut: `${modLabel()} Shift L`,
        run: toggleFocusMode,
      },
      {
        label: "Keyboard shortcuts",
        detail: "Every command without the mouse",
        icon: Keyboard,
        shortcut: "F1",
        run: () => openModal("help"),
      },
    ],
    [
      theme,
      note,
      openNewNote,
      openNewFolder,
      openModal,
      openFind,
      saveNow,
      setTheme,
      toggleFocusMode,
      toast,
    ],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .recentNotes(8)
      .then((items) => {
        if (!cancelled) setRecent(items);
      })
      .catch(() => {
        if (!cancelled) setRecent([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setJumps([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api
        .quickJump(text)
        .then((items) => {
          if (!cancelled) setJumps(items);
        })
        .catch(() => {
          if (!cancelled) setJumps([]);
        });
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setSnippets([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api
        .searchSnippets(text)
        .then((items) => {
          if (!cancelled) setSnippets(items.slice(0, 6));
        })
        .catch(() => {
          if (!cancelled) setSnippets([]);
        });
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  const filteredCommands = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((command) =>
      `${command.label} ${command.detail}`.toLowerCase().includes(needle),
    );
  }, [commands, query]);

  const notes = query.trim() ? jumps : recent;
  const entries = useMemo<Entry[]>(
    () => [
      ...filteredCommands.map((command) => ({
        kind: "command" as const,
        command,
      })),
      ...notes.map((node) => ({ kind: "note" as const, node })),
      ...snippets.map((snippet) => ({ kind: "snippet" as const, snippet })),
    ],
    [filteredCommands, notes, snippets],
  );

  useEffect(() => {
    setSelected(0);
  }, [query]);

  useEffect(() => {
    if (selected >= entries.length)
      setSelected(Math.max(0, entries.length - 1));
  }, [entries.length, selected]);

  useEffect(() => {
    document
      .querySelector(".palette-item.selected")
      ?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  const runSnippet = async (snippet: Snippet) => {
    if (note) {
      try {
        const resolved = await api.resolveSnippet(
          snippet.command,
          note.target ?? "",
        );
        window.dispatchEvent(
          new CustomEvent("redscribe:insert-snippet", {
            detail: { text: resolved.command },
          }),
        );
        toast(`Inserted “${snippet.title}”`, "success");
      } catch (error) {
        toast(
          error instanceof Error
            ? error.message
            : "Could not insert the snippet",
          "error",
        );
      }
      return;
    }
    void copyText(snippet.command).then(
      () => toast(`Copied “${snippet.title}”`, "success"),
      () => toast("Could not copy the command", "error"),
    );
  };

  const execute = (entry: Entry | undefined) => {
    if (!entry) return;
    if (entry.kind === "snippet") {
      closeModal();
      void runSnippet(entry.snippet);
      return;
    }
    closeModal();
    if (entry.kind === "command") {
      entry.command.run();
      return;
    }
    void openNote(entry.node.id).catch((error: unknown) =>
      toast(
        error instanceof Error ? error.message : "Could not open note",
        "error",
      ),
    );
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelected((current) =>
        entries.length ? (current + 1) % entries.length : 0,
      );
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelected((current) =>
        entries.length ? (current - 1 + entries.length) % entries.length : 0,
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      execute(entries[selected]);
    }
  };

  let actionIndex = -1;

  return (
    <Modal
      size="palette"
      label="Quick switch"
      hideClose
      bodyClassName="palette-body"
      footer={
        <>
          <span className="modal-hint">
            <kbd>↑</kbd>
            <kbd>↓</kbd> navigate
          </span>
          <span className="modal-hint">
            <kbd>↵</kbd> open
          </span>
          <span className="modal-hint">
            <kbd>Esc</kbd> close
          </span>
        </>
      }
    >
      <div className="palette-input-row">
        <Command />
        <input
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Jump to a note or run a command…"
          spellCheck={false}
          autoComplete="off"
          aria-label="Quick switch"
        />
        <kbd>Esc</kbd>
      </div>
      <div className="palette-list">
        {filteredCommands.length > 0 ? (
          <>
            <div className="list-label">Commands</div>
            {filteredCommands.map((command) => {
              actionIndex += 1;
              const index = actionIndex;
              const Icon = command.icon;
              return (
                <button
                  key={command.label}
                  type="button"
                  className={`palette-item ${selected === index ? "selected" : ""}`}
                  onMouseMove={() => setSelected(index)}
                  onClick={() => execute({ kind: "command", command })}
                >
                  <span className="pi-icon">
                    <Icon />
                  </span>
                  <span className="pi-copy">
                    <span className="pi-title">{command.label}</span>
                    <span className="pi-path">{command.detail}</span>
                  </span>
                  {command.shortcut ? <kbd>{command.shortcut}</kbd> : null}
                </button>
              );
            })}
          </>
        ) : null}

        {notes.length > 0 ? (
          <>
            <div className="list-label">
              {query.trim() ? "Matches" : "Recent notes"}
            </div>
            {notes.map((node) => {
              actionIndex += 1;
              const index = actionIndex;
              return (
                <button
                  key={node.id}
                  type="button"
                  className={`palette-item ${selected === index ? "selected" : ""}`}
                  onMouseMove={() => setSelected(index)}
                  onClick={() => execute({ kind: "note", node })}
                >
                  <span className="pi-icon">
                    <FileText />
                  </span>
                  <span className="pi-copy">
                    <span className="pi-title">{node.title}</span>
                    <span className="pi-path">{node.path || "Vault root"}</span>
                  </span>
                  <span className="pi-meta">
                    {node.pinned ? <Pin /> : null}
                    {node.flag ? <Flag /> : null}
                  </span>
                </button>
              );
            })}
          </>
        ) : null}

        {snippets.length > 0 ? (
          <>
            <div className="list-label">Snippets</div>
            {snippets.map((snippet) => {
              actionIndex += 1;
              const index = actionIndex;
              const key = snippet.builtin
                ? `builtin:${snippet.builtin_key}`
                : `custom:${snippet.id}`;
              return (
                <button
                  key={key}
                  type="button"
                  className={`palette-item ${selected === index ? "selected" : ""}`}
                  onMouseMove={() => setSelected(index)}
                  onClick={() => execute({ kind: "snippet", snippet })}
                >
                  <span className="pi-icon">
                    <Code2 />
                  </span>
                  <span className="pi-copy">
                    <span className="pi-title">{snippet.title}</span>
                    <span className="pi-path">{snippet.command}</span>
                  </span>
                  <span className="pi-meta">{note ? <Plus /> : <Copy />}</span>
                </button>
              );
            })}
          </>
        ) : null}

        {entries.length === 0 && !loading ? (
          <div className="palette-empty">
            No matches. Try a different word, or press <kbd>Esc</kbd> to close.
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
