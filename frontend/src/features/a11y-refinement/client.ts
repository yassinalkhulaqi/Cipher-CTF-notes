/** Typed V3 client wrapper for the a11y refinement namespace. */

import { V3Client, type V3ClientOptions } from "../../v3/apiClient";
import type {
  A11yDashboardView,
  AuditRunView,
  AuditSummaryView,
  ContrastReportView,
  FormatResultView,
  KeyboardMapView,
  LayoutManifestView,
  PreferenceRecordView,
  RuleInfo,
  SurfaceView,
  SyncReportView,
  ThemeContrastView,
} from "./types";

export interface A11yRefinementClientOptions extends V3ClientOptions {
  client?: V3Client;
}

export class A11yRefinementClient {
  private readonly client: V3Client;

  constructor(options: A11yRefinementClientOptions = {}) {
    this.client = options.client ?? new V3Client(options);
  }

  private call<T>(
    action: string,
    body: Record<string, unknown> = {},
  ): Promise<T> {
    return this.client.data<T>("a11y", action, body);
  }

  health(): Promise<{
    namespace: string;
    surfaces: number;
    wcag22_rules: number;
  }> {
    return this.call("health");
  }

  rules(level = "AAA"): Promise<{ rules: RuleInfo[]; level: string }> {
    return this.call("rules", { level });
  }

  surfaces(): Promise<{ surfaces: SurfaceView[]; names: string[] }> {
    return this.call("surfaces");
  }

  audit(surface: string, level = "AA"): Promise<AuditRunView> {
    return this.call("audit", { surface, level });
  }

  auditAll(level = "AA"): Promise<AuditSummaryView & { runs: AuditRunView[] }> {
    return this.call("audit_all", { level });
  }

  contrast(payload: Record<string, unknown>): Promise<ContrastReportView> {
    return this.call("contrast", payload);
  }

  themeContrast(): Promise<ThemeContrastView> {
    return this.call("theme_contrast");
  }

  format(
    locale: string,
    kind: string,
    value: unknown,
  ): Promise<FormatResultView> {
    return this.call("format", { locale, kind, value });
  }

  locales(
    acceptLanguage = "",
  ): Promise<{ locales: unknown[]; matched: string }> {
    return this.call("locales", { accept_language: acceptLanguage });
  }

  layout(locale: string): Promise<LayoutManifestView> {
    return this.call("rtl_manifest", { locale });
  }

  keyboard(locale = "en", platform = "desktop"): Promise<KeyboardMapView> {
    return this.call("keyboard", { locale, platform });
  }

  preferences(
    profile = "default",
  ): Promise<{ record: PreferenceRecordView; appearance: unknown }> {
    return this.call("preferences", { profile });
  }

  sync(
    payload: Record<string, unknown>,
    strategy = "merge",
  ): Promise<SyncReportView> {
    return this.call("preferences_sync", { ...payload, strategy });
  }

  motion(mode: string): Promise<{ mode: string; content_hidden: boolean }> {
    return this.call("motion", { mode });
  }

  dashboard(locale = "en"): Promise<A11yDashboardView> {
    return this.call("dashboard", { locale });
  }
}
