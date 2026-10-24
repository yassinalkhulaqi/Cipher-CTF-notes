import { BookOpen, Moon, Settings, Sparkles, Sun } from "lucide-react";
import { VIEW_MODES } from "../../lib/constants";
import type { ViewMode } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

export function SettingsModal() {
  const theme = useAppStore((state) => state.theme);
  const fontSize = useAppStore((state) => state.fontSize);
  const viewMode = useAppStore((state) => state.viewMode);
  const syncScroll = useAppStore((state) => state.syncScroll);
  const boot = useAppStore((state) => state.boot);
  const setTheme = useAppStore((state) => state.setTheme);
  const setFontSize = useAppStore((state) => state.setFontSize);
  const setViewMode = useAppStore((state) => state.setViewMode);
  const setSyncScroll = useAppStore((state) => state.setSyncScroll);
  const loadDemo = useAppStore((state) => state.loadDemo);

  const openModal = useUiStore((state) => state.openModal);
  const askConfirm = useUiStore((state) => state.askConfirm);
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);

  const demo = () => {
    askConfirm({
      title: "Load demo vault",
      message:
        "This adds a small set of sample CTF notes to the current vault. Existing notes are left untouched.",
      confirmLabel: "Load demo",
      danger: false,
      action: async () => {
        try {
          await loadDemo();
          closeModal();
          toast("Demo vault loaded", "success");
        } catch (error) {
          toast(
            error instanceof Error
              ? error.message
              : "Could not load the demo vault",
            "error",
          );
        }
      },
    });
  };

  return (
    <Modal
      title="Settings"
      subtitle="Appearance, editor, and vault"
      icon={<Settings />}
      className="settings-modal"
      footer={
        <>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => openModal("help")}
          >
            <BookOpen /> Keyboard shortcuts
          </button>
          <span className="grow" />
          <button type="button" className="btn primary" onClick={closeModal}>
            Done
          </button>
        </>
      }
      label="Settings"
    >
      <div className="settings-stack">
        <section className="settings-section">
          <div className="settings-head">
            <h3>Appearance</h3>
            <p>Choose how the Aurora interface looks.</p>
          </div>
          <div className="theme-picker">
            <button
              type="button"
              className={`theme-card ${theme === "dark" ? "selected" : ""}`}
              onClick={() => setTheme("dark")}
            >
              <Moon />
              <span>Graphite</span>
              <small>Dark</small>
            </button>
            <button
              type="button"
              className={`theme-card light ${theme === "light" ? "selected" : ""}`}
              onClick={() => setTheme("light")}
            >
              <Sun />
              <span>Paper</span>
              <small>Light</small>
            </button>
          </div>
        </section>

        <section className="settings-section">
          <div className="settings-head">
            <h3>Editor</h3>
            <p>Typography and the default workspace layout.</p>
          </div>
          <div className="settings-row">
            <label htmlFor="settings-font">Editor font size</label>
            <div className="range-row">
              <input
                id="settings-font"
                type="range"
                min={13}
                max={20}
                step={1}
                value={fontSize}
                onChange={(event) => setFontSize(Number(event.target.value))}
              />
              <span className="range-value">{fontSize}px</span>
            </div>
          </div>
          <div className="settings-row">
            <span>Default view</span>
            <div className="segmented">
              {VIEW_MODES.map((mode) => (
                <button
                  key={mode.value}
                  type="button"
                  className={viewMode === mode.value ? "selected" : ""}
                  onClick={() => setViewMode(mode.value as ViewMode)}
                >
                  {mode.label}
                </button>
              ))}
            </div>
          </div>
          <label className="check">
            <input
              type="checkbox"
              checked={syncScroll}
              onChange={(event) => setSyncScroll(event.target.checked)}
            />
            Sync editor and preview scrolling
          </label>
        </section>

        <section className="settings-section">
          <div className="settings-head">
            <h3>Vault</h3>
            <p>The local folder that stores your notes and the SQLite index.</p>
          </div>
          <div className="vault-path">{boot?.vault_path ?? "Loading…"}</div>
          <div className="settings-actions">
            <button type="button" className="btn ghost sm" onClick={demo}>
              <Sparkles /> Load demo vault
            </button>
            <button
              type="button"
              className="btn ghost sm"
              onClick={() => openModal("trash")}
            >
              Open trash
            </button>
          </div>
        </section>
      </div>
    </Modal>
  );
}
