import { Flag, ShieldCheck } from "lucide-react";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";
import { copyText, plural, wordCount } from "../lib/utils";

const SAVE_LABEL: Record<string, string> = {
  idle: "Ready",
  dirty: "Unsaved changes",
  saving: "Saving…",
  saved: "All changes saved",
  error: "Save failed",
};

export function StatusBar() {
  const boot = useAppStore((state) => state.boot);
  const note = useAppStore((state) => state.note);
  const draft = useAppStore((state) => state.draft);
  const saveState = useAppStore((state) => state.saveState);
  const saveNow = useAppStore((state) => state.saveNow);
  const cursorLine = useUiStore((state) => state.cursorLine);
  const cursorColumn = useUiStore((state) => state.cursorColumn);
  const toast = useUiStore((state) => state.toast);

  const words = wordCount(draft);
  const characters = draft.length;

  return (
    <footer className="statusbar">
      <span className={`save-dot ${saveState}`} />
      <span>{SAVE_LABEL[saveState] ?? "Ready"}</span>
      {saveState === "error" ? (
        <button
          type="button"
          className="status-retry"
          onClick={() => {
            void saveNow().then(
              () => toast("Note saved", "success"),
              () => toast("Save failed again", "error"),
            );
          }}
        >
          Retry
        </button>
      ) : null}
      {note ? (
        <span className="status-note-stats">
          <span className="sep">·</span>
          <span>{plural(words, "word")}</span>
          <span className="sep status-hide-xs">·</span>
          <span className="status-hide-xs">
            {plural(characters, "character")}
          </span>
          <span className="sep">·</span>
          <span title="Cursor position">
            Ln {cursorLine}, Col {cursorColumn}
          </span>
          <span className="sep status-hide-xs">·</span>
          <span className="status-location status-hide-xs">
            {note.path || "Vault root"}
          </span>
        </span>
      ) : (
        <>
          <span className="sep">·</span>
          <span>
            {boot
              ? `${plural(boot.stats.notes, "note")} · ${plural(boot.stats.folders, "folder")}`
              : "Local vault"}
          </span>
        </>
      )}
      <span className="grow" />
      {note?.flag ? (
        <button
          type="button"
          className="status-flag"
          onClick={() => {
            void copyText(note.flag).then(
              () => toast("Flag copied", "success"),
              () => toast("Could not copy the flag", "error"),
            );
          }}
          title="Copy flag"
        >
          <Flag />
          <span className="status-flag-text">{note.flag}</span>
        </button>
      ) : null}
      <span className="status-local" title="No network services are used">
        <ShieldCheck />
        <span className="status-local-label">Local only</span>
      </span>
    </footer>
  );
}
