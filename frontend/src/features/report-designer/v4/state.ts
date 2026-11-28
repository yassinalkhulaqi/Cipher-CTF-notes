/** Reducer and pure view helpers for the v4 report designer. */

import type {
  ExportFormatV4,
  OrientationV4,
  PageSizeV4,
  PaginatedPageV4,
  ReportLayoutV4,
  ReportSectionV4,
  SectionKindV4,
  ThemeDescriptorV4,
} from "./client";

export type ZoomModeV4 = "fit" | "75" | "100" | "125";
export type DesignerStatusV4 = "idle" | "loading" | "ready" | "error";

export interface DesignerStateV4 {
  layout: ReportLayoutV4;
  themes: ThemeDescriptorV4[];
  pages: PaginatedPageV4[];
  selectedSection: number;
  zoom: ZoomModeV4;
  format: ExportFormatV4;
  status: DesignerStatusV4;
  message: string;
  previewPage: number;
}

export type DesignerActionV4 =
  | { type: "set-title"; title: string }
  | { type: "set-subtitle"; subtitle: string }
  | { type: "select-theme"; theme: string }
  | { type: "set-page-size"; pageSize: PageSizeV4 }
  | { type: "set-orientation"; orientation: OrientationV4 }
  | { type: "select-section"; index: number }
  | { type: "add-section"; kind: SectionKindV4 }
  | { type: "remove-section"; index: number }
  | { type: "move-section"; index: number; direction: -1 | 1 }
  | { type: "toggle-break"; index: number }
  | { type: "set-zoom"; zoom: ZoomModeV4 }
  | { type: "set-format"; format: ExportFormatV4 }
  | { type: "set-page"; page: number }
  | { type: "set-themes"; themes: ThemeDescriptorV4[] }
  | { type: "set-pages"; pages: PaginatedPageV4[] }
  | { type: "set-status"; status: DesignerStatusV4; message?: string }
  | { type: "apply-layout"; layout: ReportLayoutV4 }
  | { type: "reset" };

export const SECTION_KINDS: readonly SectionKindV4[] = [
  "cover",
  "toc",
  "findings",
  "evidence",
  "appendix",
] as const;

export const ZOOM_MODES: readonly ZoomModeV4[] = [
  "fit",
  "75",
  "100",
  "125",
] as const;
export const ZOOM_SCALES: Record<ZoomModeV4, number> = {
  fit: 0.62,
  "75": 0.75,
  "100": 1,
  "125": 1.25,
};

const SECTION_TITLES: Record<SectionKindV4, string> = {
  cover: "Cover",
  toc: "Table of contents",
  findings: "Findings",
  evidence: "Evidence",
  appendix: "Appendix",
};

const BASE_LAYOUT: ReportLayoutV4 = {
  id: "draft.layout",
  title: "Untitled report",
  subtitle: "",
  theme: "classic",
  page_size: "a4",
  orientation: "portrait",
  sections: [],
  created_at: "",
};

export function sectionTitle(kind: SectionKindV4): string {
  return SECTION_TITLES[kind];
}

export function blankSection(kind: SectionKindV4): ReportSectionV4 {
  return {
    kind,
    title: SECTION_TITLES[kind],
    entries: [],
    page_break_before: kind !== "toc",
  };
}

export function initialDesignerState(
  overrides: Partial<ReportLayoutV4> = {},
): DesignerStateV4 {
  return {
    layout: {
      ...BASE_LAYOUT,
      ...overrides,
      sections: [...(overrides.sections ?? [])],
    },
    themes: [],
    pages: [],
    selectedSection: 0,
    zoom: "fit",
    format: "html",
    status: "idle",
    message: "",
    previewPage: 1,
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function withLayout(
  state: DesignerStateV4,
  layout: ReportLayoutV4,
): DesignerStateV4 {
  return { ...state, layout };
}

export function reduceDesigner(
  state: DesignerStateV4,
  action: DesignerActionV4,
): DesignerStateV4 {
  switch (action.type) {
    case "set-title":
      return withLayout(state, { ...state.layout, title: action.title });
    case "set-subtitle":
      return withLayout(state, { ...state.layout, subtitle: action.subtitle });
    case "select-theme":
      return withLayout(state, { ...state.layout, theme: action.theme });
    case "set-page-size":
      return withLayout(state, { ...state.layout, page_size: action.pageSize });
    case "set-orientation":
      return withLayout(state, {
        ...state.layout,
        orientation: action.orientation,
      });
    case "select-section":
      return {
        ...state,
        selectedSection: clamp(
          action.index,
          0,
          Math.max(0, state.layout.sections.length - 1),
        ),
      };
    case "add-section": {
      const sections = [...state.layout.sections, blankSection(action.kind)];
      return {
        ...withLayout(state, { ...state.layout, sections }),
        selectedSection: sections.length - 1,
      };
    }
    case "remove-section": {
      if (action.index < 0 || action.index >= state.layout.sections.length)
        return state;
      const sections = state.layout.sections.filter(
        (_, index) => index !== action.index,
      );
      return {
        ...withLayout(state, { ...state.layout, sections }),
        selectedSection: clamp(
          state.selectedSection,
          0,
          Math.max(0, sections.length - 1),
        ),
      };
    }
    case "move-section": {
      const { sections } = state.layout;
      const target = action.index + action.direction;
      if (action.index < 0 || target < 0 || target >= sections.length)
        return state;
      const reordered = [...sections];
      const moved = reordered[action.index];
      reordered[action.index] = reordered[target];
      reordered[target] = moved;
      return {
        ...withLayout(state, { ...state.layout, sections: reordered }),
        selectedSection: target,
      };
    }
    case "toggle-break": {
      if (action.index < 0 || action.index >= state.layout.sections.length)
        return state;
      const sections = state.layout.sections.map((section, index) =>
        index === action.index
          ? { ...section, page_break_before: !section.page_break_before }
          : section,
      );
      return withLayout(state, { ...state.layout, sections });
    }
    case "set-zoom":
      return { ...state, zoom: action.zoom };
    case "set-format":
      return { ...state, format: action.format };
    case "set-page":
      return {
        ...state,
        previewPage: clamp(action.page, 1, Math.max(1, state.pages.length)),
      };
    case "set-themes":
      return { ...state, themes: [...action.themes] };
    case "set-pages":
      return {
        ...state,
        pages: [...action.pages],
        previewPage: clamp(
          state.previewPage,
          1,
          Math.max(1, action.pages.length),
        ),
      };
    case "set-status":
      return {
        ...state,
        status: action.status,
        message: action.message ?? state.message,
      };
    case "apply-layout":
      return {
        ...state,
        layout: {
          ...action.layout,
          sections: [...action.layout.sections],
        },
        selectedSection: 0,
        previewPage: 1,
        status: "ready",
        message: `Loaded ${action.layout.title}`,
      };
    case "reset":
      return initialDesignerState();
    default:
      return state;
  }
}

export function zoomScale(zoom: ZoomModeV4): number {
  return ZOOM_SCALES[zoom];
}

export function pageDimensions(
  layout: ReportLayoutV4,
  zoom: ZoomModeV4,
): { width: number; height: number; scale: number; label: string } {
  const size: Record<PageSizeV4, [number, number]> = {
    a4: [210, 297],
    letter: [216, 279],
    a5: [148, 210],
  };
  const [widthMm, heightMm] = size[layout.page_size];
  const [paperWidth, paperHeight] =
    layout.orientation === "landscape"
      ? [heightMm, widthMm]
      : [widthMm, heightMm];
  const pixelsPerMm = 96 / 25.4;
  const scale = zoomScale(zoom);
  return {
    width: Math.round(paperWidth * pixelsPerMm * scale),
    height: Math.round(paperHeight * pixelsPerMm * scale),
    scale,
    label: `${layout.page_size.toUpperCase()} ${layout.orientation} · ${Math.round(scale * 100)}%`,
  };
}

export interface PageSummaryV4 {
  total: number;
  lines: number;
  firstSection: string;
  byKind: Record<SectionKindV4, number>;
}

export function pageSummary(pages: PaginatedPageV4[]): PageSummaryV4 {
  const byKind: Record<SectionKindV4, number> = {
    cover: 0,
    toc: 0,
    findings: 0,
    evidence: 0,
    appendix: 0,
  };
  for (const page of pages) byKind[page.section] += 1;
  return {
    total: pages.length,
    lines: pages.reduce((sum, page) => sum + page.lines.length, 0),
    firstSection: pages[0]?.title ?? "No pages",
    byKind,
  };
}

export function selectedSection(
  state: DesignerStateV4,
): ReportSectionV4 | undefined {
  return state.layout.sections[state.selectedSection];
}

export function canMoveSection(
  state: DesignerStateV4,
  index: number,
  direction: -1 | 1,
): boolean {
  const target = index + direction;
  return index >= 0 && target >= 0 && target < state.layout.sections.length;
}

export function visiblePage(
  state: DesignerStateV4,
): PaginatedPageV4 | undefined {
  return state.pages[state.previewPage - 1];
}

export function statusTone(status: DesignerStatusV4): string {
  switch (status) {
    case "error":
      return "danger";
    case "ready":
      return "success";
    case "loading":
      return "info";
    default:
      return "muted";
  }
}

export function describeState(state: DesignerStateV4): string {
  const summary = pageSummary(state.pages);
  return (
    `${state.layout.title} · ${state.layout.sections.length} sections · ` +
    `${summary.total} pages · ${state.format} · ${state.zoom}`
  );
}
