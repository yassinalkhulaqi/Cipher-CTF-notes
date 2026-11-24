/** UTC recurrence expansion and human-readable rule descriptions. */

import type { Frequency, RecurrenceRule, ValidationIssue } from "./types";
import { WEEKDAY_LABELS, issue } from "./types";

export const DEFAULT_RULE: RecurrenceRule = {
  frequency: "daily",
  interval: 1,
  by_weekday: [],
  by_month_day: null,
  hour: 9,
  minute: 0,
  start_at: 0,
  end_at: 0,
  count: 0,
};

const DAY_MS = 86_400_000;
const HOUR_MS = 3_600_000;

export function validateRule(rule: RecurrenceRule): ValidationIssue[] {
  const problems: ValidationIssue[] = [];
  if (rule.interval < 1) problems.push(issue("invalid_interval", "Interval must be at least 1", "recurrence.interval"));
  if (rule.hour < 0 || rule.hour > 23 || rule.minute < 0 || rule.minute > 59) {
    problems.push(issue("invalid_time", "Time must be a valid UTC hour and minute", "recurrence.hour"));
  }
  if ((rule.by_weekday ?? []).some((day) => day < 0 || day > 6)) {
    problems.push(issue("invalid_weekday", "Weekdays must be 0 (Mon) .. 6 (Sun)", "recurrence.by_weekday"));
  }
  if (rule.frequency !== "monthly" && rule.by_month_day) {
    problems.push(issue("ignored_field", "Month day only applies to monthly rules", "recurrence.by_month_day", "warning"));
  }
  if (rule.end_at && rule.end_at <= (rule.start_at ?? 0)) {
    problems.push(issue("invalid_window", "End must follow the start", "recurrence.end_at"));
  }
  return problems;
}

function withTime(moment: Date, rule: RecurrenceRule): number {
  return Date.UTC(
    moment.getUTCFullYear(),
    moment.getUTCMonth(),
    moment.getUTCDate(),
    rule.hour,
    rule.minute,
    0,
    0,
  );
}

function firstCandidate(rule: RecurrenceRule, lower: number): number {
  const moment = new Date(lower);
  if (rule.frequency === "hourly") {
    let candidate = Date.UTC(
      moment.getUTCFullYear(), moment.getUTCMonth(), moment.getUTCDate(), moment.getUTCHours(), rule.minute,
    );
    while (candidate < lower) candidate += rule.interval * HOUR_MS;
    return candidate;
  }
  if (rule.frequency === "daily") {
    let candidate = withTime(moment, rule);
    while (candidate < lower) candidate += rule.interval * DAY_MS;
    return candidate;
  }
  if (rule.frequency === "weekly") {
    const days = (rule.by_weekday?.length ? rule.by_weekday : [moment.getUTCDay()]).slice().sort();
    const monday = new Date(Date.UTC(moment.getUTCFullYear(), moment.getUTCMonth(), moment.getUTCDate()));
    monday.setUTCDate(monday.getUTCDate() - ((monday.getUTCDay() + 6) % 7));
    for (let offset = 0; offset < 7; offset += 1) {
      const day = new Date(monday.getTime() + offset * DAY_MS);
      if (days.includes((day.getUTCDay() + 6) % 7)) {
        const candidate = withTime(day, rule);
        if (candidate >= lower) return candidate;
      }
    }
    return withTime(new Date(monday.getTime() + rule.interval * 7 * DAY_MS + days[0]! * DAY_MS), rule);
  }
  let candidate = monthlyCandidate(moment.getUTCFullYear(), moment.getUTCMonth(), rule, moment.getUTCDate());
  candidate = withTime(new Date(candidate), rule);
  while (candidate < lower) {
    const next = new Date(candidate);
    candidate = monthlyCandidate(next.getUTCFullYear(), next.getUTCMonth() + rule.interval, rule, moment.getUTCDate());
    candidate = withTime(new Date(candidate), rule);
  }
  return candidate;
}

function monthlyCandidate(year: number, monthIndex: number, rule: RecurrenceRule, seedDay: number): number {
  const normalized = new Date(Date.UTC(year, monthIndex, 1));
  const lastDay = new Date(Date.UTC(normalized.getUTCFullYear(), normalized.getUTCMonth() + 1, 0)).getUTCDate();
  const day = Math.min(rule.by_month_day || seedDay, lastDay);
  return Date.UTC(normalized.getUTCFullYear(), normalized.getUTCMonth(), day);
}

function advance(rule: RecurrenceRule, moment: number, seedDay: number): number {
  if (rule.frequency === "hourly") return moment + rule.interval * HOUR_MS;
  const date = new Date(moment);
  if (rule.frequency === "daily") return withTime(new Date(moment + rule.interval * DAY_MS), rule);
  if (rule.frequency === "weekly") {
    const days = (rule.by_weekday?.length ? rule.by_weekday : [(date.getUTCDay() + 6) % 7]).slice().sort();
    const weekday = (date.getUTCDay() + 6) % 7;
    const index = days.indexOf(weekday);
    if (index >= 0 && index + 1 < days.length) {
      return withTime(new Date(moment + (days[index + 1]! - weekday) * DAY_MS), rule);
    }
    return withTime(new Date(moment + rule.interval * 7 * DAY_MS + days[0]! * DAY_MS - weekday * DAY_MS), rule);
  }
  const next = monthlyCandidate(date.getUTCFullYear(), date.getUTCMonth() + rule.interval, rule, seedDay);
  return withTime(new Date(next), rule);
}

export function expand(rule: RecurrenceRule, after: number, before: number, limit = 20): number[] {
  if (limit <= 0 || before <= after) return [];
  const lower = Math.max(after, rule.start_at ?? 0);
  const upper = rule.end_at ? Math.min(before, rule.end_at + 1) : before;
  if (upper <= lower) return [];
  const seedDay = new Date(lower).getUTCDate();
  let moment = firstCandidate(rule, lower);
  const results: number[] = [];
  for (let guard = 0; guard < 20_000; guard += 1) {
    if (moment >= upper) break;
    if (moment > after) {
      if (rule.count && results.length >= rule.count) break;
      results.push(moment);
      if (results.length >= limit) break;
    }
    moment = advance(rule, moment, seedDay);
  }
  return results;
}

export function nextOccurrence(rule: RecurrenceRule, after: number): number | null {
  const horizon = after + 370 * DAY_MS * (Math.max(1, rule.interval) + 1);
  return expand(rule, after, horizon, 1)[0] ?? null;
}

export function humanize(rule: RecurrenceRule): string {
  const interval = rule.interval === 1 ? "" : ` every ${rule.interval}`;
  const frequency = rule.frequency as Frequency;
  let text: string;
  if (frequency === "hourly") text = `Hourly${interval}`;
  else if (frequency === "daily") text = `Daily${interval}`;
  else if (frequency === "weekly") {
    const days = (rule.by_weekday ?? []).map((day) => WEEKDAY_LABELS[day]).filter(Boolean).join(",");
    text = `Weekly${interval}${days ? ` on ${days}` : ""}`;
  } else {
    text = `Monthly${interval}${rule.by_month_day ? ` on day ${rule.by_month_day}` : ""}`;
  }
  return `${text} at ${String(rule.hour).padStart(2, "0")}:${String(rule.minute).padStart(2, "0")} UTC`;
}

export function formatOccurrence(timestamp: number): string {
  return new Date(timestamp).toISOString().slice(0, 16).replace("T", " ") + " UTC";
}
