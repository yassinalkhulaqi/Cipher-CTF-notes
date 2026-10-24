import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  ChevronDown,
  Code2,
  Columns2,
  Copy,
  Eye,
  FileDown,
  Flag,
  Focus,
  MoreHorizontal,
  PenLine,
  Pin,
  PinOff,
  Plus,
  SlidersHorizontal,
  Tag,
  Target,
  Trash2,
} from "lucide-react";
import { downloadNote, downloadVault } from "../lib/api";
import { STATUS_LABEL } from "../lib/constants";
import { usePreview } from "../hooks/usePreview";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { Menu, type MenuEntry } from "./Menu";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";
import { copyText, plural, wordCount } from "../lib/utils";

export function NoteWorkspace() {
  const note = useAppStore((state) => state.note);
  const nodes = useAppStore((state) => state.nodes);
  const draft = useAppStore((state) => state.draft);
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
  const askConfirm = useUiStore((state) => state.askConfirm);
  const toast = useUiStore((state) => state.toast);
  const setMobileSidebar = useUiStore((state) => state.setMobileSidebar);

  const editorRef = useRef<HTMLTextAreaElement>(null);
  const previewScrollRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const cancelRename = useRef(false);
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
      previewScrollRef.current?.scrollTo({ top: 0 });
      if (editorRef.current) editorRef.current.scrollTop = 0;
    }, 50);
    return () => window.clearTimeout(timer);
  }, [note?.id]);

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

  const applyEditorText = (replacement: string, start: number, end: number) => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.setRangeText(replacement, start, end, "end");
    setDraft(editor.value);
  };

  const wrapSelection = (
    prefix: string,
    suffix: string,
    placeholder: string,
  ) => {
    const editor = editorRef.current;
    if (!editor) return;
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const selected = editor.value.slice(start, end);
    let nextStart = start;
    let nextEnd = end;
    if (selected.startsWith(prefix) && selected.endsWith(suffix)) {
      const inner = selected.slice(
        prefix.length,
        selected.length - suffix.length,
      );
      applyEditorText(inner, start, end);
      nextStart = start;
      nextEnd = start + inner.length;
    } else {
      const inner = selected || placeholder;
      applyEditorText(prefix + inner + suffix, start, end);
      nextStart = start + prefix.length;
      nextEnd = start + prefix.length + inner.length;
    }
    window.requestAnimationFrame(() => {
      editor.focus();
      editor.setSelectionRange(nextStart, nextEnd);
    });
  };

  const indentSelection = (outdent: boolean) => {
    const editor = editorRef.current;
    if (!editor) return;
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const lineStart = editor.value.lastIndexOf("\n", start - 1) + 1;
    let lineEnd = editor.value.indexOf("\n", end);
    if (lineEnd < 0) lineEnd = editor.value.length;
    const lines = editor.value.slice(lineStart, lineEnd).split("\n");
    const shifted = lines.map((line) =>
      outdent ? line.replace(/^(\t| {1,4})/, "") : `    ${line}`,
    );
    const replacement = shifted.join("\n");
    applyEditorText(replacement, lineStart, lineEnd);
    window.requestAnimationFrame(() => {
      editor.focus();
      editor.setSelectionRange(lineStart, lineStart + replacement.length);
    });
  };

  const continueList = (): boolean => {
    const editor = editorRef.current;
    if (!editor) return false;
    const start = editor.selectionStart;
    const lineStart = editor.value.lastIndexOf("\n", start - 1) + 1;
    let lineEnd = editor.value.indexOf("\n", start);
    if (lineEnd < 0) lineEnd = editor.value.length;
    const line = editor.value.slice(lineStart, lineEnd);
    const match = /^(\s*)([-+*] \[[ xX]\] |[-+*] |\d{1,9}[.)] )(.*)$/.exec(
      line,
    );
    if (!match) return false;
    const marker = match[2] ?? "";
    const body = match[3] ?? "";
    if (!body.trim()) return false;
    let nextMarker = marker;
    const numbered = /^(\d{1,9})([.)] )$/.exec(marker);
    if (numbered) nextMarker = `${Number(numbered[1]) + 1}${numbered[2]}`;
    applyEditorText(`\n${match[1] ?? ""}${nextMarker}`, start, start);
    window.requestAnimationFrame(() => editor.focus());
    return true;
  };

  const handleEditorKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    const control = event.ctrlKey || event.metaKey;
    if (event.key === "Tab") {
      event.preventDefault();
      indentSelection(event.shiftKey);
      return;
    }
    if (
      event.key === "Enter" &&
      !control &&
      !event.shiftKey &&
      continueList()
    ) {
      event.preventDefault();
      return;
    }
    if (!control) return;
    const key = event.key.toLowerCase();
    if (key === "b") {
      event.preventDefault();
      wrapSelection("**", "**", "bold text");
    } else if (key === "i") {
      event.preventDefault();
      wrapSelection("*", "*", "italic");
    } else if (key === "k") {
      event.preventDefault();
      wrapSelection("`", "`", "code");
    } else if (event.shiftKey && key === "x") {
      event.preventDefault();
      wrapSelection("~~", "~~", "struck out");
    }
  };

  const handleEditorScroll = () => {
    if (!syncScroll || effectiveView !== "split") return;
    const editor = editorRef.current;
    const previewPane = previewScrollRef.current;
    if (!editor || !previewPane) return;
    const editorScrollable = editor.scrollHeight - editor.clientHeight;
    const previewScrollable =
      previewPane.scrollHeight - previewPane.clientHeight;
    if (editorScrollable <= 0 || previewScrollable <= 0) return;
    previewPane.scrollTop =
      (editor.scrollTop / editorScrollable) * previewScrollable;
  };

  const startSplitDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const body = bodyRef.current;
    if (!body) return;
    const rect = body.getBoundingClientRect();
    const onMove = (moveEvent: PointerEvent) => {
      const percent = ((moveEvent.clientX - rect.left) / rect.width) * 100;
      setSplit(percent, false);
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      setSplit(useAppStore.getState().split, true);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  };

  const exportItems: MenuEntry[] = [
    {
      label: "Export as Markdown",
      icon: FileDown,
      onSelect: () => {
        downloadNote(note.id, "md");
        toast("Export started");
      },
    },
    {
      label: "Export as HTML",
      icon: Code2,
      onSelect: () => {
        downloadNote(note.id, "html");
        toast("Export started");
      },
    },
    "separator",
    {
      label: "Export whole vault",
      icon: FileDown,
      onSelect: () => {
        downloadVault();
        toast("Vault export started");
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
        void copyText(note.path || note.title).then(
          () => toast("Path copied", "success"),
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

  return (
    <section className="note">
      <header className="note-head">
        <div className="note-topline">
          <div className="breadcrumbs" aria-label="Breadcrumb">
            <button type="button" onClick={() => void closeNote()}>
              Vault
            </button>
            {crumbs.map((crumb) => (
              <span key={crumb.id} style={{ display: "contents" }}>
                <span className="sep">/</span>
                <button
                  type="button"
                  onClick={() => void openNote(crumb.id)}
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
              title={note.pinned ? "Unpin note" : "Pin note"}
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
                setExportMenu({ x: rect.right - 230, y: rect.bottom + 6 });
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
              title="Toggle focus mode"
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
                setMoreMenu({ x: rect.right - 210, y: rect.bottom + 6 });
              }}
              title="More actions"
              aria-label="More actions"
            >
              <MoreHorizontal />
            </button>
            <div
              className="view-switch"
              role="tablist"
              aria-label="Editor view"
            >
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
            ref={titleRef}
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
            <span className={`dot ${note.status}`} />
            {STATUS_LABEL[note.status]}
          </button>
          {note.difficulty ? (
            <button
              type="button"
              className="chip difficulty"
              onClick={() => openModal("properties")}
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

      <div ref={bodyRef} className="note-body" data-view={effectiveView}>
        <section
          className="pane editor-pane"
          style={{ flexBasis: `${split}%` }}
        >
          <div className="pane-head">
            <span>Markdown</span>
            <span className="pane-meta">{plural(words, "word")}</span>
          </div>
          <textarea
            ref={editorRef}
            className="editor-area"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleEditorKey}
            onScroll={handleEditorScroll}
            spellCheck={false}
            autoComplete="off"
            placeholder="# Start writing…"
            aria-label="Note content"
          />
        </section>

        <div
          className="sash split-sash"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize editor and preview"
          onPointerDown={startSplitDrag}
        />

        <section className="pane preview-pane">
          <div className="pane-head">
            <span>Preview</span>
            <span className="pane-meta">
              {preview.pending ? (
                <span className="preview-pending">
                  <span className="dot" />
                  Rendering
                </span>
              ) : (
                "Live markdown"
              )}
            </span>
          </div>
          <div ref={previewScrollRef} className="preview-scroll">
            <div className="preview-inner">
              {preview.html ? (
                <div
                  className="markdown"
                  dangerouslySetInnerHTML={{ __html: preview.html }}
                />
              ) : (
                <div className="markdown">
                  <p className="preview-empty">
                    Nothing to preview yet. Start typing in the editor to see
                    the rendered note.
                  </p>
                </div>
              )}
            </div>
          </div>
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
