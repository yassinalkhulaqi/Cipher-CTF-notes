import { useEffect, useMemo, useState } from "react";
import { Pin, Save, SlidersHorizontal } from "lucide-react";
import { api } from "../../lib/api";
import { DIFFICULTIES, STATUSES, STATUS_LABEL } from "../../lib/constants";
import type { FlagPattern, Status } from "../../lib/types";
import { formatDate } from "../../lib/utils";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

export function PropertiesModal() {
  const note = useAppStore((state) => state.note);
  const renameCurrent = useAppStore((state) => state.renameCurrent);
  const updateCurrent = useAppStore((state) => state.updateCurrent);
  const togglePin = useAppStore((state) => state.togglePin);
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);

  const [title, setTitle] = useState(note?.title ?? "");
  const [status, setStatus] = useState<Status>(
    (note?.status as Status) ?? "todo",
  );
  const [difficulty, setDifficulty] = useState<string>(note?.difficulty ?? "");
  const [target, setTarget] = useState(note?.target ?? "");
  const [tags, setTags] = useState(note?.tags ?? "");
  const [flag, setFlag] = useState(note?.flag ?? "");
  const [pinned, setPinned] = useState(note?.pinned ?? false);
  const [saving, setSaving] = useState(false);
  const [patterns, setPatterns] = useState<FlagPattern[]>([]);

  useEffect(() => {
    if (!note) return;
    setTitle(note.title);
    setStatus(note.status as Status);
    setDifficulty(note.difficulty);
    setTarget(note.target);
    setTags(note.tags);
    setFlag(note.flag);
    setPinned(note.pinned);
  }, [note]);

  useEffect(() => {
    let cancelled = false;
    api
      .flagPatterns()
      .then((items) => {
        if (!cancelled) setPatterns(items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const matchedPattern = useMemo<FlagPattern | null>(() => {
    const brace = flag.indexOf("{");
    if (brace <= 0) return null;
    const prefix = flag.slice(0, brace).trim().toLowerCase();
    return patterns.find((pattern) => pattern.pattern_key === prefix) ?? null;
  }, [flag, patterns]);

  if (!note) return null;

  const save = async () => {
    setSaving(true);
    try {
      if (title.trim() && title.trim() !== note.title) {
        await renameCurrent(title.trim());
      }
      await updateCurrent({ status, difficulty, target, tags, flag });
      if (pinned !== note.pinned) {
        await togglePin(note.id);
      }
      closeModal();
      toast("Properties saved", "success");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not save properties",
        "error",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="Note properties"
      subtitle={note.path || "Vault root"}
      icon={<SlidersHorizontal />}
      footer={
        <>
          <span className="modal-hint">
            Updated {formatDate(note.updated_at, true)} · Created{" "}
            {formatDate(note.created_at)}
          </span>
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
            <Save /> {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
      label="Note properties"
    >
      <div className="form-stack">
        <div className="field">
          <label htmlFor="prop-title">Title</label>
          <input
            id="prop-title"
            className="input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            autoFocus
            spellCheck={false}
            autoComplete="off"
          />
        </div>
        <div className="field-row">
          <div className="field">
            <label htmlFor="prop-status">Status</label>
            <select
              id="prop-status"
              className="select"
              value={status}
              onChange={(event) => setStatus(event.target.value as Status)}
            >
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {STATUS_LABEL[value]}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="prop-difficulty">Difficulty</label>
            <select
              id="prop-difficulty"
              className="select"
              value={difficulty}
              onChange={(event) => setDifficulty(event.target.value)}
            >
              {DIFFICULTIES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="field-row">
          <div className="field">
            <label htmlFor="prop-target">Target</label>
            <input
              id="prop-target"
              className="input"
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              spellCheck={false}
              autoComplete="off"
              placeholder="10.10.10.5"
            />
          </div>
          <div className="field">
            <label htmlFor="prop-tags">Tags</label>
            <input
              id="prop-tags"
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
          <label htmlFor="prop-flag">Flag</label>
          <input
            id="prop-flag"
            className="input mono-input"
            value={flag}
            onChange={(event) => setFlag(event.target.value)}
            spellCheck={false}
            autoComplete="off"
            placeholder="CTF{...}"
          />
          {matchedPattern ? (
            <span className="field-hint">
              Looks like a {matchedPattern.platform} flag —{" "}
              {matchedPattern.hint}.
            </span>
          ) : null}
          {patterns.length > 0 ? (
            <div
              className="flag-chips"
              aria-label="Start a flag with a known prefix"
            >
              {patterns.slice(0, 8).map((pattern) => (
                <button
                  key={pattern.pattern_key}
                  type="button"
                  className="flag-chip"
                  onClick={() => setFlag(`${pattern.prefix}{`)}
                  title={`Start a ${pattern.platform} flag`}
                >
                  {pattern.example}
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={pinned}
            onChange={(event) => setPinned(event.target.checked)}
          />
          <Pin size={14} /> Pin this note to the top of the sidebar
        </label>
      </div>
    </Modal>
  );
}
