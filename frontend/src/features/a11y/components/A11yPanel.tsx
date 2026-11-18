import { useEffect, useMemo, useRef, useState } from "react";
import { A11yClient } from "../client";
import { useA11yAnnouncer } from "../hooks/useA11yAnnouncer";
import { useA11yDashboard } from "../hooks/useA11yDashboard";
import { useA11yPreferences } from "../hooks/useA11yPreferences";
import { useFocusOrder } from "../hooks/useFocusOrder";
import { formatFontScale } from "../pure";
import { useA11yStore } from "../store";
import { AuditSummary } from "./AuditSummary";
import { ContrastReportView } from "./ContrastReportView";
import { FocusOrderView } from "./FocusOrderView";
import { LocalePicker } from "./LocalePicker";
import { ScreenReaderHelper } from "./ScreenReaderHelper";
import { ShortcutEditor } from "./ShortcutEditor";
import { ThemePicker } from "./ThemePicker";
import "../../../styles/a11y.css";

export interface A11yPanelProps {
  client?: A11yClient;
  initialOpen?: boolean;
}

export function A11yPanel({ client, initialOpen = false }: A11yPanelProps) {
  const a11yClient = useMemo(() => client ?? new A11yClient(), [client]);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [level, setLevel] = useState("AA");
  const [foreground, setForeground] = useState("#111827");
  const [background, setBackground] = useState("#FFFFFF");

  const panelOpen = useA11yStore((state) => state.panelOpen);
  const togglePanel = useA11yStore((state) => state.togglePanel);
  const setPanelOpen = useA11yStore((state) => state.setPanelOpen);
  const locales = useA11yStore((state) => state.locales);
  const themes = useA11yStore((state) => state.themes);
  const shortcuts = useA11yStore((state) => state.shortcuts);
  const contrast = useA11yStore((state) => state.contrast);
  const audit = useA11yStore((state) => state.audit);
  const error = useA11yStore((state) => state.error);
  const loading = useA11yStore((state) => state.loading);
  const setContrast = useA11yStore((state) => state.setContrast);
  const setAudit = useA11yStore((state) => state.setAudit);
  const setShortcuts = useA11yStore((state) => state.setShortcuts);
  const setError = useA11yStore((state) => state.setError);

  const { preferences, direction, fontScaleLabel, updatePreferences } =
    useA11yPreferences();
  const { announce } = useA11yAnnouncer();
  const { load } = useA11yDashboard(a11yClient, panelOpen);
  const { steps } = useFocusOrder(panelRef, [panelOpen, shortcuts.length]);

  useEffect(() => {
    if (initialOpen) setPanelOpen(true);
  }, [initialOpen, setPanelOpen]);

  const savePreferences = async (): Promise<void> => {
    try {
      await a11yClient.preferencesUpdate(
        {
          locale: preferences.locale,
          theme: preferences.theme,
          direction: preferences.direction,
          font_scale: preferences.font_scale,
          reduce_motion: preferences.reduce_motion,
          high_contrast: preferences.high_contrast,
          screen_reader_hints: preferences.screen_reader_hints,
          focus_ring_boost: preferences.focus_ring_boost,
          shortcuts: preferences.shortcuts,
        },
        "default",
        `a11y-panel-${Date.now()}`,
      );
      setError(null);
      announce("Accessibility preferences saved");
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Unable to save accessibility preferences",
      );
    }
  };

  const runAudit = async (): Promise<void> => {
    try {
      const report = await a11yClient.audit(
        [
          {
            tag: "main",
            attrs: { id: "main", role: "main" },
            text: "",
            children: [
              {
                tag: "h1",
                attrs: {},
                text: "RedScribe",
                children: [],
                visible: true,
                path: "/0/0",
              },
              {
                tag: "button",
                attrs: { "aria-label": "Save note" },
                text: "",
                children: [],
                visible: true,
                path: "/0/1",
              },
            ],
            visible: true,
            path: "/0",
          },
        ],
        { level, locale: preferences.locale, theme: preferences.theme },
      );
      setAudit(report);
      setError(null);
      announce(`Audit complete with score ${report.score.toFixed(0)}`);
    } catch (auditError) {
      setError(
        auditError instanceof Error
          ? auditError.message
          : "Unable to run audit",
      );
    }
  };

  const runContrast = async (): Promise<void> => {
    try {
      await a11yClient.contrastCheck(foreground, background, level);
      const report = await a11yClient.contrast({
        pairs: [
          {
            name: "Custom pair",
            foreground,
            background,
            font_size: 16,
            bold: false,
          },
        ],
        level,
      });
      setContrast(report);
      setError(null);
      announce(`Contrast check complete with score ${report.score.toFixed(0)}`);
    } catch (contrastError) {
      setError(
        contrastError instanceof Error
          ? contrastError.message
          : "Unable to check contrast",
      );
    }
  };

  const overrideShortcut = async (
    action: string,
    keys: string[],
  ): Promise<void> => {
    try {
      const report = await a11yClient.shortcuts({ [action]: keys });
      setShortcuts(report.shortcuts);
      setError(null);
      announce(`${action} shortcut updated`);
    } catch (shortcutError) {
      setError(
        shortcutError instanceof Error
          ? shortcutError.message
          : "Unable to update shortcut",
      );
    }
  };

  return (
    <>
      <button
        type="button"
        className="a11y-toggle"
        aria-expanded={panelOpen}
        aria-controls="a11y-panel"
        onClick={togglePanel}
      >
        Accessibility
      </button>
      {panelOpen && (
        <div
          ref={panelRef}
          id="a11y-panel"
          className="a11y-panel"
          role="dialog"
          aria-label="Accessibility settings"
        >
          <header className="a11y-panel-header">
            <div>
              <h2>Accessibility and language</h2>
              <p className="a11y-muted">
                Theme, locale, contrast, focus order, and shortcut controls
              </p>
            </div>
            <div className="a11y-inline-controls">
              <button
                type="button"
                className="a11y-button"
                onClick={() => void load()}
              >
                Refresh
              </button>
              <button
                type="button"
                className="a11y-button"
                onClick={() => setPanelOpen(false)}
              >
                Close
              </button>
            </div>
          </header>
          {loading && (
            <p className="a11y-loading">Loading accessibility data…</p>
          )}
          {error && (
            <p className="a11y-error" role="alert">
              {error}
            </p>
          )}

          <ThemePicker
            themes={themes}
            value={preferences.theme}
            level={level}
            onLevelChange={setLevel}
            onChange={(theme) => updatePreferences({ theme })}
          />
          <LocalePicker
            locales={locales}
            value={preferences.locale}
            direction={preferences.direction}
            resolvedDirection={direction}
            onChange={(locale) => updatePreferences({ locale })}
            onDirectionChange={(value) =>
              updatePreferences({ direction: value })
            }
          />

          <section
            className="a11y-section"
            aria-labelledby="a11y-display-title"
          >
            <h3 id="a11y-display-title">Display</h3>
            <label className="a11y-field">
              <span>Text size</span>
              <input
                type="range"
                min={0.75}
                max={2}
                step={0.05}
                value={preferences.font_scale}
                onChange={(event) =>
                  updatePreferences({ font_scale: Number(event.target.value) })
                }
              />
              <output>{formatFontScale(preferences.font_scale)}</output>
            </label>
            <div className="a11y-check-grid">
              {(
                [
                  ["reduce_motion", "Reduce motion"],
                  ["high_contrast", "High contrast"],
                  ["focus_ring_boost", "Boost focus rings"],
                  ["screen_reader_hints", "Screen reader hints"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="a11y-check">
                  <input
                    type="checkbox"
                    checked={preferences[key]}
                    onChange={(event) =>
                      updatePreferences({ [key]: event.target.checked })
                    }
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
            <button
              type="button"
              className="a11y-button"
              onClick={() => void savePreferences()}
            >
              Save preferences
            </button>
            {fontScaleLabel !== "100%" && (
              <p className="a11y-muted">Current text size: {fontScaleLabel}</p>
            )}
          </section>

          <section className="a11y-section" aria-labelledby="a11y-checks-title">
            <h3 id="a11y-checks-title">Checks</h3>
            <div className="a11y-inline-controls">
              <button
                type="button"
                className="a11y-button"
                onClick={() => void runAudit()}
              >
                Run audit
              </button>
              <label className="a11y-field">
                <span>Foreground</span>
                <input
                  type="color"
                  value={foreground}
                  onChange={(event) => setForeground(event.target.value)}
                />
              </label>
              <label className="a11y-field">
                <span>Background</span>
                <input
                  type="color"
                  value={background}
                  onChange={(event) => setBackground(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="a11y-button"
                onClick={() => void runContrast()}
              >
                Check contrast
              </button>
            </div>
          </section>

          <AuditSummary report={audit} />
          <ContrastReportView report={contrast} />
          <ShortcutEditor shortcuts={shortcuts} onOverride={overrideShortcut} />
          <FocusOrderView steps={steps} />
          <ScreenReaderHelper audit={audit} contrast={contrast} />
        </div>
      )}
    </>
  );
}
