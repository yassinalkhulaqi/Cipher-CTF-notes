import { useEffect } from "react";
import { formatFontScale, resolveDirection } from "../pure";
import { useA11yStore } from "../store";

export function useA11yPreferences() {
  const preferences = useA11yStore((state) => state.preferences);
  const updatePreferences = useA11yStore((state) => state.updatePreferences);
  const direction = resolveDirection(preferences.direction, preferences.locale);
  const fontScaleLabel = formatFontScale(preferences.font_scale);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.a11yTheme = preferences.theme;
    root.dataset.a11yDirection = direction;
    root.dir = direction;
    root.style.setProperty("--a11y-font-scale", String(preferences.font_scale));
    root.classList.toggle("a11y-reduce-motion", preferences.reduce_motion);
    root.classList.toggle("a11y-high-contrast", preferences.high_contrast);
    root.classList.toggle("a11y-focus-boost", preferences.focus_ring_boost);
    root.classList.toggle("a11y-reader-hints", preferences.screen_reader_hints);
  }, [
    preferences.theme,
    preferences.reduce_motion,
    preferences.high_contrast,
    preferences.focus_ring_boost,
    preferences.screen_reader_hints,
    preferences.font_scale,
    direction,
  ]);

  return { preferences, direction, fontScaleLabel, updatePreferences };
}
