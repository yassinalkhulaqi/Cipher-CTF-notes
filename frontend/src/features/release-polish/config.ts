/** Static release-polish catalogue mirrored from the Python release content. */

import type {
  AnimationAudit,
  Breakpoint,
  EmptyStateSpec,
  IconLabel,
  OnboardingStep,
  PolishCheck,
  ShowcaseEntry,
} from "./types";

export const RELEASE_NAMESPACE = "release";

export const RELEASE_ROUTES = {
  manifest: "manifest",
  golden: "golden",
  smoke: "smoke",
  gates: "gates",
  gateAudit: "gate_audit",
  docs: "docs",
  changelog: "changelog",
  migrationNotes: "migration_notes",
  readiness: "readiness",
  onboarding: "onboarding",
  showcase: "showcase",
  polish: "polish",
} as const;

export const GOLDEN_PHASES: readonly string[] = [
  "capture",
  "finding",
  "evidence",
  "report",
  "export",
  "import",
  "merge",
];

export const ONBOARDING_STEPS: readonly OnboardingStep[] = [
  {
    id: "welcome",
    title: "Welcome to RedScribe",
    description:
      "A local-first notebook for captures, findings, evidence, and reports.",
    control: "welcome-card",
    hint: "Nothing leaves this device.",
    required: true,
  },
  {
    id: "first-capture",
    title: "Record your first capture",
    description: "Create a note to anchor the engagement timeline.",
    control: "quick-capture-button",
    hint: "Press N from anywhere to open quick capture.",
    required: true,
  },
  {
    id: "confirm-local",
    title: "Confirm local storage",
    description:
      "Your vault is stored on disk and never sent to a remote service.",
    control: "storage-status-badge",
    hint: "Offline-only is enabled by default.",
    required: true,
  },
  {
    id: "review-basics",
    title: "Review the design system",
    description:
      "See panels, metrics, kind colors, density, and motion tokens.",
    control: "showcase-panel",
    hint: "Keyboard focus use is visible on every control.",
    required: true,
  },
  {
    id: "start-engagement",
    title: "Start your engagement",
    description: "Add a target and move your first note into a finding.",
    control: "engagement-launch-button",
    hint: "You can revisit these steps from Help.",
    required: false,
  },
];

export const EMPTY_STATES: readonly EmptyStateSpec[] = [
  {
    surface: "notes",
    title: "No captures yet",
    body: "Quick capture creates the first note in this vault.",
    actionLabel: "Create a note",
    actionRoute: "capture.create",
    icon: "file-text",
  },
  {
    surface: "findings",
    title: "No findings yet",
    body: "Promote a note into a finding to start the report.",
    actionLabel: "New finding",
    actionRoute: "findings.create",
    icon: "alert",
  },
  {
    surface: "evidence",
    title: "No evidence attached",
    body: "Attach a file or hash to preserve the chain of custody.",
    actionLabel: "Attach evidence",
    actionRoute: "evidence.ingest",
    icon: "paperclip",
  },
  {
    surface: "report",
    title: "Report is empty",
    body: "Findings you compose are collected here automatically.",
    actionLabel: "Compose report",
    actionRoute: "reports.compose",
    icon: "book",
  },
  {
    surface: "activity",
    title: "No activity recorded",
    body: "Actions appear here as correlated local events.",
    actionLabel: "Open capture",
    actionRoute: "capture.create",
    icon: "activity",
  },
];

export const SHOWCASE_ENTRIES: readonly ShowcaseEntry[] = [
  { token: "--v3-surface", label: "Surface", kind: "note", preview: "panel" },
  {
    token: "--v3-surface-raised",
    label: "Raised surface",
    kind: "folder",
    preview: "stat",
  },
  { token: "--v3-text", label: "Primary text", kind: "section", preview: "Aa" },
  {
    token: "--v3-text-muted",
    label: "Muted text",
    kind: "section",
    preview: "Aa",
  },
  { token: "--v3-focus", label: "Focus ring", kind: "target", preview: "ring" },
  {
    token: "--v3-good",
    label: "Positive tone",
    kind: "evidence",
    preview: "good",
  },
  { token: "--v3-warn", label: "Warning tone", kind: "run", preview: "warn" },
  {
    token: "--v3-bad",
    label: "Negative tone",
    kind: "finding",
    preview: "bad",
  },
  {
    token: "--v3-kind-target",
    label: "Target color",
    kind: "target",
    preview: "crosshair",
  },
  {
    token: "--v3-kind-evidence",
    label: "Evidence color",
    kind: "evidence",
    preview: "paperclip",
  },
  {
    token: "--v3-kind-finding",
    label: "Finding color",
    kind: "finding",
    preview: "alert",
  },
  {
    token: "--v3-kind-report",
    label: "Report color",
    kind: "report",
    preview: "book",
  },
];

export const ICON_LABELS: readonly IconLabel[] = [
  { icon: "file-text", label: "Note", kind: "note" },
  { icon: "folder", label: "Folder", kind: "folder" },
  { icon: "crosshair", label: "Target", kind: "target" },
  { icon: "alert", label: "Finding", kind: "finding" },
  { icon: "paperclip", label: "Evidence", kind: "evidence" },
  { icon: "list", label: "Playbook", kind: "playbook" },
  { icon: "play", label: "Run", kind: "run" },
  { icon: "book", label: "Report", kind: "report" },
  { icon: "layout", label: "Section", kind: "section" },
  { icon: "activity", label: "Activity", kind: "activity" },
  { icon: "puzzle", label: "Extension", kind: "extension" },
  { icon: "terminal", label: "Snippet", kind: "snippet" },
];

export const KIND_LABELS: Record<string, string> = {
  note: "Note",
  folder: "Folder",
  target: "Target",
  finding: "Finding",
  evidence: "Evidence",
  playbook: "Playbook",
  run: "Run",
  report: "Report",
  section: "Section",
  activity: "Activity",
  extension: "Extension",
  snippet: "Snippet",
};

export const ANIMATION_AUDITS: readonly AnimationAudit[] = [
  {
    surface: "panel-enter",
    property: "opacity",
    durationToken: "--v3-motion-normal",
    reducedMotionSafe: true,
    note: "Fades content without shifting layout.",
  },
  {
    surface: "stat-count",
    property: "font-variant-numeric",
    durationToken: "--v3-motion-fast",
    reducedMotionSafe: true,
    note: "Tabular values avoid jitter under reduced motion.",
  },
  {
    surface: "toast-stack",
    property: "transform",
    durationToken: "--v3-motion-normal",
    reducedMotionSafe: true,
    note: "Slides are disabled with prefers-reduced-motion.",
  },
  {
    surface: "aurora-background",
    property: "filter",
    durationToken: "--v3-motion-slow",
    reducedMotionSafe: true,
    note: "Static gradient is used when motion is reduced.",
  },
  {
    surface: "skeleton-shimmer",
    property: "background-position",
    durationToken: "--v3-motion-slow",
    reducedMotionSafe: false,
    note: "Fallback to a solid placeholder is required.",
  },
];

export const POLISH_CHECKS: readonly PolishCheck[] = [
  {
    id: "onboarding.steps",
    area: "Onboarding",
    label: "Ordered first-run steps",
    detail: "Five guided steps with a skippable final action.",
    severity: "major",
    done: true,
  },
  {
    id: "onboarding.progress",
    area: "Onboarding",
    label: "Progress is visible",
    detail: "Completed and required counts are shown.",
    severity: "minor",
    done: true,
  },
  {
    id: "empty.notes",
    area: "Empty states",
    label: "Notes empty state",
    detail: "Named surface, action label, and route are defined.",
    severity: "major",
    done: true,
  },
  {
    id: "empty.findings",
    area: "Empty states",
    label: "Findings empty state",
    detail: "Promotes a note into a finding.",
    severity: "major",
    done: true,
  },
  {
    id: "empty.evidence",
    area: "Empty states",
    label: "Evidence empty state",
    detail: "Explains hashing and custody.",
    severity: "major",
    done: true,
  },
  {
    id: "showcase.density",
    area: "Design system",
    label: "Density modes",
    detail: "Compact and comfortable are both demonstrated.",
    severity: "minor",
    done: true,
  },
  {
    id: "showcase.kinds",
    area: "Design system",
    label: "Kind colors",
    detail: "All entity kinds resolve to a semantic token.",
    severity: "major",
    done: true,
  },
  {
    id: "icons.labels",
    area: "Iconography",
    label: "Icons carry labels",
    detail: "Every icon is paired with a stable kind label.",
    severity: "major",
    done: true,
  },
  {
    id: "labels.consistency",
    area: "Iconography",
    label: "Labels are consistent",
    detail: "Singular and plural labels match the registry.",
    severity: "minor",
    done: true,
  },
  {
    id: "motion.reduced",
    area: "Animation",
    label: "Reduced-motion path",
    detail: "Content stays usable with transitions removed.",
    severity: "blocker",
    done: true,
  },
  {
    id: "motion.tokens",
    area: "Animation",
    label: "Token usage",
    detail: "Durations use v3 motion tokens only.",
    severity: "major",
    done: true,
  },
  {
    id: "responsive.breakpoints",
    area: "Responsive",
    label: "Breakpoint coverage",
    detail: "Narrow, medium, and wide layouts are checked.",
    severity: "major",
    done: true,
  },
  {
    id: "responsive.focus",
    area: "Responsive",
    label: "Focus order",
    detail: "Keyboard order follows visual order at each size.",
    severity: "blocker",
    done: true,
  },
  {
    id: "responsive.touch",
    area: "Responsive",
    label: "Touch targets",
    detail: "Controls remain reachable at compact density.",
    severity: "minor",
    done: true,
  },
];

export const BREAKPOINTS: readonly Breakpoint[] = [
  { name: "narrow", width: 480 },
  { name: "medium", width: 768 },
  { name: "wide", width: 1280 },
];

export const MOTION_TOKENS: readonly string[] = [
  "--v3-motion-fast",
  "--v3-motion-normal",
  "--v3-motion-slow",
  "--v3-ease",
];

export const RELEASE_SURFACES: readonly string[] = [
  "onboarding-flow",
  "empty-first-run",
  "design-system-showcase",
  "iconography-label-audit",
  "animation-audit",
  "responsive-polish-checklist",
];
