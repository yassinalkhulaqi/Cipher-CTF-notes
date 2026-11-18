import { V2Client } from "../../lib/apiClient";
import type {
  ConfigSchema,
  ProfileSummary,
  RedactionResult,
  RedactionRule,
  ReportDocument,
  ReportFormat,
  ReportPreview,
  ReportSection,
  ReportTemplate,
  RenderedReport,
  ReportingHealth,
  ReportingRequest,
  SectionSummary,
  SeveritySummary,
  SourceSnapshot,
  TemplateSummary,
  ValidationReport,
} from "./types";

export interface ReportingSourceFilters {
  tag?: string;
  status?: string;
  root_id?: number;
}

export interface ReportExportResult {
  directory: string;
  formats: string[];
  outputs: Record<string, string>;
  manifest: Record<string, unknown>;
}

export interface RedactionOptions {
  rules?: RedactionRule[];
  context?: number;
}

function asRequest(value: object): ReportingRequest {
  return value as ReportingRequest;
}

function withGeneratedAt(
  config: object,
  generatedAt: string,
  extra: ReportingRequest = {},
): ReportingRequest {
  const body: ReportingRequest = { ...asRequest(config), ...extra };
  if (generatedAt) body.generated_at = generatedAt;
  return body;
}

export class ReportingClient {
  readonly routes: Record<string, string> = {
    health: "reporting.health",
    templates: "reporting.templates",
    template: "reporting.template",
    profiles: "reporting.profiles",
    configSchema: "reporting.config_schema",
    sections: "reporting.sections",
    source: "reporting.source",
    build: "reporting.build",
    preview: "reporting.preview",
    validate: "reporting.validate",
    severity: "reporting.severity",
    inclusion: "reporting.inclusion",
    render: "reporting.render",
    export: "reporting.export",
    bundle: "reporting.bundle",
    manifest: "reporting.manifest",
    redact: "reporting.redact",
    redactionRules: "reporting.redaction_rules",
    reorder: "reporting.reorder",
    move: "reporting.move",
  };

  constructor(private readonly client: V2Client) {}

  async health(): Promise<ReportingHealth> {
    return this.client.call<ReportingHealth>(this.routes.health);
  }

  async templates(): Promise<TemplateSummary[]> {
    const data = await this.client.call<{ templates: TemplateSummary[] }>(
      this.routes.templates,
    );
    return data.templates;
  }

  async template(key: string): Promise<ReportTemplate> {
    return this.client.call<ReportTemplate>(this.routes.template, { key });
  }

  async profiles(): Promise<ProfileSummary[]> {
    const data = await this.client.call<{ profiles: ProfileSummary[] }>(
      this.routes.profiles,
    );
    return data.profiles;
  }

  async configSchema(): Promise<ConfigSchema> {
    return this.client.call<ConfigSchema>(this.routes.configSchema);
  }

  async sections(
    key?: string,
    sections?: ReportSection[],
  ): Promise<SectionSummary> {
    const body: ReportingRequest = {};
    if (key) body.key = key;
    if (sections) body.sections = sections;
    return this.client.call<SectionSummary>(this.routes.sections, body);
  }

  async source(filters: ReportingSourceFilters = {}): Promise<SourceSnapshot> {
    const body: ReportingRequest = { ...filters };
    return this.client.call<SourceSnapshot>(this.routes.source, body);
  }

  async build(config: object, generatedAt = ""): Promise<ReportDocument> {
    return this.client.call<ReportDocument>(
      this.routes.build,
      withGeneratedAt(config, generatedAt),
    );
  }

  async preview(config: object, generatedAt = ""): Promise<ReportPreview> {
    return this.client.call<ReportPreview>(
      this.routes.preview,
      withGeneratedAt(config, generatedAt),
    );
  }

  async validate(config: object, generatedAt = ""): Promise<ValidationReport> {
    return this.client.call<ValidationReport>(
      this.routes.validate,
      withGeneratedAt(config, generatedAt),
    );
  }

  async severity(config: object, generatedAt = ""): Promise<SeveritySummary> {
    return this.client.call<SeveritySummary>(
      this.routes.severity,
      withGeneratedAt(config, generatedAt),
    );
  }

  async inclusion(
    config: object,
    generatedAt = "",
  ): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      this.routes.inclusion,
      withGeneratedAt(config, generatedAt),
    );
  }

  async render(
    config: object,
    format: ReportFormat,
    profile = "",
    generatedAt = "",
  ): Promise<RenderedReport> {
    return this.client.call<RenderedReport>(
      this.routes.render,
      withGeneratedAt(config, generatedAt, { format, profile }),
    );
  }

  async exportReport(
    config: object,
    format: ReportFormat,
    directory: string,
    profile = "",
    generatedAt = "",
  ): Promise<ReportExportResult> {
    return this.client.call<ReportExportResult>(
      this.routes.export,
      withGeneratedAt(config, generatedAt, { format, profile, directory }),
    );
  }

  async bundle(
    config: object,
    directory: string,
    formats: ReportFormat[],
    generatedAt = "",
  ): Promise<ReportExportResult> {
    return this.client.call<ReportExportResult>(
      this.routes.bundle,
      withGeneratedAt(config, generatedAt, { directory, formats }),
    );
  }

  async manifest(
    config: object,
    generatedAt = "",
  ): Promise<Record<string, unknown>> {
    return this.client.call<Record<string, unknown>>(
      this.routes.manifest,
      withGeneratedAt(config, generatedAt),
    );
  }

  async redact(
    text: string,
    options: RedactionOptions = {},
  ): Promise<RedactionResult> {
    const body: ReportingRequest = { text };
    if (options.rules) body.rules = options.rules;
    if (options.context !== undefined) body.context = options.context;
    return this.client.call<RedactionResult>(this.routes.redact, body);
  }

  async redactionRules(includeHosts = false): Promise<RedactionRule[]> {
    const data = await this.client.call<{ rules: RedactionRule[] }>(
      this.routes.redactionRules,
      { include_hosts: includeHosts },
    );
    return data.rules;
  }

  async reorder(
    sections: ReportSection[],
    parentId: string,
    order: string[],
  ): Promise<SectionSummary> {
    return this.client.call<SectionSummary>(this.routes.reorder, {
      sections,
      parent_id: parentId,
      order,
    });
  }

  async move(
    sections: ReportSection[],
    identifier: string,
    parentId: string,
    index: number,
  ): Promise<SectionSummary> {
    return this.client.call<SectionSummary>(this.routes.move, {
      sections,
      identifier,
      parent_id: parentId,
      index,
    });
  }
}
