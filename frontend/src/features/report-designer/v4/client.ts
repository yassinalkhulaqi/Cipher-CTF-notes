/** Typed API client for the v4 report designer surface. */

import { V4Client } from "../../v4-kernel/client";
import type { V4RequestOptions } from "../../v4-kernel/client";
import type { PageMetaV4 } from "../../v4-kernel/types-v4";

export type PageSizeV4 = "a4" | "letter" | "a5";
export type OrientationV4 = "portrait" | "landscape";
export type SectionKindV4 =
  | "cover"
  | "toc"
  | "findings"
  | "evidence"
  | "appendix";
export type ExportFormatV4 = "html" | "markdown";

export interface ThemeColorsV4 {
  primary?: string;
  secondary?: string;
  accent?: string;
  text?: string;
  background?: string;
  muted?: string;
  border?: string;
}

export interface ThemeFontsV4 {
  heading?: string;
  body?: string;
  mono?: string;
  body_size?: number;
  line_height?: number;
}

export interface ThemeMarginsV4 {
  top?: number;
  right?: number;
  bottom?: number;
  left?: number;
}

export interface ThemeDescriptorV4 {
  name: string;
  parent: string;
  lineage: string[];
  description: string;
}

export interface ResolvedThemeV4 {
  name: string;
  colors: Record<string, string>;
  fonts: Record<string, string | number>;
  margins: Record<string, number>;
  header: string;
  footer: string;
  lineage: string[];
}

export interface ReportEntryV4 {
  title: string;
  detail: string;
  level: number;
  ref: string;
}

export interface ReportSectionV4 {
  kind: SectionKindV4;
  title: string;
  entries: ReportEntryV4[];
  page_break_before: boolean;
}

export interface ReportLayoutV4 {
  id: string;
  title: string;
  subtitle: string;
  theme: string;
  page_size: PageSizeV4;
  orientation: OrientationV4;
  sections: ReportSectionV4[];
  created_at: string;
}

export interface PaginatedPageV4 {
  number: number;
  section: SectionKindV4;
  lines: string[];
  title: string;
}

export interface ReportFindingV4 {
  ref: string;
  title: string;
  severity: string;
  detail: string;
  evidence: string[];
}

export interface ReportEvidenceV4 {
  ref: string;
  label: string;
  source: string;
  summary: string;
  tags: string[];
}

export interface ReportSourceV4 {
  title: string;
  subtitle: string;
  findings: ReportFindingV4[];
  evidence: ReportEvidenceV4[];
  appendix: string[];
  metadata: Array<[string, string]>;
}

export interface RenderedReportV4 {
  layout_id: string;
  format: ExportFormatV4;
  extension: string;
  mime_type: string;
  page_count: number;
  checksum: string;
  preview: string;
  text: string;
  pages: PaginatedPageV4[];
}

export interface PagedV4<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  next_cursor: string;
  etag: string;
}

export interface ExportManifestV4 {
  id: string;
  version: number;
  generated_at: string;
  digest: string;
  entries: Array<{
    layout_id: string;
    format: string;
    checksum: string;
    page_count: number;
  }>;
}

export interface DesignerStatsV4 {
  layouts: number;
  sections: number;
  entries: number;
  themes: number;
  page_sizes: number;
  theme_index: Record<string, number>;
  page_size: {
    lines_per_page: number;
    line_width: number;
    section_gap: number;
  };
}

export interface DescribeResultV4 {
  service: string;
  actions: string[];
  capabilities: string[];
  routes: string[];
  formats: string[];
}

export interface ApiResult<T> {
  data: T;
  meta: PageMetaV4;
}

export class ReportDesignerClient {
  constructor(private readonly client: V4Client = new V4Client("/api/v4")) {}

  private actionUrl(
    action: string,
    params: Record<string, string> = {},
  ): string {
    const url = new URL(
      `/reports?action=${encodeURIComponent(action)}`,
      "http://localhost",
    );
    for (const [key, value] of Object.entries(params)) {
      if (value) url.searchParams.set(key, value);
    }
    return `${url.pathname}${url.search}`;
  }

  private async get<T>(
    action: string,
    params: Record<string, string>,
    options: V4RequestOptions = {},
  ): Promise<ApiResult<T>> {
    return this.client.get<T>(this.actionUrl(action, params), options);
  }

  private post<T>(action: string, payload: object = {}): Promise<T> {
    return this.client.post<T>("/reports", { action, ...payload });
  }

  describe(): Promise<ApiResult<DescribeResultV4>> {
    return this.get<DescribeResultV4>("describe", {});
  }

  themes(
    page = 1,
    pageSize = 50,
  ): Promise<ApiResult<PagedV4<ThemeDescriptorV4>>> {
    return this.get<PagedV4<ThemeDescriptorV4>>(
      "themes",
      {},
      { page, pageSize },
    );
  }

  theme(name: string): Promise<ApiResult<ResolvedThemeV4>> {
    return this.get<ResolvedThemeV4>("theme", { theme: name });
  }

  layouts(
    page = 1,
    pageSize = 50,
    theme = "",
  ): Promise<ApiResult<PagedV4<ReportLayoutV4>>> {
    return this.get<PagedV4<ReportLayoutV4>>(
      "layouts",
      { theme },
      { page, pageSize },
    );
  }

  layout(id: string): Promise<ApiResult<ReportLayoutV4>> {
    return this.get<ReportLayoutV4>("layout", { layout_id: id });
  }

  create(layout: Partial<ReportLayoutV4>): Promise<ReportLayoutV4> {
    return this.post<ReportLayoutV4>("create", layout);
  }

  update(
    id: string,
    changes: Partial<ReportLayoutV4>,
  ): Promise<ReportLayoutV4> {
    return this.post<ReportLayoutV4>("update", {
      layout_id: id,
      changes,
    });
  }

  remove(id: string): Promise<ReportLayoutV4> {
    return this.post<ReportLayoutV4>("delete", { layout_id: id });
  }

  pages(
    id: string,
    page = 1,
    pageSize = 50,
  ): Promise<ApiResult<PagedV4<PaginatedPageV4>>> {
    return this.get<PagedV4<PaginatedPageV4>>(
      "pages",
      { layout_id: id },
      { page, pageSize },
    );
  }

  build(
    source: ReportSourceV4,
    options: { layoutId?: string; theme?: string } = {},
  ): Promise<ReportLayoutV4> {
    return this.post<ReportLayoutV4>("build", {
      source,
      layout_id: options.layoutId ?? "",
      theme: options.theme ?? "classic",
    });
  }

  render(
    id: string,
    format: ExportFormatV4 = "html",
    trigger = "ui",
  ): Promise<RenderedReportV4> {
    return this.post<RenderedReportV4>("render", {
      layout_id: id,
      format,
      trigger,
    });
  }

  manifest(entries?: ExportManifestV4["entries"]): Promise<ExportManifestV4> {
    return this.post<ExportManifestV4>("manifest", {
      manifests: entries ?? [],
    });
  }

  stats(): Promise<ApiResult<DesignerStatsV4>> {
    return this.get<DesignerStatsV4>("stats", {});
  }
}

export const reportDesignerClient = new ReportDesignerClient();
