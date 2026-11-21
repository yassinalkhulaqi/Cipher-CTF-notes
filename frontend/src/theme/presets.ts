import { lighten } from "./colorUtils";
import type { ThemeColors, ThemeDefinition, ThemeName } from "./types";

const darkColors: ThemeColors = {
  accent: "#8b7cf6",
  accentHover: "#9d8ffa",
  surfaceBase: "#0d0d10",
  surfaceRaised: "#16161a",
  surfaceOverlay: "#1d1d22",
  textPrimary: "#f5f5f6",
  textSecondary: "#a1a1aa",
  border: "#2a2a31",
  success: "#4ade80",
  warning: "#fbbf24",
  danger: "#f87171",
};

const lightColors: ThemeColors = {
  accent: "#5b47d6",
  accentHover: "#6d59e6",
  surfaceBase: "#f7f7f8",
  surfaceRaised: "#ffffff",
  surfaceOverlay: "#eeeeF1",
  textPrimary: "#1a1a1e",
  textSecondary: "#56565f",
  border: "#d7d7dd",
  success: "#15803d",
  warning: "#b45309",
  danger: "#b91c1c",
};

function create(
  name: ThemeName,
  label: string,
  mode: "light" | "dark",
  accent: string,
  overrides: Partial<ThemeColors> = {},
): ThemeDefinition {
  const base = mode === "dark" ? darkColors : lightColors;
  return {
    name,
    label,
    mode,
    colors: {
      ...base,
      accent,
      accentHover: lighten(accent, 0.12),
      ...overrides,
    },
  };
}

export const themes: Record<ThemeName, ThemeDefinition> = {
  slate: create("slate", "Slate & Signal", "dark", "#8b7cf6"),
  aurora: create("aurora", "Aurora", "dark", "#38bdf8", {
    surfaceBase: "#071014",
    surfaceRaised: "#0d1b22",
    border: "#1c3540",
  }),
  ember: create("ember", "Ember", "dark", "#fb7185", {
    surfaceBase: "#120b0d",
    surfaceRaised: "#1c1114",
    border: "#3a2026",
  }),
  contrast: create("contrast", "High Contrast", "dark", "#c4b5fd", {
    surfaceBase: "#050506",
    surfaceRaised: "#0d0d0f",
    surfaceOverlay: "#161619",
    textPrimary: "#ffffff",
    textSecondary: "#f0f0f2",
    border: "#ffffff",
  }),
};

export const themeNames = Object.keys(themes) as ThemeName[];

export function getTheme(name: ThemeName): ThemeDefinition {
  return themes[name];
}
