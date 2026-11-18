import { V2Client } from "../../lib/apiClient";
import { A11Y_ROUTES } from "./config";
import type {
  A11yDashboard,
  A11yHealth,
  AriaReportPayload,
  AuditReportPayload,
  CatalogPayload,
  ContrastReportPayload,
  CssPayload,
  FocusReportPayload,
  PreferenceRecordPayload,
  RtlPayload,
  ShortcutReportPayload,
  ThemeDefinitionPayload,
  ThemeDetailPayload,
  ThemeOption,
} from "./types";

export interface A11yTransport {
  call<T>(
    route: string,
    body?: Record<string, unknown>,
    options?: { idempotencyKey?: string },
  ): Promise<T>;
}

export interface A11yClientOptions {
  client?: A11yTransport;
}

export interface A11yListResult {
  locales: Array<Record<string, unknown>>;
  themes: ThemeOption[];
  tokens: string[];
}

export interface A11yRolesResult {
  roles: string[];
  categories: Record<string, string[]>;
  count: number;
}

export interface A11yCoverageResult {
  locales: Record<string, Record<string, unknown>>;
  total_keys: number;
}

export class A11yClient {
  private readonly transport: A11yTransport;

  constructor(options: A11yClientOptions = {}) {
    this.transport = options.client ?? new V2Client();
  }

  health(): Promise<A11yHealth> {
    return this.transport.call(A11Y_ROUTES.health);
  }

  audit(
    nodes: readonly Record<string, unknown>[],
    options: Record<string, unknown> = {},
  ): Promise<AuditReportPayload> {
    return this.transport.call(A11Y_ROUTES.audit, {
      nodes: [...nodes],
      ...options,
    });
  }

  contrast(payload: Record<string, unknown>): Promise<ContrastReportPayload> {
    return this.transport.call(A11Y_ROUTES.contrast, payload);
  }

  contrastCheck(
    foreground: string,
    background: string,
    level = "AA",
  ): Promise<Record<string, unknown>> {
    return this.transport.call(A11Y_ROUTES.contrastCheck, {
      foreground,
      background,
      level,
    });
  }

  focus(
    nodes: readonly Record<string, unknown>[],
    options: Record<string, unknown> = {},
  ): Promise<FocusReportPayload> {
    return this.transport.call(A11Y_ROUTES.focus, {
      nodes: [...nodes],
      ...options,
    });
  }

  aria(
    nodes: readonly Record<string, unknown>[],
    strict = false,
  ): Promise<AriaReportPayload> {
    return this.transport.call(A11Y_ROUTES.aria, { nodes: [...nodes], strict });
  }

  ariaAttribute(
    attribute: string,
    value: string,
    role?: string,
  ): Promise<{
    attribute: string;
    value: string;
    issues: string[];
    valid: boolean;
  }> {
    return this.transport.call(A11Y_ROUTES.ariaAttribute, {
      attribute,
      value,
      ...(role ? { role } : {}),
    });
  }

  roles(): Promise<A11yRolesResult> {
    return this.transport.call(A11Y_ROUTES.roles);
  }

  shortcuts(
    overrides: Record<string, string | readonly string[]> = {},
    suggestFor?: string,
    scope?: string,
  ): Promise<ShortcutReportPayload> {
    return this.transport.call(A11Y_ROUTES.shortcuts, {
      overrides,
      ...(suggestFor ? { suggest_for: suggestFor } : {}),
      ...(scope ? { scope } : {}),
    });
  }

  shortcutFormat(
    binding: string | readonly string[],
    platform = "desktop",
  ): Promise<{
    binding: string;
    keys: string[];
    label: string;
    platform: string;
  }> {
    return this.transport.call(A11Y_ROUTES.shortcutFormat, {
      binding,
      platform,
    });
  }

  locales(acceptLanguage?: string): Promise<Array<Record<string, unknown>>> {
    return this.transport.call(A11Y_ROUTES.locales, {
      ...(acceptLanguage ? { accept_language: acceptLanguage } : {}),
    });
  }

  localeDetail(locale: string): Promise<Record<string, unknown>> {
    return this.transport.call(A11Y_ROUTES.localeDetail, { locale });
  }

  catalog(
    locale: string,
    prefixes: readonly string[] = [],
  ): Promise<CatalogPayload> {
    return this.transport.call(A11Y_ROUTES.catalog, {
      locale,
      prefixes: [...prefixes],
    });
  }

  translate(
    locale: string,
    key: string,
    params: Record<string, string | number> = {},
  ): Promise<{ locale: string; key: string; value: string }> {
    return this.transport.call(A11Y_ROUTES.translate, { locale, key, params });
  }

  coverage(): Promise<A11yCoverageResult> {
    return this.transport.call(A11Y_ROUTES.coverage);
  }

  format(
    payload: Record<string, unknown>,
  ): Promise<{ kind: string; value: string }> {
    return this.transport.call(A11Y_ROUTES.format, payload);
  }

  rtl(payload: Record<string, unknown>): Promise<RtlPayload> {
    return this.transport.call(A11Y_ROUTES.rtl, payload);
  }

  themes(): Promise<A11yListResult> {
    return this.transport.call(A11Y_ROUTES.themes);
  }

  themeDetail(theme: string): Promise<ThemeDetailPayload> {
    return this.transport.call(A11Y_ROUTES.themeDetail, { theme });
  }

  themeCreate(
    payload: Omit<ThemeDefinitionPayload, "name"> & { name: string },
  ): Promise<ThemeDefinitionPayload> {
    return this.transport.call(A11Y_ROUTES.themeCreate, { ...payload });
  }

  themeCss(theme: string, selector = ":root"): Promise<CssPayload> {
    return this.transport.call(A11Y_ROUTES.themeCss, { theme, selector });
  }

  themeCompare(
    first: string,
    second: string,
  ): Promise<Record<string, unknown>> {
    return this.transport.call(A11Y_ROUTES.themeCompare, { first, second });
  }

  themeContrast(
    payload: Record<string, unknown>,
  ): Promise<ContrastReportPayload> {
    return this.transport.call(A11Y_ROUTES.themeContrast, payload);
  }

  themeFixes(
    theme: string,
  ): Promise<{ theme: string; fixes: string[]; issues: string[] }> {
    return this.transport.call(A11Y_ROUTES.themeFixes, { theme });
  }

  preferences(profile = "default"): Promise<PreferenceRecordPayload> {
    return this.transport.call(A11Y_ROUTES.preferences, { profile });
  }

  preferencesDefaults(): Promise<Record<string, unknown>> {
    return this.transport.call(A11Y_ROUTES.preferencesDefaults);
  }

  preferencesSchema(): Promise<Record<string, unknown>> {
    return this.transport.call(A11Y_ROUTES.preferencesSchema);
  }

  preferencesValidate(
    preferences: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    return this.transport.call(A11Y_ROUTES.preferencesValidate, {
      preferences,
    });
  }

  preferencesUpdate(
    patch: Record<string, unknown>,
    profile = "default",
    idempotencyKey?: string,
  ): Promise<PreferenceRecordPayload> {
    return this.transport.call(
      A11Y_ROUTES.preferencesUpdate,
      { patch, profile },
      {
        ...(idempotencyKey ? { idempotencyKey } : {}),
      },
    );
  }

  preferencesReplace(
    preferences: Record<string, unknown>,
    profile = "default",
  ): Promise<PreferenceRecordPayload> {
    return this.transport.call(A11Y_ROUTES.preferencesReplace, {
      preferences,
      profile,
    });
  }

  preferencesReset(profile = "default"): Promise<PreferenceRecordPayload> {
    return this.transport.call(A11Y_ROUTES.preferencesReset, { profile });
  }

  preferencesExport(profile = "default"): Promise<Record<string, unknown>> {
    return this.transport.call(A11Y_ROUTES.preferencesExport, { profile });
  }

  preferencesImport(
    payload: Record<string, unknown>,
    profile = "default",
  ): Promise<PreferenceRecordPayload> {
    return this.transport.call(A11Y_ROUTES.preferencesImport, {
      payload,
      profile,
    });
  }

  dashboard(payload: Record<string, unknown> = {}): Promise<A11yDashboard> {
    return this.transport.call(A11Y_ROUTES.dashboard, payload);
  }
}
