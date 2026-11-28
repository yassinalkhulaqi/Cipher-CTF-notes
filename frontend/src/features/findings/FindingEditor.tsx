import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";

import { CvssCalculator } from "./CvssCalculator";
import {
  DuplicateSuggestions,
  type DuplicateSuggestionsProps,
} from "./DuplicateSuggestions";
import {
  RemediationChecklist,
  type RemediationChecklistProps,
} from "./RemediationChecklist";
import { RetestPanel, type RetestPanelProps } from "./RetestPanel";
import { nextSection, severityTone, type EditorSection } from "./logic";
import type { FindingDetail, ScorePreview } from "./types";

export interface FindingEditorProps {
  detail: FindingDetail;
  preview: ScorePreview | null;
  onPreview: (vector: string) => Promise<void>;
  onSave: (fields: {
    title: string;
    summary: string;
    owner: string;
    tags: string[];
  }) => Promise<void>;
  onVectorChange: (vector: string) => Promise<void>;
  onTransitionAction: (action: string, note: string) => Promise<void>;
  onMarkDuplicate: DuplicateSuggestionsProps["onMark"];
  onRefreshDuplicates: () => Promise<void>;
  remediation: Omit<RemediationChecklistProps, "detail">;
  retest: Omit<RetestPanelProps, "detail">;
  busy?: boolean;
  onCancel?: () => void;
}

const NOTE_REQUIRED = new Set(["dismiss", "reopen", "regress"]);

export function FindingEditor({
  detail,
  preview,
  onPreview,
  onSave,
  onVectorChange,
  onTransitionAction,
  onMarkDuplicate,
  onRefreshDuplicates,
  remediation,
  retest,
  busy = false,
  onCancel,
}: FindingEditorProps) {
  const finding = detail.finding;
  const [title, setTitle] = useState(finding.title);
  const [summary, setSummary] = useState(finding.summary);
  const [owner, setOwner] = useState(finding.owner);
  const [tags, setTags] = useState(finding.tags.join(", "));
  const [vector, setVector] = useState(finding.vector);
  const [note, setNote] = useState("");
  const [section, setSection] = useState<EditorSection>("details");
  const [error, setError] = useState("");

  useEffect(() => {
    setTitle(finding.title);
    setSummary(finding.summary);
    setOwner(finding.owner);
    setTags(finding.tags.join(", "));
    setVector(finding.vector);
    setNote("");
  }, [
    finding.ref,
    finding.version,
    finding.title,
    finding.summary,
    finding.owner,
    finding.vector,
  ]);

  const save = async () => {
    try {
      await onSave({
        title: title.trim() || finding.title,
        summary,
        owner,
        tags: tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      });
      setError("");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not save finding",
      );
    }
  };

  const handleKeyboard = (event: KeyboardEvent<HTMLElement>) => {
    if (
      event.altKey &&
      (event.key === "ArrowRight" || event.key === "ArrowLeft")
    ) {
      event.preventDefault();
      setSection((current) =>
        nextSection(current, event.key === "ArrowRight" ? 1 : -1),
      );
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      void save();
      return;
    }
    if (
      (event.ctrlKey || event.metaKey) &&
      event.key === "Enter" &&
      finding.state === "draft"
    ) {
      event.preventDefault();
      void onTransitionAction("confirm", note).catch(() => undefined);
      return;
    }
    if (event.key === "Escape" && onCancel) {
      event.preventDefault();
      onCancel();
    }
  };

  const runTransition = async (
    action: string,
    event: FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();
    if (NOTE_REQUIRED.has(action) && !note.trim()) {
      setError(`A note is required for ${action}.`);
      return;
    }
    try {
      await onTransitionAction(action, note);
      setNote("");
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `Could not ${action}`);
    }
  };

  const actions = detail.lifecycle.actions;

  return (
    <div
      className="finding-editor"
      data-testid="finding-editor"
      data-section={section}
      data-severity={finding.severity}
      tabIndex={0}
      onKeyDown={handleKeyboard}
      aria-label={`Editor for ${finding.title}`}
    >
      <nav
        className="finding-editor__tabs"
        aria-label="Finding editor sections"
      >
        {(
          [
            "details",
            "cvss",
            "remediation",
            "retest",
            "duplicates",
          ] as EditorSection[]
        ).map((tab) => (
          <button
            type="button"
            key={tab}
            data-active={section === tab}
            aria-current={section === tab ? "true" : undefined}
            onClick={() => setSection(tab)}
          >
            {tab}
          </button>
        ))}
      </nav>

      <div
        className="finding-editor__section"
        data-section="details"
        hidden={section !== "details"}
      >
        <div className="finding-editor__heading">
          <span className="finding-editor__ref">{finding.ref}</span>
          <span
            className="finding-editor__severity"
            data-tone={severityTone(finding.severity)}
          >
            {finding.severity} · {finding.score.toFixed(1)}
          </span>
        </div>
        <label htmlFor="finding-title">Title</label>
        <input
          id="finding-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          disabled={busy}
        />
        <label htmlFor="finding-summary">Summary</label>
        <textarea
          id="finding-summary"
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          rows={4}
          disabled={busy}
        />
        <div className="finding-editor__row">
          <label htmlFor="finding-owner">Owner</label>
          <input
            id="finding-owner"
            value={owner}
            onChange={(event) => setOwner(event.target.value)}
            disabled={busy}
          />
          <label htmlFor="finding-tags">Tags (comma separated)</label>
          <input
            id="finding-tags"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            disabled={busy}
          />
        </div>
        <button type="button" onClick={() => void save()} disabled={busy}>
          Save details (Ctrl+S)
        </button>
        <form
          className="finding-editor__transitions"
          onSubmit={(event) => void event.preventDefault()}
        >
          <label htmlFor="finding-note">Transition note</label>
          <input
            id="finding-note"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Why this transition?"
          />
          <div className="finding-editor__actions">
            {actions.length === 0 && <span>No transitions available</span>}
            {actions.map((action) => (
              <button
                type="button"
                key={action}
                data-action={action}
                disabled={busy}
                onClick={(event) =>
                  void runTransition(
                    action,
                    event as unknown as FormEvent<HTMLFormElement>,
                  )
                }
              >
                {action}
              </button>
            ))}
          </div>
        </form>
      </div>

      <div
        className="finding-editor__section"
        data-section="cvss"
        hidden={section !== "cvss"}
      >
        <CvssCalculator
          vector={vector}
          preview={preview}
          onPreview={onPreview}
          onChange={(next) => {
            setVector(next);
            void onVectorChange(next).catch((cause: unknown) => {
              setError(
                cause instanceof Error
                  ? cause.message
                  : "Could not update vector",
              );
            });
          }}
          disabled={busy}
        />
      </div>

      <div
        className="finding-editor__section"
        data-section="remediation"
        hidden={section !== "remediation"}
      >
        <RemediationChecklist detail={detail} {...remediation} />
      </div>

      <div
        className="finding-editor__section"
        data-section="retest"
        hidden={section !== "retest"}
      >
        <RetestPanel detail={detail} {...retest} />
      </div>

      <div
        className="finding-editor__section"
        data-section="duplicates"
        hidden={section !== "duplicates"}
      >
        <DuplicateSuggestions
          detail={detail}
          onMark={onMarkDuplicate}
          onRefresh={onRefreshDuplicates}
          busy={busy}
        />
      </div>

      {error && (
        <p className="finding-editor__error" role="alert">
          {error}
        </p>
      )}
      <p className="finding-editor__hint">
        Alt+←/→ switches sections · Ctrl+S saves · Ctrl+Enter confirms a draft
      </p>
    </div>
  );
}
