import { useState } from "react";
import { ClipboardPaste, Save, Zap } from "lucide-react";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

export function QuickCaptureModal() {
  const quickCapture = useAppStore((state) => state.quickCapture);
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);

  const [title, setTitle] = useState("");
  const [target, setTarget] = useState("");
  const [tags, setTags] = useState("");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);

  const pasteClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text) {
        toast("Clipboard is empty", "default");
        return;
      }
      setContent((current) => (current ? `${current}\n\n${text}` : text));
    } catch {
      toast("Could not read the clipboard", "error");
    }
  };

  const save = async () => {
    if (!title.trim() && !content.trim()) {
      toast("Add a title or some content first", "default");
      return;
    }
    setSaving(true);
    try {
      const node = await quickCapture({ title, content, target, tags });
      closeModal();
      toast(`Captured “${node.title}”`, "success");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not capture this note",
        "error",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="Quick capture"
      subtitle="Raw text straight into a note"
      icon={<Zap />}
      footer={
        <>
          <span className="modal-hint">Capture opens the note for editing</span>
          <span className="grow" />
          <button type="button" className="btn ghost" onClick={closeModal}>
            Cancel
          </button>
          <button
            type="button"
            className="btn primary"
            onClick={() => void save()}
            disabled={saving}
          >
            <Save /> {saving ? "Capturing…" : "Capture note"}
          </button>
        </>
      }
      label="Quick capture"
    >
      <div className="form-stack">
        <div className="field">
          <label htmlFor="qc-title">Title</label>
          <input
            id="qc-title"
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            autoFocus
            spellCheck={false}
            autoComplete="off"
            placeholder="Untitled"
          />
        </div>
        <div className="field-row">
          <div className="field">
            <label htmlFor="qc-target">Target</label>
            <input
              id="qc-target"
              className="input"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              spellCheck={false}
              autoComplete="off"
              placeholder="10.10.10.5"
            />
          </div>
          <div className="field">
            <label htmlFor="qc-tags">Tags</label>
            <input
              id="qc-tags"
              className="input"
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              spellCheck={false}
              autoComplete="off"
              placeholder="recon, web"
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="qc-content">Content</label>
          <textarea
            id="qc-content"
            className="textarea capture-area"
            value={content}
            onChange={(event) => setContent(event.target.value)}
            spellCheck={false}
            placeholder="Anything worth remembering — scan output, a lead, a flag…"
          />
          <div className="capture-actions">
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => void pasteClipboard()}
            >
              <ClipboardPaste /> Paste from clipboard
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
