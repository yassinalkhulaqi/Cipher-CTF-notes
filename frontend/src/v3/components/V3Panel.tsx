import type { CSSProperties, ReactNode } from "react";

import type { EntityKind } from "../types";

export interface V3PanelProps {
  title: string;
  subtitle?: string;
  kind?: EntityKind;
  actions?: ReactNode;
  children: ReactNode;
  density?: "comfortable" | "compact";
}

const KIND_COLORS: Record<string, string> = {
  note: "var(--v3-kind-note)",
  folder: "var(--v3-kind-folder)",
  target: "var(--v3-kind-target)",
  finding: "var(--v3-kind-finding)",
  evidence: "var(--v3-kind-evidence)",
  playbook: "var(--v3-kind-playbook)",
  run: "var(--v3-kind-run)",
  report: "var(--v3-kind-report)",
  section: "var(--v3-kind-section)",
  activity: "var(--v3-kind-activity)",
  extension: "var(--v3-kind-extension)",
  snippet: "var(--v3-kind-snippet)",
};

export function kindColor(kind: EntityKind | undefined): string {
  return (kind && KIND_COLORS[kind]) || "var(--v3-kind-default)";
}

export function V3Panel({
  title,
  subtitle,
  kind,
  actions,
  children,
  density = "comfortable",
}: V3PanelProps) {
  return (
    <section
      className="v3-panel"
      data-density={density}
      style={{ "--v3-accent": kindColor(kind) } as CSSProperties}
    >
      <header className="v3-panel__header">
        <div>
          <h2 className="v3-panel__title">{title}</h2>
          {subtitle && <p className="v3-panel__subtitle">{subtitle}</p>}
        </div>
        {actions && <div className="v3-panel__actions">{actions}</div>}
      </header>
      <div className="v3-panel__body">{children}</div>
    </section>
  );
}

export interface V3StatProps {
  label: string;
  value: number | string;
  hint?: string;
  tone?: "neutral" | "good" | "warn" | "bad";
}

export function V3Stat({ label, value, hint, tone = "neutral" }: V3StatProps) {
  return (
    <div className="v3-stat" data-tone={tone}>
      <span className="v3-stat__label">{label}</span>
      <strong className="v3-stat__value">{value}</strong>
      {hint && <span className="v3-stat__hint">{hint}</span>}
    </div>
  );
}
