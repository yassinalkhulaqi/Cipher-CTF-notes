import { create } from "zustand";
import { A11Y_STORAGE_KEY, DEFAULT_A11Y_PREFERENCES } from "./config";
import {
  clampFontScale,
  createAnnouncement,
  mergePreferences,
  normalizeLocaleTag,
  normalizeThemeName,
  parseBinding,
  trimAnnouncements,
} from "./pure";
import type {
  A11yDirection,
  A11yPreferences,
  Announcement,
  AuditReportPayload,
  ContrastReportPayload,
  LocaleOption,
  Politeness,
  ShortcutBinding,
  ThemeOption,
} from "./types";

function sanitizePreferences(
  value: Partial<A11yPreferences> | null,
): A11yPreferences {
  if (!value) return { ...DEFAULT_A11Y_PREFERENCES, shortcuts: {} };
  const shortcuts: Record<string, string[]> = {};
  if (value.shortcuts && typeof value.shortcuts === "object") {
    for (const [action, keys] of Object.entries(value.shortcuts)) {
      if (Array.isArray(keys))
        shortcuts[action] = parseBinding(keys.map(String));
    }
  }
  const direction: A11yDirection =
    value.direction === "ltr" ||
    value.direction === "rtl" ||
    value.direction === "auto"
      ? value.direction
      : DEFAULT_A11Y_PREFERENCES.direction;
  return {
    locale: normalizeLocaleTag(value.locale ?? DEFAULT_A11Y_PREFERENCES.locale),
    theme: normalizeThemeName(value.theme ?? DEFAULT_A11Y_PREFERENCES.theme),
    direction,
    font_scale: clampFontScale(
      typeof value.font_scale === "number"
        ? value.font_scale
        : DEFAULT_A11Y_PREFERENCES.font_scale,
    ),
    reduce_motion: value.reduce_motion === true,
    high_contrast: value.high_contrast === true,
    screen_reader_hints:
      value.screen_reader_hints === undefined
        ? true
        : value.screen_reader_hints === true,
    focus_ring_boost: value.focus_ring_boost === true,
    shortcuts,
    updated_at:
      typeof value.updated_at === "string"
        ? value.updated_at
        : DEFAULT_A11Y_PREFERENCES.updated_at,
    revision:
      typeof value.revision === "number" && Number.isFinite(value.revision)
        ? value.revision
        : 0,
  };
}

function readStoredPreferences(): A11yPreferences {
  if (typeof window === "undefined" || !window.localStorage) {
    return sanitizePreferences(null);
  }
  try {
    const raw = window.localStorage.getItem(A11Y_STORAGE_KEY);
    if (!raw) return sanitizePreferences(null);
    const parsed = JSON.parse(raw) as Partial<A11yPreferences>;
    return sanitizePreferences(parsed);
  } catch {
    return sanitizePreferences(null);
  }
}

function persistPreferences(preferences: A11yPreferences): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(A11Y_STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    return;
  }
}

export interface A11yState {
  preferences: A11yPreferences;
  panelOpen: boolean;
  locales: LocaleOption[];
  themes: ThemeOption[];
  contrast: ContrastReportPayload | null;
  audit: AuditReportPayload | null;
  shortcuts: ShortcutBinding[];
  announcements: Announcement[];
  loading: boolean;
  error: string | null;
  setPanelOpen: (open: boolean) => void;
  togglePanel: () => void;
  setPreferences: (preferences: A11yPreferences) => void;
  updatePreferences: (patch: Partial<A11yPreferences>) => void;
  resetPreferences: () => void;
  setLocales: (locales: LocaleOption[]) => void;
  setThemes: (themes: ThemeOption[]) => void;
  setContrast: (report: ContrastReportPayload | null) => void;
  setAudit: (report: AuditReportPayload | null) => void;
  setShortcuts: (shortcuts: ShortcutBinding[]) => void;
  announce: (message: string, politeness?: Politeness) => void;
  dismissAnnouncement: (id: string) => void;
  clearAnnouncements: () => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useA11yStore = create<A11yState>((set, get) => ({
  preferences: readStoredPreferences(),
  panelOpen: false,
  locales: [],
  themes: [],
  contrast: null,
  audit: null,
  shortcuts: [],
  announcements: [],
  loading: false,
  error: null,

  setPanelOpen: (open) => set({ panelOpen: open }),
  togglePanel: () => set((state) => ({ panelOpen: !state.panelOpen })),
  setPreferences: (preferences) => {
    const next = sanitizePreferences(preferences);
    persistPreferences(next);
    set({ preferences: next });
  },
  updatePreferences: (patch) => {
    const next = mergePreferences(get().preferences, patch);
    persistPreferences(next);
    set({ preferences: next });
    get().announce("Accessibility preferences updated");
  },
  resetPreferences: () => {
    const next: A11yPreferences = {
      ...DEFAULT_A11Y_PREFERENCES,
      shortcuts: {},
      updated_at: new Date().toISOString(),
      revision: get().preferences.revision + 1,
    };
    persistPreferences(next);
    set({ preferences: next });
    get().announce("Accessibility preferences reset");
  },
  setLocales: (locales) => set({ locales: [...locales] }),
  setThemes: (themes) => set({ themes: [...themes] }),
  setContrast: (report) => set({ contrast: report }),
  setAudit: (report) => set({ audit: report }),
  setShortcuts: (shortcuts) => set({ shortcuts: [...shortcuts] }),
  announce: (message, politeness = "polite") =>
    set((state) => ({
      announcements: trimAnnouncements([
        ...state.announcements,
        createAnnouncement(message, politeness),
      ]),
    })),
  dismissAnnouncement: (id) =>
    set((state) => ({
      announcements: state.announcements.filter((item) => item.id !== id),
    })),
  clearAnnouncements: () => set({ announcements: [] }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));
