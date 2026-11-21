import type { ThemeColors, ThemeDefinition } from "./types";

const VARIABLES: Record<keyof ThemeColors, string> = {
  accent: "--accent",
  accentHover: "--accent-hover",
  surfaceBase: "--surface-base",
  surfaceRaised: "--surface-raised",
  surfaceOverlay: "--surface-overlay",
  textPrimary: "--text-primary",
  textSecondary: "--text-secondary",
  border: "--border",
  success: "--success",
  warning: "--warning",
  danger: "--danger",
};

export function applyTheme(
  definition: ThemeDefinition,
  target: HTMLElement = document.documentElement,
): void {
  const entries = Object.entries(VARIABLES) as [keyof ThemeColors, string][];
  for (const [key, cssVariable] of entries) {
    target.style.setProperty(cssVariable, definition.colors[key]);
  }
  target.dataset.theme = definition.name;
  target.dataset.mode = definition.mode;
  document.documentElement.style.colorScheme = definition.mode;
}
