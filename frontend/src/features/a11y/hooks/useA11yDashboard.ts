import { useCallback, useEffect } from "react";
import type { A11yClient } from "../client";
import { directionOfLocale } from "../pure";
import { useA11yStore } from "../store";
import type { LocaleOption } from "../types";

function asLocaleOption(value: Record<string, unknown>): LocaleOption {
  const locale = String(value.value ?? value.locale ?? "en");
  return {
    value: locale,
    label: String(value.label ?? locale),
    native: String(value.native ?? value.name ?? value.label ?? locale),
    direction: directionOfLocale(locale),
  };
}

export function useA11yDashboard(client: A11yClient, enabled = false) {
  const setLocales = useA11yStore((state) => state.setLocales);
  const setThemes = useA11yStore((state) => state.setThemes);
  const setShortcuts = useA11yStore((state) => state.setShortcuts);
  const setContrast = useA11yStore((state) => state.setContrast);
  const setAudit = useA11yStore((state) => state.setAudit);
  const setPreferences = useA11yStore((state) => state.setPreferences);
  const setLoading = useA11yStore((state) => state.setLoading);
  const setError = useA11yStore((state) => state.setError);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [themes, locales, shortcuts, contrast, audit, record] =
        await Promise.all([
          client.themes(),
          client.locales(),
          client.shortcuts(),
          client.contrast({ pairs: [] }),
          client.audit([]),
          client.preferences(),
        ]);
      setThemes(themes.themes ?? []);
      setLocales(locales.map(asLocaleOption));
      setShortcuts(shortcuts.shortcuts ?? []);
      setContrast(contrast);
      setAudit(audit);
      setPreferences(record.preferences);
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Unable to load accessibility data",
      );
    } finally {
      setLoading(false);
    }
  }, [
    client,
    setAudit,
    setContrast,
    setError,
    setLoading,
    setLocales,
    setPreferences,
    setShortcuts,
    setThemes,
  ]);

  useEffect(() => {
    if (enabled) void load();
  }, [enabled, load]);

  return { load };
}
