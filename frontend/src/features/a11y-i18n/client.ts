/** Typed API client for the v4 accessibility panel. */

import { V4Client } from "../v4-kernel/client";
import type { PageMetaV4 } from "../v4-kernel/types-v4";

export const ACCESSIBILITY_ROUTE = "/accessibility";

export interface PreferenceView {
  theme: "light" | "graphite" | "system";
  density: "compact" | "default" | "comfortable";
  motion: "full" | "subtle" | "off";
  locale: string;
  direction: "ltr" | "rtl";
  reduce_transparency: boolean;
  high_contrast: boolean;
  font_scale: number;
}

export interface RuleView {
  id: string;
  description: string;
  severity: "info" | "warning" | "error";
  enabled: boolean;
}

export interface MotionView {
  preference: "full" | "subtle" | "off";
  durations: Record<string, number>;
  reduce_transparency: boolean;
  animated: boolean;
}

export interface AuditIssueView {
  rule_id: string;
  target: string;
  detail: string;
  suggestion: string;
  severity: "info" | "warning" | "error";
  fingerprint: string;
}

export interface AuditReportView {
  issues: AuditIssueView[];
  rules_run: string[];
  descriptor_count: number;
  passed: boolean;
  severity_counts: Record<string, number>;
}

export interface TourStateView {
  index: number;
  status: "not_started" | "in_progress" | "completed" | "skipped";
  visited_ids: string[];
  completed_ids: string[];
  total: number;
  can_advance: boolean;
  can_go_back: boolean;
  progress: number;
}

export interface TourStepView {
  id: string;
  target: string;
  title: string;
  body: string;
}

export interface SnapshotIndexView {
  names: string[];
  locales: string[];
  total: number;
  latest_saved_at: string;
}

export interface EmptyStateView {
  title: string;
  body: string;
  action_label: string;
}

export interface CatalogRecordView {
  locale: string;
  language: string;
  direction: "ltr" | "rtl";
  message_count: number;
  checksum: string;
}

export interface CatalogIndexView {
  version: number;
  catalogs: CatalogRecordView[];
}

export interface TranslationView {
  text: string;
  message: string;
  locale: string;
  resolved_locale: string;
  fallback_used: boolean;
  missing_placeholders: string[];
}

export interface AccessibilityStatus {
  actions: string[];
  capabilities: string[];
  catalogs: CatalogIndexView;
  directions: Record<string, string>;
  empty_states: Record<string, EmptyStateView>;
  event_count: number;
  feature_enabled: boolean;
  locales: string[];
  motion: MotionView;
  preferences: PreferenceView;
  reduce_motion: boolean;
  rules: RuleView[];
  snapshots: SnapshotIndexView;
  tour: TourStateView;
  tour_step: TourStepView;
}

export interface PatchResponse {
  action: string;
  result: Record<string, unknown>;
  status: AccessibilityStatus;
}

export interface TourResponse {
  operation: string;
  state: TourStateView;
  step: TourStepView;
}

export interface StatusResponse {
  data: AccessibilityStatus;
  meta: PageMetaV4;
}

export interface TranslateOptions {
  message: string;
  locale: string;
  params?: Record<string, string | number>;
  plural?: boolean;
  count?: number;
}

export class AccessibilityClientError extends Error {
  readonly code: string;
  readonly details: string[];

  constructor(code: string, message: string, details: string[] = []) {
    super(message);
    this.name = "AccessibilityClientError";
    this.code = code;
    this.details = details;
  }
}

export function describeClientError(error: unknown): AccessibilityClientError {
  if (error instanceof AccessibilityClientError) return error;
  if (error !== null && typeof error === "object") {
    const candidate = error as {
      code?: unknown;
      message?: unknown;
      details?: unknown;
    };
    const code =
      typeof candidate.code === "string" ? candidate.code : "internal";
    const message =
      typeof candidate.message === "string"
        ? candidate.message
        : "Accessibility request failed";
    const details = Array.isArray(candidate.details)
      ? candidate.details.map((item) => String(item))
      : [];
    return new AccessibilityClientError(code, message, details);
  }
  return new AccessibilityClientError(
    "internal",
    error instanceof Error ? error.message : "Accessibility request failed",
  );
}

export class AccessibilityClient {
  constructor(private readonly client: V4Client = new V4Client()) {}

  async status(): Promise<StatusResponse> {
    return this.client.get<AccessibilityStatus>(ACCESSIBILITY_ROUTE);
  }

  async patch(body: Record<string, unknown>): Promise<PatchResponse> {
    try {
      return await this.client.patch<PatchResponse>(ACCESSIBILITY_ROUTE, body);
    } catch (error) {
      throw describeClientError(error);
    }
  }

  async applyPreferences(
    overrides: Partial<PreferenceView>,
  ): Promise<PatchResponse> {
    return this.patch({ action: "preferences", preferences: overrides });
  }

  async setMotion(
    motion: "full" | "subtle" | "off",
    reduceMotion: boolean,
  ): Promise<PatchResponse> {
    return this.patch({
      action: "motion",
      motion,
      reduce_motion: reduceMotion,
    });
  }

  async reset(): Promise<PatchResponse> {
    return this.patch({ action: "reset" });
  }

  async translate(options: TranslateOptions): Promise<TranslationView> {
    const response = await this.patch({
      action: "translate",
      message: options.message,
      locale: options.locale,
      params: options.params ?? {},
      plural: options.plural ?? false,
      count: options.count ?? 1,
    });
    return response.result.translation as TranslationView;
  }

  async audit(
    descriptors: Record<string, unknown>[],
  ): Promise<AuditReportView> {
    const response = await this.patch({ action: "audit", descriptors });
    return response.result.report as AuditReportView;
  }

  async tour(operation: string): Promise<TourResponse> {
    const response = await this.patch({ action: "tour", operation });
    return {
      operation,
      state: response.result.state as TourStateView,
      step: response.result.step as TourStepView,
    };
  }

  async saveSnapshot(name: string, overwrite = false): Promise<PatchResponse> {
    return this.patch({ action: "snapshot-save", name, overwrite });
  }

  async loadSnapshot(name: string): Promise<PatchResponse> {
    return this.patch({ action: "snapshot-load", name });
  }

  async deleteSnapshot(name: string): Promise<PatchResponse> {
    return this.patch({ action: "snapshot-delete", name });
  }
}

export const accessibilityClient = new AccessibilityClient();
