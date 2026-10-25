import { useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  Briefcase,
  Bug,
  Crosshair,
  FilePlus2,
  FileText,
  Globe,
  Server,
  type LucideIcon,
} from "lucide-react";
import { api } from "../../lib/api";
import { collectFolders, parentForSelection } from "../../lib/tree";
import type { Template } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

const TEMPLATE_ICONS: Record<string, LucideIcon> = {
  blank: FileText,
  ctf: Crosshair,
  host: Server,
  web: Globe,
  finding: Bug,
  engagement: Briefcase,
  cheatsheet: BookOpen,
};

export function NewNoteModal() {
  const tree = useAppStore((state) => state.tree);
  const nodes = useAppStore((state) => state.nodes);
  const selectedId = useAppStore((state) => state.selectedId);
  const boot = useAppStore((state) => state.boot);
  const createNote = useAppStore((state) => state.createNote);
  const newNoteParent = useUiStore((state) => state.newNoteParent);
  const newNoteTemplate = useUiStore((state) => state.newNoteTemplate);
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);

  const defaultParent =
    newNoteParent === undefined
      ? parentForSelection(nodes, selectedId)
      : newNoteParent;

  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState(
    newNoteTemplate || boot?.last_template || "ctf",
  );
  const [title, setTitle] = useState("");
  const [target, setTarget] = useState("");
  const [parent, setParent] = useState<number | null>(defaultParent);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .templates()
      .then((items) => {
        if (cancelled) return;
        setTemplates(items);
        if (!items.some((template) => template.key === selected)) {
          setSelected(items[0]?.key ?? "blank");
        }
      })
      .catch((error: unknown) =>
        toast(
          error instanceof Error ? error.message : "Could not load templates",
          "error",
        ),
      )
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [toast]);

  const folders = useMemo(() => collectFolders(tree), [tree]);
  const current = templates.find((template) => template.key === selected);

  const create = async () => {
    setCreating(true);
    try {
      const node = await createNote({
        template_key: selected,
        title,
        target,
        parent_id: parent,
      });
      closeModal();
      toast(`Created “${node.title}”`, "success");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not create note",
        "error",
      );
    } finally {
      setCreating(false);
    }
  };

  return (
    <Modal
      title="New note"
      subtitle={current?.name}
      icon={<FilePlus2 />}
      footer={
        <>
          <span className="modal-hint">
            Templates include structure and starter commands
          </span>
          <span className="grow" />
          <button type="button" className="btn ghost" onClick={closeModal}>
            Cancel
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={() => void create()}
            disabled={creating || loading}
          >
            <FilePlus2 /> {creating ? "Creating…" : "Create note"}
          </button>
        </>
      }
      label="New note"
    >
      <div className="template-grid">
        {loading
          ? Array.from({ length: 6 }).map((_, index) => (
              <div className="template-card" key={index}>
                <span className="tc-glyph" />
                <span className="tc-name">Loading…</span>
                <span className="tc-desc">Fetching templates</span>
              </div>
            ))
          : templates.map((template) => {
              const Icon = TEMPLATE_ICONS[template.key] ?? FileText;
              return (
                <button
                  key={template.key}
                  type="button"
                  className={`template-card ${selected === template.key ? "selected" : ""}`}
                  onClick={() => setSelected(template.key)}
                >
                  <span className="tc-glyph">
                    <Icon size={15} />
                  </span>
                  <span className="tc-name">{template.name}</span>
                  <span className="tc-desc">{template.description}</span>
                </button>
              );
            })}
      </div>

      <div className="form-stack">
        <div className="field">
          <label htmlFor="new-note-title">Title</label>
          <input
            id="new-note-title"
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            autoFocus
            spellCheck={false}
            autoComplete="off"
            placeholder={current?.default_title ?? "Untitled note"}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void create();
              }
            }}
          />
        </div>
        <div className="field-row">
          <div className="field">
            <label htmlFor="new-note-target">
              Target <span className="opt">IP, domain, or URL</span>
            </label>
            <input
              id="new-note-target"
              className="input"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              spellCheck={false}
              autoComplete="off"
              placeholder="10.10.10.5"
            />
          </div>
          <div className="field">
            <label htmlFor="new-note-parent">Folder</label>
            <select
              id="new-note-parent"
              className="select"
              value={parent ?? ""}
              onChange={(event) =>
                setParent(
                  event.target.value ? Number(event.target.value) : null,
                )
              }
            >
              <option value="">Vault root</option>
              {folders.map((folder) => (
                <option key={folder.id} value={folder.id}>
                  {"  ".repeat(folder.depth)}
                  {folder.title}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </Modal>
  );
}
