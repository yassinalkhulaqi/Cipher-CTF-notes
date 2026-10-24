import { Flag } from "lucide-react";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";
import { copyText, plural, wordCount } from "../lib/utils";

const SAVE_LABEL: Record<string, string> = {
  idle: "Ready",
  dirty: "Unsaved changes",
  saving: "Saving…",
  saved: "Saved",
  error: "Save failed",
};

export function StatusBar() {
  const note = useAppStore((state) => state.note);
  const draft = useAppStore((state) => state.draft);
  const saveState = useAppStore((state) => state.saveState);
  const toast = useUiStore((state) => state.toast);

  const words = wordCount(draft);
  const characters = draft.length;

  return (
    <footer className="statusbar">
      <span className={`save-dot ${saveState}`} />
      <span>{SAVE_LABEL[saveState] ?? "Ready"}</span>
      <span className="sep">·</span>
      <span>{plural(words, "word")}</span>
      <span className="sep">·</span>
      <span>{plural(characters, "character")}</span>
      <span className="status-location">
        <span className="sep">·</span>
        {note ? note.path || "Vault root" : "Welcome"}
      </span>
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
          {note.flag}
        </button>
      ) : null}
    </footer>
  );
}
