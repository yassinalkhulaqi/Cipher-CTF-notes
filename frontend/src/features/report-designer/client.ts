/** Typed client for the reports namespace of the V3 API. */

import { V3Client } from "../../v3/apiClient";
import type {
  DesignResult,
  DesignSpec,
  PreviewResult,
  RenderFormat,
  RenderOutput,
  ReportsHealth,
  ThemeDescriptor,
  ThemeSummary,
  ValidationResult,
} from "./types";

export interface ThemesResponse {
  default: string;
  themes: ThemeDescriptor[];
  summaries: ThemeSummary[];
}

export interface FormatsResponse {
  formats: RenderFormat[];
  mime_types: Record<string, string>;
  extensions: Record<string, string>;
}

export interface PaginateResponse {
  plan: DesignResult["pagination"];
  entries: DesignResult["toc"];
}

export interface ManifestResponse {
  manifest: Record<string, unknown>;
  theme: string;
  sections: number;
  pages: number;
}

export interface RedactResponse {
  preview: DesignResult["redaction_preview"];
  rules: DesignSpec["redactions"];
  applied: string[];
}

function bodyOf(spec: DesignSpec): Record<string, unknown> {
  return { ...spec };
}

export class ReportDesignerClient {
  readonly routes: Record<string, string> = {
    health: "reports.health",
    themes: "reports.themes",
    formats: "reports.formats",
    design: "reports.design",
    preview: "reports.preview",
    paginate: "reports.paginate",
    render: "reports.render",
    manifest: "reports.manifest",
    redact: "reports.redact",
    validate: "reports.validate",
  };

  constructor(private readonly client: V3Client) {}

  async health(): Promise<ReportsHealth> {
    return this.client.data<ReportsHealth>("reports", "health");
  }

  async themes(): Promise<ThemesResponse> {
    return this.client.data<ThemesResponse>("reports", "themes");
  }

  async formats(): Promise<FormatsResponse> {
    return this.client.data<FormatsResponse>("reports", "formats");
  }

  async design(spec: DesignSpec): Promise<DesignResult> {
    return this.client.data<DesignResult>("reports", "design", bodyOf(spec));
  }

  async preview(spec: DesignSpec): Promise<PreviewResult> {
    return this.client.data<PreviewResult>("reports", "preview", bodyOf(spec));
  }

  async paginate(spec: DesignSpec): Promise<PaginateResponse> {
    return this.client.data<PaginateResponse>(
      "reports",
      "paginate",
      bodyOf(spec),
    );
  }

  async render(spec: DesignSpec, format: RenderFormat): Promise<RenderOutput> {
    return this.client.data<RenderOutput>("reports", "render", {
      ...bodyOf(spec),
      format,
    });
  }

  async manifest(spec: DesignSpec): Promise<ManifestResponse> {
    return this.client.data<ManifestResponse>(
      "reports",
      "manifest",
      bodyOf(spec),
    );
  }

  async redact(spec: DesignSpec): Promise<RedactResponse> {
    return this.client.data<RedactResponse>("reports", "redact", bodyOf(spec));
  }

  async validate(spec: DesignSpec): Promise<ValidationResult> {
    return this.client.data<ValidationResult>(
      "reports",
      "validate",
      bodyOf(spec),
    );
  }
}
