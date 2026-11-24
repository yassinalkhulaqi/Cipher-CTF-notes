import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { applyTheme } from "./applyTheme";
import { getTheme } from "./presets";
import type { ThemeMode, ThemeName } from "./types";

export interface ThemeContextValue {
  mode: ThemeMode;
  theme: ThemeName;
  resolvedMode: "light" | "dark";
  setMode: (mode: ThemeMode) => void;
  setTheme: (theme: ThemeName) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

const MODE_KEY = "redscribe.theme.mode";
const THEME_KEY = "redscribe.theme.name";

function systemMode(): "light" | "dark" {
  if (typeof window === "undefined" || !window.matchMedia) return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function readStored<T extends string>(key: string, fallback: T): T {
  try {
    const value = window.localStorage.getItem(key);
    return value ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

function persist(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    return;
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() =>
    readStored(MODE_KEY, "system"),
  );
  const [theme, setThemeState] = useState<ThemeName>(() =>
    readStored(THEME_KEY, "slate"),
  );
  const [system, setSystem] = useState<"light" | "dark">(systemMode);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const list = window.matchMedia("(prefers-color-scheme: light)");
    const update = (event: MediaQueryListEvent): void =>
      setSystem(event.matches ? "light" : "dark");
    if (typeof list.addEventListener === "function") {
      list.addEventListener("change", update);
      return () => list.removeEventListener("change", update);
    }
    list.addListener(update);
    return () => list.removeListener(update);
  }, []);

  const resolvedMode = mode === "system" ? system : mode;

  useEffect(() => {
    applyTheme({ ...getTheme(theme), mode: resolvedMode });
  }, [theme, resolvedMode]);

  const setMode = useCallback((next: ThemeMode): void => {
    setModeState(next);
    persist(MODE_KEY, next);
  }, []);

  const setTheme = useCallback((next: ThemeName): void => {
    setThemeState(next);
    persist(THEME_KEY, next);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, theme, resolvedMode, setMode, setTheme }),
    [mode, theme, resolvedMode, setMode, setTheme],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}
