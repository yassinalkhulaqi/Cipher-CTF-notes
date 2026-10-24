import { useEffect, useState } from "react";
import { Code2, Save, Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

const SNIPPETS_CHANGED = "redscribe:snippets-changed";

export function SnippetFormModal() {
  const snippetEditorId = useUiStore((state) => state.snippetEditorId);
  const closeModal = useUiStore((state) => state.closeModal);
  const askConfirm = useUiStore((state) => state.askConfirm);
  const toast = useUiStore((state) => state.toast);

  const editing = snippetEditorId !== null;
  const [title, setTitle] = useState("");
  const [command, setCommand] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [loading, setLoading] = useState(editing);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (snippetEditorId === null) return;
    let cancelled = false;
    setLoading(true);
    api
      .listSnippets()
      .then((snippets) => {
        if (cancelled) return;
        const snippet = snippets.find((item) => item.id === snippetEditorId);
        if (!snippet) {
          toast("Snippet does not exist", "error");
          closeModal();
          return;
        }
        setTitle(snippet.title);
        setCommand(snippet.command);
        setDescription(snippet.description);
        setTags(snippet.tags);
      })
      .catch((error: unknown) =>
        toast(
          error instanceof Error ? error.message : "Could not load snippet",
          "error",
        ),
      )
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [snippetEditorId, closeModal, toast]);

  const save = async () => {
    if (!command.trim()) {
      toast("A snippet needs a command", "error");
      return;
    }
    setSaving(true);
    try {
      if (editing && snippetEditorId !== null) {
        await api.updateSnippet({
          id: snippetEditorId,
          title: title.trim() || "Untitled snippet",
          command: command.trim(),
          description,
          tags,
        });
        toast("Snippet updated", "success");
      } else {
        await api.createSnippet({
          title: title.trim() || "Untitled snippet",
          command: command.trim(),
          description,
          tags,
        });
        toast("Snippet created", "success");
      }
      window.dispatchEvent(new Event(SNIPPETS_CHANGED));
      closeModal();
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not save snippet",
        "error",
      );
    } finally {
      setSaving(false);
    }
  };

  const remove = () => {
    if (snippetEditorId === null) return;
    const id = snippetEditorId;
    askConfirm({
      title: "Delete snippet",
      message: `Delete “${title || "this snippet"}”? This cannot be undone.`,
      confirmLabel: "Delete snippet",
      danger: true,
      action: async () => {
        try {
          await api.deleteSnippet(id);
          window.dispatchEvent(new Event(SNIPPETS_CHANGED));
          toast("Snippet deleted", "success");
          closeModal();
        } catch (error) {
          toast(
            error instanceof Error ? error.message : "Could not delete snippet",
            "error",
          );
        }
      },
    });
  };

  return (
    <Modal
      title={editing ? "Edit snippet" : "New snippet"}
      subtitle={editing ? "Custom command" : "Reusable command"}
      icon={<Code2 />}
      footer={
        <>
          {editing ? (
            <button
              type="button"
              className="btn danger-ghost sm"
              onClick={remove}
              disabled={saving || loading}
            >
              <Trash2 /> Delete
            </button>
          ) : null}
          <span className="grow" />
          <button type="button" className="btn ghost" onClick={closeModal}>
            Cancel
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={() => void save()}
            disabled={saving || loading}
          >
            <Save /> {saving ? "Saving…" : "Save snippet"}
          </button>
        </>
      }
      label={editing ? "Edit snippet" : "New snippet"}
    >
      <div className="form-stack">
        <div className="field">
          <label htmlFor="snippet-title">Title</label>
          <input
            id="snippet-title"
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            autoFocus
            spellCheck={false}
            autoComplete="off"
            placeholder="Nmap quick scan"
          />
        </div>
        <div className="field">
          <label htmlFor="snippet-command">
            Command{" "}
            <span className="opt">placeholders like {"{{target}}"}</span>
          </label>
          <textarea
            id="snippet-command"
            className="textarea mono-input"
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            rows={4}
            spellCheck={false}
            placeholder="nmap -sC -sV {{target}}"
          />
        </div>
        <div className="field">
          <label htmlFor="snippet-description">Description</label>
          <input
            id="snippet-description"
            className="input"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            spellCheck={false}
            autoComplete="off"
            placeholder="What this command is for"
          />
        </div>
        <div className="field">
          <label htmlFor="snippet-tags">
            Tags <span className="opt">first tag becomes the category</span>
          </label>
          <input
            id="snippet-tags"
            className="input"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            spellCheck={false}
            autoComplete="off"
            placeholder="recon, nmap"
          />
        </div>
      </div>
    </Modal>
  );
}
