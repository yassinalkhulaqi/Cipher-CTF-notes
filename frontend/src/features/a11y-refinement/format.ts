/** Locale-aware formatting helpers shared by the refined surfaces. */

import { languageOf, localeDirection, normalizeLocale } from "./catalogs";
import type { FormatResultView } from "./types";

const DIGIT_MAPS: Record<string, string[]> = {
  ar: "٠١٢٣٤٥٦٧٨٩".split(""),
  fa: "۰۱۲۳۴۵۶۷۸۹".split(""),
  ur: "۰۱۲۳۴۵۶۷۸۹".split(""),
};

function separators(locale: string): { group: string; decimal: string } {
  const language = languageOf(locale);
  if (language === "de" || language === "fr" || language === "it" || language === "nl" || language === "pt" || language === "fa") {
    return { group: language === "de" ? "." : language === "fa" ? "٬" : " ", decimal: language === "fa" ? "٫" : "," };
  }
  return { group: ",", decimal: "." };
}

export function localizeDigits(text: string, locale: string): string {
  const digits = DIGIT_MAPS[languageOf(locale)];
  if (!digits) return text;
  return text.replace(/\d/g, (char) => digits[Number(char)]);
}

export function formatNumber(value: number, locale: string, digits = 0): string {
  const settings = separators(normalizeLocale(locale));
  const fixed = value.toFixed(digits);
  const [integer, fraction] = fixed.split(".");
  const chunks: string[] = [];
  let head = integer.replace("-", "");
  while (head.length > 3) {
    chunks.unshift(head.slice(-3));
    head = head.slice(0, -3);
  }
  chunks.unshift(head);
  const sign = integer.startsWith("-") ? "−" : "";
  const body = chunks.join(settings.group) + (fraction ? settings.decimal + fraction : "");
  return localizeDigits(sign + body, locale);
}

export function parseNumber(text: string, locale: string): number {
  const normalized = normalizeLocale(locale);
  const settings = separators(normalized);
  const digits = DIGIT_MAPS[languageOf(normalized)];
  let plain = text.trim().replace(/−/g, "-");
  if (digits) plain = plain.replace(/[^\d\-.,\s]/g, (char) => {
    const index = digits.indexOf(char);
    return index >= 0 ? String(index) : char;
  });
  plain = plain.split(settings.group).join("").replace(settings.decimal, ".");
  return Number.parseFloat(plain);
}

export function roundTrip(value: number, locale: string, digits = 2): { formatted: string; parsed: number; exact: boolean } {
  const formatted = formatNumber(value, locale, digits);
  const parsed = parseNumber(formatted, locale);
  return { formatted, parsed, exact: Math.abs(parsed - value) < 1e-9 };
}

export function formatDate(iso: string, locale: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso.trim());
  if (!match) return iso;
  const [, year, month, day] = match;
  const normalized = languageOf(locale);
  if (normalized === "en") return `${year}-${month}-${day}`;
  if (normalized === "ja" || normalized === "ko" || normalized === "zh") return `${year}/${month}/${day}`;
  return `${day}/${month}/${year}`;
}

export function formatBytes(bytes: number, locale: string, binary = false): string {
  const base = binary ? 1024 : 1000;
  const units = binary ? ["B", "KiB", "MiB", "GiB"] : ["B", "KB", "MB", "GB"];
  let amount = bytes;
  let index = 0;
  while (Math.abs(amount) >= base && index < units.length - 1) {
    amount /= base;
    index += 1;
  }
  return `${formatNumber(amount, locale, index === 0 ? 0 : 1)} ${units[index]}`;
}

export function pluralText(count: number, singular: string, plural: string, locale: string): string {
  const language = languageOf(locale);
  const form =
    language === "ja" || language === "ko" || language === "zh" || count !== 1 ? plural : singular;
  return `${formatNumber(count, locale)} ${form}`;
}

export function isolateBidi(text: string, locale: string): string {
  return localeDirection(locale) === "rtl" ? `\u2068${text}\u2069` : text;
}

export function formatValue(kind: string, value: unknown, locale: string): FormatResultView {
  const direction = localeDirection(locale);
  let text: string;
  if (kind === "number") {
    text = formatNumber(Number(value ?? 0), locale);
  } else if (kind === "bytes") {
    text = formatBytes(Number(value ?? 0), locale);
  } else if (kind === "date") {
    text = formatDate(String(value ?? ""), locale);
  } else if (kind === "percent") {
    text = `${formatNumber(Number(value ?? 0) * 100, locale, 1)}%`;
  } else if (kind === "currency") {
    text = `${languageOf(locale) === "de" || languageOf(locale) === "fr" ? "" : "$"}${formatNumber(Number(value ?? 0), locale, 2)}`;
  } else {
    text = String(value ?? "");
  }
  return {
    locale: normalizeLocale(locale),
    kind,
    text,
    direction: direction === "rtl" ? "rtl" : "ltr",
    bidi_isolated: direction === "rtl",
    fallback: "",
  };
}

export function formatAuditMessage(
  template: string,
  params: Record<string, string | number>,
  locale: string,
): string {
  const rendered = template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
  return isolateBidi(rendered, locale);
}

export function localeFormatOptions(locale: string): { locale: string; decimal: string; group: string; rtl: boolean } {
  const settings = separators(normalizeLocale(locale));
  return { locale: normalizeLocale(locale), ...settings, rtl: localeDirection(locale) === "rtl" };
}
