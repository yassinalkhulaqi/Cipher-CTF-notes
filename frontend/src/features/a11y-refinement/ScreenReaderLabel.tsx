/** Screen-reader label helpers for every refined V3 control. */

import type { ReactNode } from "react";

import { translate } from "./catalogs";

export interface ScreenReaderLabelProps {
  text: string;
  id?: string;
}

export function ScreenReaderLabel({ text, id }: ScreenReaderLabelProps) {
  return (
    <span className="a11y-refine__sr-only" data-a11y-sr-label="true" id={id}>
      {text}
    </span>
  );
}

export function labelledBy(id: string, extra?: string): { "aria-labelledby": string } {
  return { "aria-labelledby": extra ? `${id} ${extra}` : id };
}

export function describedBy(id: string): { "aria-describedby": string } {
  return { "aria-describedby": id };
}

export function controlLabel(label: string, hint?: string): ReactNode {
  return (
    <>
      <span className="a11y-refine__control-label">{label}</span>
      {hint && <ScreenReaderLabel text={hint} />}
    </>
  );
}

export function announcementFor(
  score: number,
  findings: number,
  locale: string,
): string {
  const template = findings === 0 ? translate(locale, "v3.audit.passed", { surface: "v3" }) : translate(locale, "v3.audit.findings", { count: findings, surface: "v3" });
  return `${template.message} · ${translate(locale, "v3.contrast.score", { score: Math.round(score) }).message}`;
}

export function actionLabel(action: string, locale = "en"): string {
  const translated = translate(locale, "v3.command.run", { name: action.replaceAll("_", " ") });
  return translated.missing ? action : translated.message;
}

export function liveRegionProps(polite = true): {
  "aria-live": "polite" | "assertive";
  "aria-atomic": "true";
} {
  return { "aria-live": polite ? "polite" : "assertive", "aria-atomic": "true" };
}
