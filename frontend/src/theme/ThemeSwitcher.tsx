import { getTheme, themeNames } from "./presets";
import type { ThemeMode } from "./types";
import { useTheme } from "./useTheme";

const MODES: ThemeMode[] = ["light", "dark", "system"];

export function ThemeSwitcher() {
  const { mode, theme, setMode, setTheme } = useTheme();

  return (
    <div className="theme-switcher" role="group" aria-label="Theme settings">
      <div className="theme-switcher__group">
        <span className="theme-switcher__label" id="theme-mode-label">
          Mode
        </span>
        <div className="theme-switcher__segment" aria-labelledby="theme-mode-label">
          {MODES.map((option) => (
            <button
              key={option}
              type="button"
              className="theme-switcher__option"
              aria-pressed={mode === option}
              onClick={() => setMode(option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      <div className="theme-switcher__group">
        <span className="theme-switcher__label" id="theme-name-label">
          Palette
        </span>
        <div className="theme-switcher__palette" aria-labelledby="theme-name-label">
          {themeNames.map((name) => (
            <button
              key={name}
              type="button"
              className="theme-switcher__swatch"
              aria-pressed={theme === name}
              aria-label={getTheme(name).label}
              title={getTheme(name).label}
              onClick={() => setTheme(name)}
              style={{ backgroundColor: getTheme(name).colors.accent }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
