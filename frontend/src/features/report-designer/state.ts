/** Reducer and selectors for the report designer feature. */

import { designSignature } from "./format";
import type {
  DesignSpec,
  DesignResult,
  FindingItem,
  LayoutSection,
  RedactionRule,
  RenderFormat,
  SectionKind,
  SelectionRule,
} from "./types";

export interface SectionDraft {
  key: string;
  title: string;
  kind: SectionKind;
  level: number;
  body: string;
  visible: boolean;
  includeToc: boolean;
  pageBreakBefore: boolean;
  order: number;
}

export type DesignerStatus = "idle" | "loading" | "ready" | "error";

export interface DesignerState {
  title: string;
  subtitle: string;
  client: string;
  author: string;
  classification: string;
  generatedAt: string;
  theme: string;
  sections: SectionDraft[];
  findings: FindingItem[];
  excluded: string[];
  rules: SelectionRule[];
  redactions: RedactionRule[];
  formats: RenderFormat[];
  options: Record<string, boolean>;
  zoom: number;
  selectedSection: string;
  activeFormat: RenderFormat;
  printPreview: boolean;
  showRedactions: boolean;
  status: DesignerStatus;
  error: string;
  preview: DesignResult | null;
}

export type DesignerAction =
  | { type: "field"; field: TextField; value: string }
  | { type: "theme"; value: string }
  | { type: "zoom"; value: number }
  | { type: "activeFormat"; value: RenderFormat }
  | { type: "select"; key: string }
  | { type: "toggleVisible"; key: string }
  | { type: "toggleToc"; key: string }
  | { type: "togglePageBreak"; key: string }
  | { type: "moveSection"; key: string; delta: number }
  | { type: "dropSection"; from: number; to: number }
  | { type: "addSection"; kind: SectionKind }
  | { type: "removeSection"; key: string }
  | { type: "toggleFinding"; ref: string }
  | { type: "updateRedaction"; index: number; patch: Partial<RedactionRule> }
  | { type: "addRedaction" }
  | { type: "removeRedaction"; index: number }
  | { type: "toggleFormat"; format: RenderFormat }
  | { type: "setOption"; name: string; value: boolean }
  | { type: "togglePrintPreview" }
  | { type: "toggleRedactions" }
  | { type: "status"; value: DesignerStatus }
  | { type: "error"; value: string }
  | { type: "preview"; value: DesignResult };

export type TextField =
  | "title"
  | "subtitle"
  | "client"
  | "author"
  | "classification"
  | "generatedAt";

export const DESIGN_FORMATS: RenderFormat[] = [
  "html",
  "markdown",
  "json",
  "print",
];

export function emptySelectionRule(name: string): SelectionRule {
  return {
    name,
    action: "include",
    severities: [],
    statuses: [],
    tags: [],
    categories: [],
    minimum_confidence: 0,
    identifier: "",
  };
}

export function sampleFindings(): FindingItem[] {
  return [
    {
      ref: "finding:auth-bypass",
      label: "Auth bypass",
      title: "Authentication bypass in admin portal",
      summary: "Unauthenticated access to admin@example.com endpoints.",
      severity: "high",
      status: "confirmed",
      category: "authentication",
      tags: ["web", "owasp"],
      confidence: 0.92,
      impact: "Full administrative control of the application.",
      recommendation: "Enforce authentication on every admin route.",
      evidence: [
        {
          ref: "evidence:http-log",
          label: "HTTP log",
          title: "HTTP request log",
          content:
            "GET /admin as admin@example.com from 10.0.0.12 flag{demo0001}",
          excerpt: "GET /admin returned HTTP 200 without a session cookie.",
          kind: "command",
          locator: "line 14",
          sensitive: false,
        },
      ],
      references: ["CWE-287"],
      identifier: "auth-bypass",
    },
    {
      ref: "finding:verbose-headers",
      label: "Verbose headers",
      title: "Verbose server headers",
      summary: "Server version disclosed in response headers.",
      severity: "low",
      status: "open",
      category: "information",
      tags: ["web"],
      confidence: 0.78,
      impact: "Minor information disclosure.",
      recommendation: "Remove version banners from responses.",
      evidence: [],
      references: [],
      identifier: "verbose-headers",
    },
  ];
}

export function sampleRedactions(): RedactionRule[] {
  return [
    {
      name: "email",
      pattern: "[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}",
      replacement: "[EMAIL]",
      enabled: true,
      priority: 30,
      scope: "all",
    },
    {
      name: "ipv4",
      pattern: "\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b",
      replacement: "[IP]",
      enabled: true,
      priority: 50,
      scope: "all",
    },
  ];
}

export function initialDesignerState(): DesignerState {
  return {
    title: "Client Security Assessment",
    subtitle: "External penetration test",
    client: "Acme Corp",
    author: "RedScribe",
    classification: "confidential",
    generatedAt: "2026-01-01T00:00:00Z",
    theme: "client",
    sections: [
      {
        key: "executive-summary",
        title: "Executive Summary",
        kind: "executive_summary",
        level: 1,
        body: "This assessment covered the external web footprint.",
        visible: true,
        includeToc: true,
        pageBreakBefore: false,
        order: 0,
      },
      {
        key: "scope",
        title: "Scope and Methodology",
        kind: "text",
        level: 1,
        body: "Testing was performed against acme.com with a fixed scope.",
        visible: true,
        includeToc: true,
        pageBreakBefore: false,
        order: 1,
      },
      {
        key: "recommendations",
        title: "Recommendations",
        kind: "recommendations",
        level: 1,
        body: "Prioritise remediation of high severity findings.",
        visible: true,
        includeToc: true,
        pageBreakBefore: false,
        order: 2,
      },
    ],
    findings: sampleFindings(),
    excluded: [],
    rules: [],
    redactions: sampleRedactions(),
    formats: [...DESIGN_FORMATS],
    options: {
      cover: true,
      toc: true,
      appendix: true,
      findings_section: true,
      redact: true,
    },
    zoom: 100,
    selectedSection: "executive-summary",
    activeFormat: "html",
    printPreview: false,
    showRedactions: true,
    status: "idle",
    error: "",
    preview: null,
  };
}

function moveByDelta(
  sections: SectionDraft[],
  key: string,
  delta: number,
): SectionDraft[] {
  const from = sections.findIndex((section) => section.key === key);
  if (from < 0) return sections;
  const to = Math.min(
    sections.length - 1,
    Math.max(0, from + Math.sign(delta)),
  );
  if (from === to) return sections;
  const next = [...sections];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return reindex(next);
}

function reindex(sections: SectionDraft[]): SectionDraft[] {
  return sections.map((section, index) => ({ ...section, order: index }));
}

export function designerReducer(
  state: DesignerState,
  action: DesignerAction,
): DesignerState {
  switch (action.type) {
    case "field":
      return { ...state, [action.field]: action.value };
    case "theme":
      return { ...state, theme: action.value };
    case "zoom":
      return { ...state, zoom: action.value };
    case "activeFormat":
      return { ...state, activeFormat: action.value };
    case "select":
      return { ...state, selectedSection: action.key };
    case "toggleVisible":
      return {
        ...state,
        sections: state.sections.map((section) =>
          section.key === action.key
            ? { ...section, visible: !section.visible }
            : section,
        ),
      };
    case "toggleToc":
      return {
        ...state,
        sections: state.sections.map((section) =>
          section.key === action.key
            ? { ...section, includeToc: !section.includeToc }
            : section,
        ),
      };
    case "togglePageBreak":
      return {
        ...state,
        sections: state.sections.map((section) =>
          section.key === action.key
            ? { ...section, pageBreakBefore: !section.pageBreakBefore }
            : section,
        ),
      };
    case "moveSection":
      return {
        ...state,
        sections: moveByDelta(state.sections, action.key, action.delta),
      };
    case "dropSection": {
      if (action.from < 0 || action.from >= state.sections.length) return state;
      const to = Math.min(state.sections.length - 1, Math.max(0, action.to));
      const next = [...state.sections];
      const [item] = next.splice(action.from, 1);
      next.splice(to, 0, item);
      return { ...state, sections: reindex(next), selectedSection: item.key };
    }
    case "addSection": {
      const key = `section-${state.sections.length + 1}`;
      const section: SectionDraft = {
        key,
        title: `New ${action.kind.replace("_", " ")} section`,
        kind: action.kind,
        level: 1,
        body: "",
        visible: true,
        includeToc: true,
        pageBreakBefore: false,
        order: state.sections.length,
      };
      return {
        ...state,
        sections: [...state.sections, section],
        selectedSection: key,
      };
    }
    case "removeSection": {
      const sections = state.sections.filter(
        (section) => section.key !== action.key,
      );
      return {
        ...state,
        sections: reindex(sections),
        selectedSection:
          state.selectedSection === action.key
            ? (sections[0]?.key ?? "")
            : state.selectedSection,
      };
    }
    case "toggleFinding": {
      const excluded = state.excluded.includes(action.ref)
        ? state.excluded.filter((ref) => ref !== action.ref)
        : [...state.excluded, action.ref];
      return { ...state, excluded };
    }
    case "updateRedaction":
      return {
        ...state,
        redactions: state.redactions.map((rule, index) =>
          index === action.index ? { ...rule, ...action.patch } : rule,
        ),
      };
    case "addRedaction":
      return {
        ...state,
        redactions: [
          ...state.redactions,
          {
            name: `custom-${state.redactions.length + 1}`,
            pattern: "SECRET",
            replacement: "[REDACTED]",
            enabled: true,
            priority: 100,
            scope: "all",
          },
        ],
      };
    case "removeRedaction":
      return {
        ...state,
        redactions: state.redactions.filter(
          (_rule, index) => index !== action.index,
        ),
      };
    case "toggleFormat": {
      const formats = state.formats.includes(action.format)
        ? state.formats.filter((format) => format !== action.format)
        : [...state.formats, action.format];
      return { ...state, formats };
    }
    case "setOption":
      return {
        ...state,
        options: { ...state.options, [action.name]: action.value },
      };
    case "togglePrintPreview":
      return { ...state, printPreview: !state.printPreview };
    case "toggleRedactions":
      return { ...state, showRedactions: !state.showRedactions };
    case "status":
      return { ...state, status: action.value };
    case "error":
      return { ...state, status: "error", error: action.value };
    case "preview":
      return { ...state, status: "ready", preview: action.value, error: "" };
  }
}

export function sectionsToLayout(sections: SectionDraft[]): LayoutSection[] {
  return sections.map((section) => ({
    key: section.key,
    title: section.title,
    kind: section.kind,
    level: section.level,
    order: section.order,
    visible: section.visible,
    body: section.body,
    summary: "",
    findings: [],
    children: [],
    page_break_before: section.pageBreakBefore,
    include_toc: section.includeToc,
    metadata: {},
    anchor: `sec-${section.key}`,
  }));
}

export function specFromState(state: DesignerState): DesignSpec {
  const explicitRules: SelectionRule[] = state.excluded.map((ref) => ({
    ...emptySelectionRule(`hide-${ref}`),
    action: "exclude",
    identifier: ref,
  }));
  return {
    key: `designer-${state.title.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "report"}`,
    title: state.title,
    subtitle: state.subtitle,
    client: state.client,
    author: state.author,
    classification: state.classification,
    generated_at: state.generatedAt,
    theme: state.theme,
    sections: sectionsToLayout(state.sections),
    findings: state.findings,
    rules: [...state.rules, ...explicitRules],
    redactions: state.redactions,
    minimum_severity: "info",
    statuses: [],
    tags: [],
    require_evidence: false,
    include_sensitive_evidence: false,
    formats: [...state.formats],
    options: { ...state.options },
  };
}

export function designerSignature(state: DesignerState): string {
  return designSignature(specFromState(state));
}
