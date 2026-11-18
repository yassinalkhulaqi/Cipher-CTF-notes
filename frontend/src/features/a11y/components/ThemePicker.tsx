import { MODE_LABEL, WCAG_LEVELS } from "../config";
import { sortThemes } from "../pure";
import type { ThemeOption } from "../types";

export interface ThemePickerProps {
  themes: readonly ThemeOption[];
  value: string;
  onChange: (theme: string) => void;
  level?: string;
  onLevelChange?: (level: string) => void;
}

export function ThemePicker({
  themes,
  value,
  onChange,
  level = "AA",
  onLevelChange,
}: ThemePickerProps) {
  const options = sortThemes(themes);
  return (
    <section className="a11y-section" aria-labelledby="a11y-theme-title">
      <h3 id="a11y-theme-title">Theme</h3>
      {options.length === 0 ? (
        <p className="a11y-empty">No themes are available.</p>
      ) : (
        <div className="a11y-theme-grid">
          {options.map((theme) => (
            <button
              type="button"
              key={theme.value}
              className="a11y-theme-card"
              data-selected={theme.value === value}
              aria-pressed={theme.value === value}
              onClick={() => onChange(theme.value)}
            >
              <span
                className="a11y-swatch"
                style={{ background: theme.accent }}
              />
              <strong>{theme.label}</strong>
              <span className="a11y-muted">
                {MODE_LABEL[theme.mode] ?? theme.mode}
              </span>
              <span className="a11y-muted">{theme.description}</span>
            </button>
          ))}
        </div>
      )}
      <label className="a11y-field">
        <span>Contrast target</span>
        <select
          value={level}
          onChange={(event) => onLevelChange?.(event.target.value)}
          disabled={!onLevelChange}
        >
          {WCAG_LEVELS.map((option) => (
            <option key={option} value={option}>
              WCAG {option}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
