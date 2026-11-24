/** Additional locale catalogs used by the refined V3 surfaces. */

import type { Direction, LocaleOptionView } from "./types";

export interface CatalogEntry {
  locale: string;
  messages: Record<string, string>;
}

const BASE: Record<string, string> = {
  "v3.audit.passed": "Audit passed for {surface}",
  "v3.audit.findings": "{count} findings on {surface}",
  "v3.contrast.score": "Contrast score {score} percent",
  "v3.keyboard.binding": "{action}: {binding}",
  "v3.layout.direction": "Layout direction {direction}",
  "v3.finding.severity": "Finding severity {severity}",
  "v3.evidence.integrity": "Evidence integrity {status}",
  "v3.report.generated": "Report generated at {time}",
  "v3.prefs.synced": "Preferences synchronized to revision {revision}",
  "v3.command.run": "Running command {name}",
  "v3.search.results": "{count} results",
  "v3.theme.changed": "Theme changed to {theme}",
  "v3.motion.reduced": "Reduced motion enabled",
  "v3.shortcut.help": "Press {key} for keyboard help",
};

export const V3_CATALOGS: CatalogEntry[] = [
  {
    locale: "pt-BR",
    messages: {
      "v3.audit.passed": "Auditoria aprovada para {surface}",
      "v3.audit.findings": "{count} problemas em {surface}",
      "v3.contrast.score": "Pontuação de contraste {score} por cento",
      "v3.keyboard.binding": "{action}: {binding}",
      "v3.report.generated": "Relatório gerado às {time}",
      "v3.search.results": "{count} resultados",
      "v3.theme.changed": "Tema alterado para {theme}",
    },
  },
  {
    locale: "it",
    messages: {
      "v3.audit.passed": "Controllo superato per {surface}",
      "v3.audit.findings": "{count} problemi in {surface}",
      "v3.contrast.score": "Punteggio di contrasto {score} percento",
      "v3.keyboard.binding": "{action}: {binding}",
      "v3.report.generated": "Report generato alle {time}",
      "v3.search.results": "{count} risultati",
      "v3.theme.changed": "Tema cambiato in {theme}",
    },
  },
  {
    locale: "nl",
    messages: {
      "v3.audit.passed": "Audit geslaagd voor {surface}",
      "v3.audit.findings": "{count} bevindingen op {surface}",
      "v3.contrast.score": "Contrastscore {score} procent",
      "v3.keyboard.binding": "{action}: {binding}",
      "v3.report.generated": "Rapport gegenereerd om {time}",
      "v3.search.results": "{count} resultaten",
      "v3.theme.changed": "Thema gewijzigd naar {theme}",
    },
  },
  {
    locale: "ko",
    messages: {
      "v3.audit.passed": "{surface} 감사 통과",
      "v3.audit.findings": "{surface}에서 {count}건 발견",
      "v3.contrast.score": "대비 점수 {score}퍼센트",
      "v3.keyboard.binding": "{action}: {binding}",
      "v3.report.generated": "{time}에 보고서 생성",
      "v3.search.results": "결과 {count}건",
      "v3.theme.changed": "테마를 {theme}(으)로 변경",
    },
  },
  {
    locale: "fa",
    messages: {
      "v3.audit.passed": "بررسی با موفقیت برای {surface} انجام شد",
      "v3.audit.findings": "{count} یافته در {surface}",
      "v3.contrast.score": "امتیاز تضاد {score} درصد",
      "v3.keyboard.binding": "{binding} : {action}",
      "v3.layout.direction": "جهت طرحبندی {direction}",
      "v3.report.generated": "گزارش در {time} ایجاد شد",
      "v3.search.results": "{count} نتیجه",
      "v3.theme.changed": "تغییر تم به {theme}",
    },
  },
  {
    locale: "ur",
    messages: {
      "v3.audit.passed": "{surface} کے لیے آڈٹ کامیاب",
      "v3.audit.findings": "{surface} میں {count} نتائج",
      "v3.contrast.score": "کنٹراسٹ اسکور {score} فیصد",
      "v3.keyboard.binding": "{action}: {binding}",
      "v3.layout.direction": "ترتیب کی سمت {direction}",
      "v3.report.generated": "رپورٹ {time} پر تیار ہوئی",
      "v3.search.results": "{count} نتائج",
      "v3.theme.changed": "تھیم {theme} میں تبدیل",
    },
  },
];

const RTL_LANGUAGES = new Set(["ar", "he", "fa", "ur", "ps", "yi"]);

export function normalizeLocale(locale: string): string {
  const parts = locale.trim().replace(/_/g, "-").split("-");
  if (!parts[0]) return "en";
  const language = parts[0].toLowerCase();
  const tail = parts.slice(1).map((part) =>
    part.length === 2 ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1),
  );
  return [language, ...tail].join("-");
}

export function languageOf(locale: string): string {
  return normalizeLocale(locale).split("-")[0];
}

export function localeDirection(locale: string): Direction {
  return RTL_LANGUAGES.has(languageOf(locale)) ? "rtl" : "ltr";
}

export function resolvedDirection(locale: string, override?: Direction): "ltr" | "rtl" {
  if (override === "ltr" || override === "rtl") return override;
  return localeDirection(locale) === "rtl" ? "rtl" : "ltr";
}

export function catalogKeys(): string[] {
  return Object.keys(BASE).sort();
}

export function catalogFor(locale: string): Record<string, string> {
  const normalized = normalizeLocale(locale);
  const extra = V3_CATALOGS.find((entry) => entry.locale === normalized);
  return { ...BASE, ...(extra?.messages ?? {}) };
}

export function translate(
  locale: string,
  key: string,
  params: Record<string, string | number> = {},
): { message: string; missing: boolean; used: string } {
  const normalized = normalizeLocale(locale);
  const language = languageOf(normalized);
  const candidates = [normalized, language, ...V3_CATALOGS.filter((entry) => languageOf(entry.locale) === language).map((entry) => entry.locale), "en"];
  for (const candidate of candidates) {
    const catalog = catalogFor(candidate);
    const template = catalog[key];
    if (template !== undefined) {
      return {
        message: interpolate(template, params),
        missing: false,
        used: candidate,
      };
    }
  }
  return { message: key, missing: true, used: "" };
}

export function interpolate(template: string, params: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match,
  );
}

export function coverage(locale: string): number {
  const keys = catalogKeys();
  const normalized = normalizeLocale(locale);
  const catalog =
    normalized === "en"
      ? BASE
      : (V3_CATALOGS.find((entry) => entry.locale === normalized)?.messages ?? {});
  return Math.round((keys.filter((key) => key in catalog).length / keys.length) * 1000) / 10;
}

export function additionalLocaleOptions(): LocaleOptionView[] {
  return [
    { value: "pt-BR", label: "Portuguese (Brazil)", native_name: "Português (Brasil)", direction: "ltr", script: "Latn" },
    { value: "it", label: "Italian", native_name: "Italiano", direction: "ltr", script: "Latn" },
    { value: "nl", label: "Dutch", native_name: "Nederlands", direction: "ltr", script: "Latn" },
    { value: "ko", label: "Korean", native_name: "한국어", direction: "ltr", script: "Hang" },
    { value: "fa", label: "Persian", native_name: "فارسی", direction: "rtl", script: "Arab" },
    { value: "ur", label: "Urdu", native_name: "اردو", direction: "rtl", script: "Arab" },
  ];
}
