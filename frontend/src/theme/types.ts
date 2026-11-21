export type ThemeMode = "light" | "dark" | "system";
export type ThemeName = "slate" | "aurora" | "ember" | "contrast";

export interface ThemeColors {
  accent: string;
  accentHover: string;
  surfaceBase: string;
  surfaceRaised: string;
  surfaceOverlay: string;
  textPrimary: string;
  textSecondary: string;
  border: string;
  success: string;
  warning: string;
  danger: string;
}

export interface ThemeDefinition {
  name: ThemeName;
  label: string;
  mode: "light" | "dark";
  colors: ThemeColors;
}

export interface ThemeState {
  mode: ThemeMode;
  theme: ThemeName;
  resolvedMode: "light" | "dark";
}
