import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import {
  AlertTriangle,
  Bold,
  ChevronDown,
  Code2,
  Columns2,
  Copy,
  Eye,
  FileCode2,
  FileDown,
  Flag,
  Focus,
  Heading1,
  Heading2,
  Italic,
  Link2,
  List,
  ListOrdered,
  MoreHorizontal,
  PenLine,
  Pin,
  PinOff,
  Plus,
  Quote,
  Search,
  SlidersHorizontal,
  SquareCode,
  Strikethrough,
  Tag,
  Target,
  Trash2,
  Upload,
  type LucideIcon,
} from "lucide-react";
import { api } from "../lib/api";
import { usePreview } from "../hooks/usePreview";
import { useMediaQuery } from "../hooks/useMediaQuery";
import {
  MarkdownEditor,
  type MarkdownEditorHandle,
} from "./editor/MarkdownEditor";
import { MarkdownPreview } from "./editor/MarkdownPreview";
import { Menu, type MenuEntry } from "./Menu";
import { StatusIcon } from "./StatusIcon";
import { ScrollProgress } from "../motion/ScrollProgress";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";
import {
  copyText,
  downloadText,
  modLabel,
  plural,
  wordCount,
} from "../lib/utils";
import { STATUS_LABEL } from "../lib/constants";

function ToolButton({
  icon: Icon,
  label,
  shortcut,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  shortcut?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="tool-btn"
      onClick={onClick}
      title={`${label}${shortcut ? ` (${shortcut})` : ""}`}
      aria-label={label}
    >
      <Icon />
    </button>
  );
}

export function NoteWorkspace() {
  const note = useAppStore((state) => state.note);
  const nodes = useAppStore((state) => state.nodes);
  const boot = useAppStore((state) => state.boot);
  const draft = useAppStore((state) => state.draft);
  const saveState = useAppStore((state) => state.saveState);
  const saveNow = useAppStore((state) => state.saveNow);
  const setDraft = useAppStore((state) => state.setDraft);
  const viewMode = useAppStore((state) => state.viewMode);
  const setViewMode = useAppStore((state) => state.setViewMode);
  const split = useAppStore((state) => state.split);
  const setSplit = useAppStore((state) => state.setSplit);
  const syncScroll = useAppStore((state) => state.syncScroll);
  const focusMode = useAppStore((state) => state.focusMode);
  const toggleFocusMode = useAppStore((state) => state.toggleFocusMode);
  const togglePin = useAppStore((state) => state.togglePin);
  const renameCurrent = useAppStore((state) => state.renameCurrent);
  const duplicateNode = useAppStore((state) => state.duplicateNode);
  const trashNode = useAppStore((state) => state.trashNode);
  const openNote = useAppStore((state) => state.openNote);
  const closeNote = useAppStore((state) => state.closeNote);
  const setFilter = useAppStore((state) => state.setFilter);

  const openModal = useUiStore((state) => state.openModal);
  const openFind = useUiStore((state) => state.openFind);
  const askConfirm = useUiStore((state) => state.askConfirm);
  const toast = useUiStore((state) => state.toast);
  const setMobileSidebar = useUiStore((state) => state.setMobileSidebar);

  const editorRef = useRef<MarkdownEditorHandle>(null);
  const previewScrollRef = useRef<HTMLDivElement | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const cancelRename = useRef(false);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [title, setTitle] = useState(note?.title ?? "");
  const [exportMenu, setExportMenu] = useState<{ x: number; y: number } | null>(
    null,
  );
  const [moreMenu, setMoreMenu] = useState<{ x: number; y: number } | null>(
    null,
  );

  const mobile = useMediaQuery("(max-width: 720px)");
  const effectiveView = mobile && viewMode === "split" ? "editor" : viewMode;
  const preview = usePreview(
    draft,
    Boolean(note) && effectiveView !== "editor",
  );
  const words = wordCount(draft);

  const crumbs = useMemo(() => {
    if (!note) return [];
    const chain: { id: number; title: string }[] = [];
    let current = nodes.get(note.id);
    let guard = 0;
    while (current?.parent_id != null && guard < 64) {
      const parent = nodes.get(current.parent_id);
      if (!parent) break;
      chain.unshift({ id: parent.id, title: parent.title });
      current = parent;
      guard += 1;
    }
    return chain;
  }, [nodes, note]);

  useEffect(() => {
    if (!note) return;
    setTitle(note.title);
  }, [note?.id, note?.title]);

  useEffect(() => {
    if (!note) return;
    const timer = window.setTimeout(() => {
      editorRef.current?.focus();
      editorRef.current?.scrollToTop();
      previewScrollRef.current?.scrollTo({ top: 0 });
    }, 50);
    return () => window.clearTimeout(timer);
  }, [note?.id]);

  useEffect(() => {
    const insert = (event: Event) => {
      const detail = (event as CustomEvent<{ text?: string }>).detail;
      if (!detail?.text) return;
      editorRef.current?.insertText(detail.text);
      toast("Snippet inserted at the cursor", "success");
    };
    window.addEventListener("redscribe:insert-snippet", insert);
    return () => window.removeEventListener("redscribe:insert-snippet", insert);
  }, [toast]);

  if (!note) return null;

  const commitTitle = async () => {
    const next = title.trim();
    if (!next) {
      setTitle(note.title);
      return;
    }
    if (next === note.title) return;
    try {
      await renameCurrent(next);
      toast("Renamed", "success");
    } catch (error) {
      setTitle(note.title);
      toast(
        error instanceof Error ? error.message : "Could not rename note",
        "error",
      );
    }
  };

  const handleTitleKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      event.currentTarget.blur();
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelRename.current = true;
      setTitle(note.title);
      event.currentTarget.blur();
    }
  };

  const onTitleBlur = () => {
    if (cancelRename.current) {
      cancelRename.current = false;
      return;
    }
    void commitTitle();
  };

  const syncPreview = (scrollTop: number, scrollable: number) => {
    setScrollProgress(scrollable > 0 ? scrollTop / scrollable : 0);
    if (!syncScroll || effectiveView !== "split") return;
    const previewPane = previewScrollRef.current;
    if (!previewPane || scrollable <= 0) return;
    const previewScrollable =
      previewPane.scrollHeight - previewPane.clientHeight;
    if (previewScrollable <= 0) return;
    previewPane.scrollTop = (scrollTop / scrollable) * previewScrollable;
  };

  const startSplitDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const body = bodyRef.current;
    if (!body) return;
    const rect = body.getBoundingClientRect();
    const handle = event.currentTarget;
    handle.classList.add("dragging");
    const onMove = (moveEvent: PointerEvent) => {
      const percent = ((moveEvent.clientX - rect.left) / rect.width) * 100;
      setSplit(percent, false);
    };
    const onUp = () => {
      handle.classList.remove("dragging");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      setSplit(useAppStore.getState().split, true);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  };

  const splitKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setSplit(split - 2, true);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      setSplit(split + 2, true);
    } else if (event.key === "Home") {
      event.preventDefault();
      setSplit(25, true);
    } else if (event.key === "End") {
      event.preventDefault();
      setSplit(80, true);
    }
  };

  const exportNote = async (format: "md" | "html") => {
    try {
      const payload =
        format === "md"
          ? await api.exportNoteMarkdown(note.id)
          : await api.exportNoteHtml(note.id);
      downloadText(payload.filename, payload.content, payload.mime);
      toast(`${format === "md" ? "Markdown" : "HTML"} export ready`, "success");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not export note",
        "error",
      );
    }
  };

  const exportItems: MenuEntry[] = [
    {
      label: "Export note as Markdown",
      icon: FileDown,
      onSelect: () => void exportNote("md"),
    },
    {
      label: "Export note as HTML",
      icon: Code2,
      onSelect: () => void exportNote("html"),
    },
    "separator",
    {
      label: "Export whole vault as HTML",
      icon: FileDown,
      onSelect: () => {
        void api
          .exportVaultHtml()
          .then((payload) => {
            downloadText(payload.filename, payload.content, payload.mime);
            toast("Vault export ready", "success");
          })
          .catch((error: unknown) =>
            toast(
              error instanceof Error
                ? error.message
                : "Could not export the vault",
              "error",
            ),
          );
      },
    },
    {
      label: "Export whole vault as Print HTML",
      icon: FileDown,
      onSelect: () => {
        void api
          .exportVaultPrint()
          .then((payload) => {
            downloadText(payload.filename, payload.content, payload.mime);
            toast("Vault print export ready", "success");
          })
          .catch((error: unknown) =>
            toast(
              error instanceof Error
                ? error.message
                : "Could not export the vault print",
              "error",
            ),
          );
      },
    },
  ];

  const moreItems: MenuEntry[] = [
    {
      label: "Duplicate note",
      icon: Copy,
      onSelect: () => {
        void duplicateNode(note.id).then(
          () => toast("Note duplicated", "success"),
          (error: unknown) =>
            toast(
              error instanceof Error ? error.message : "Could not duplicate",
              "error",
            ),
        );
      },
    },
    {
      label: "Copy vault path",
      icon: Copy,
      onSelect: () => {
        void copyText(boot?.vault_path ?? note.path).then(
          () => toast("Vault path copied", "success"),
          () => toast("Could not copy path", "error"),
        );
      },
    },
    "separator",
    {
      label: "Move to trash",
      icon: Trash2,
      danger: true,
      onSelect: () => {
        askConfirm({
          title: "Move to trash",
          message: `Move “${note.title}” to the trash?`,
          confirmLabel: "Move to trash",
          danger: true,
          action: async () => {
            try {
              await trashNode(note.id);
              toast("Moved to trash");
            } catch (error) {
              toast(
                error instanceof Error ? error.message : "Could not move note",
                "error",
              );
            }
          },
        });
      },
    },
  ];

  const copyFlag = () => {
    if (!note.flag) return;
    void copyText(note.flag).then(
      () => toast("Flag copied", "success"),
      () => toast("Could not copy the flag", "error"),
    );
  };

  const close = () => {
    void closeNote().catch((error: unknown) =>
      toast(
        error instanceof Error ? error.message : "Could not save the note",
        "error",
      ),
    );
  };

  const goTo = (id: number) => {
    void openNote(id).catch((error: unknown) =>
      toast(
        error instanceof Error ? error.message : "Could not open note",
        "error",
      ),
    );
  };

  const formatButton = (
    icon: LucideIcon,
    label: string,
    shortcut: string | undefined,
    action: () => void,
  ): ReactNode => (
    <ToolButton
      icon={icon}
      label={label}
      shortcut={shortcut}
      onClick={action}
    />
  );

  return (
    <section className="note">
      <ScrollProgress
        value={scrollProgress}
        visible={scrollProgress > 0.01 && scrollProgress < 0.995}
      />
      <header className="note-head">
        <div className="note-topline">
          <div className="breadcrumbs" aria-label="Breadcrumb">
            <button type="button" onClick={close}>
              Vault
            </button>
            {crumbs.map((crumb) => (
              <span key={crumb.id} style={{ display: "contents" }}>
                <span className="sep">/</span>
                <button
                  type="button"
                  onClick={() => goTo(crumb.id)}
                  title={crumb.title}
                >
                  {crumb.title}
                </button>
              </span>
            ))}
            <span className="sep">/</span>
            <span className="current">{note.title}</span>
          </div>

          <div className="note-actions">
            <button
              className={`icon-btn ${note.pinned ? "active" : ""}`}
              type="button"
              onClick={() => {
                void togglePin(note.id).then(
                  () =>
                    toast(
                      note.pinned ? "Note unpinned" : "Note pinned",
                      "success",
                    ),
                  (error: unknown) =>
                    toast(
                      error instanceof Error
                        ? error.message
                        : "Could not update pin",
                      "error",
                    ),
                );
              }}
              title={`${note.pinned ? "Unpin note" : "Pin note"} (${modLabel()}+Shift+P)`}
              aria-label={note.pinned ? "Unpin note" : "Pin note"}
            >
              {note.pinned ? <PinOff /> : <Pin />}
            </button>
            <button
              className="icon-btn"
              type="button"
              onClick={() => openModal("properties")}
              title="Note properties (F2)"
              aria-label="Note properties"
            >
              <SlidersHorizontal />
            </button>
            <button
              className="icon-btn"
              type="button"
              onClick={(event) => {
                const rect = event.currentTarget.getBoundingClientRect();
                setExportMenu({ x: rect.right - 232, y: rect.bottom + 5 });
              }}
              title="Export"
              aria-label="Export"
            >
              <FileDown />
              <ChevronDown className="icon-caret" />
            </button>
            <button
              className={`icon-btn ${focusMode ? "active" : ""}`}
              type="button"
              onClick={toggleFocusMode}
              title={`Toggle focus mode (${modLabel()}+Shift+L)`}
              aria-label="Toggle focus mode"
            >
              <Focus />
            </button>
            <span className="sep-line" />
            <button
              className="icon-btn"
              type="button"
              onClick={(event) => {
                const rect = event.currentTarget.getBoundingClientRect();
                setMoreMenu({ x: rect.right - 208, y: rect.bottom + 5 });
              }}
              title="More actions"
              aria-label="More actions"
            >
              <MoreHorizontal />
            </button>
            <div className="view-switch" role="group" aria-label="Editor view">
              <button
                type="button"
                aria-pressed={viewMode === "editor"}
                onClick={() => setViewMode("editor")}
                title="Editor only"
              >
                <PenLine />
                <span>Editor</span>
              </button>
              <button
                type="button"
                aria-pressed={viewMode === "split"}
                onClick={() => setViewMode("split")}
                title="Split editor and preview"
              >
                <Columns2 />
                <span>Split</span>
              </button>
              <button
                type="button"
                aria-pressed={viewMode === "preview"}
                onClick={() => setViewMode("preview")}
                title="Preview only"
              >
                <Eye />
                <span>Preview</span>
              </button>
            </div>
          </div>
        </div>

        <div className="title-row">
          <input
            className="title-input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            onBlur={onTitleBlur}
            onKeyDown={handleTitleKey}
            spellCheck={false}
            autoComplete="off"
            aria-label="Note title"
            placeholder="Untitled note"
          />
        </div>

        <div className="meta-row">
          <button
            type="button"
            className={`chip status-${note.status}`}
            onClick={() => openModal("properties")}
            title="Edit note status"
          >
            <StatusIcon status={note.status} />
            {STATUS_LABEL[note.status]}
          </button>
          {note.difficulty ? (
            <button
              type="button"
              className="chip difficulty"
              onClick={() => openModal("properties")}
              title="Edit difficulty"
            >
              {note.difficulty}
            </button>
          ) : null}
          {note.target ? (
            <button
              type="button"
              className="chip target"
              onClick={() => {
                void copyText(note.target).then(
                  () => toast("Target copied", "success"),
                  () => toast("Could not copy target", "error"),
                );
              }}
              title="Copy target"
            >
              <Target />
              {note.target}
            </button>
          ) : null}
          {note.flag ? (
            <button
              type="button"
              className="chip flag"
              onClick={copyFlag}
              title="Copy flag"
            >
              <Flag />
              {note.flag}
            </button>
          ) : null}
          {note.tag_list.map((tag) => (
            <button
              key={tag}
              type="button"
              className="chip tag"
              onClick={() => {
                setFilter(tag);
                setMobileSidebar(true);
              }}
              title={`Filter vault by #${tag}`}
            >
              <Tag />
              {tag}
            </button>
          ))}
          <button
            type="button"
            className="chip add"
            onClick={() => openModal("properties")}
            title="Edit tags and properties"
          >
            <Plus />
            {note.tag_list.length === 0 ? "Add details" : "Tag"}
          </button>
        </div>
      </header>

      {saveState === "error" ? (
        <div className="save-error-banner" role="alert">
          <AlertTriangle />
          <span className="grow">
            This note could not be saved. Your draft is still open.
          </span>
          <button
            type="button"
            className="btn tiny danger-ghost"
            onClick={() => {
              void saveNow().then(
                () => toast("Note saved", "success"),
                () => toast("Save failed again", "error"),
              );
            }}
          >
            Retry save
          </button>
        </div>
      ) : null}

      <div ref={bodyRef} className="note-body" data-view={effectiveView}>
        <section
          className="pane editor-pane"
          style={{ flexBasis: `${split}%` }}
        >
          <div className="pane-head editor-pane-head">
            <span className="pane-label">
              <FileCode2 />
              Markdown
            </span>
            <div
              className="format-toolbar"
              role="toolbar"
              aria-label="Formatting"
            >
              {formatButton(Bold, "Bold", `${modLabel()}+B`, () =>
                editorRef.current?.wrapSelection("**", "**", "bold text"),
              )}
              {formatButton(Italic, "Italic", `${modLabel()}+I`, () =>
                editorRef.current?.wrapSelection("*", "*", "italic"),
              )}
              {formatButton(
                Strikethrough,
                "Strikethrough",
                `${modLabel()}+Shift+X`,
                () =>
                  editorRef.current?.wrapSelection("~~", "~~", "struck out"),
              )}
              {formatButton(Code2, "Inline code", `${modLabel()}+K`, () =>
                editorRef.current?.wrapSelection("`", "`", "code"),
              )}
              <span className="tool-sep" />
              {formatButton(Heading1, "Heading 1", undefined, () =>
                editorRef.current?.toggleLinePrefix("# "),
              )}
              {formatButton(Heading2, "Heading 2", undefined, () =>
                editorRef.current?.toggleLinePrefix("## "),
              )}
              {formatButton(List, "Bulleted list", undefined, () =>
                editorRef.current?.toggleLinePrefix("- "),
              )}
              {formatButton(ListOrdered, "Numbered list", undefined, () =>
                editorRef.current?.toggleLinePrefix("1. "),
              )}
              {formatButton(Quote, "Blockquote", undefined, () =>
                editorRef.current?.toggleLinePrefix("> "),
              )}
              {formatButton(Link2, "Link", undefined, () =>
                editorRef.current?.wrapSelection("[", "](https://)", "label"),
              )}
              {formatButton(SquareCode, "Code block", undefined, () =>
                editorRef.current?.insertBlock("```bash\n\n```\n"),
              )}
              {formatButton(Upload, "Attach file", `${modLabel()}+U`, () =>
                editorRef.current?.insertText("[[attachment:]]"),
              )}
              <span className="tool-sep" />
              {formatButton(Search, "Find in note", `${modLabel()}+F`, () =>
                openFind("find"),
              )}
            </div>
            <span className="pane-meta">{plural(words, "word")}</span>
            <button
              type="button"
              className="icon-btn sm pane-copy"
              onClick={() => {
                void copyText(draft).then(
                  () => toast("Note Markdown copied", "success"),
                  () => toast("Could not copy note", "error"),
                );
              }}
              title="Copy note Markdown"
              aria-label="Copy note Markdown"
            >
              <Copy />
            </button>
          </div>
          <MarkdownEditor
            ref={editorRef}
            noteId={note.id}
            value={draft}
            onChange={setDraft}
            onScroll={syncPreview}
            placeholder="# Start writing…"
            ariaLabel="Note content"
          />
        </section>

        <div
          className="sash split-sash"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize editor and preview"
          aria-valuemin={25}
          aria-valuemax={80}
          aria-valuenow={Math.round(split)}
          tabIndex={0}
          onPointerDown={startSplitDrag}
          onKeyDown={splitKey}
        />

        <section className="pane preview-pane">
          <div className="pane-head">
            <span className="pane-label">
              <Eye />
              Preview
            </span>
            <span className="pane-meta">
              {preview.pending ? (
                <span className="preview-pending">
                  <span className="dot" />
                  Rendering
                </span>
              ) : (
                "Rendered locally"
              )}
            </span>
          </div>
          <MarkdownPreview
            html={preview.html}
            scrollRef={previewScrollRef}
            emptyText="Nothing to preview yet. Start typing in the editor to see the rendered note."
          />
        </section>
      </div>

      {exportMenu ? (
        <Menu
          x={exportMenu.x}
          y={exportMenu.y}
          items={exportItems}
          onClose={() => setExportMenu(null)}
          label="Export"
        />
      ) : null}
      {moreMenu ? (
        <Menu
          x={moreMenu.x}
          y={moreMenu.y}
          items={moreItems}
          onClose={() => setMoreMenu(null)}
          label="More note actions"
        />
      ) : null}
    </section>
  );
}
