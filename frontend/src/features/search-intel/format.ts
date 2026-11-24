/** Formatting helpers for search intelligence views. */

export function formatCount(value: number): string {
  if (value < 1000) return String(value);
  return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)}k`;
}

export function formatScore(value: number): string {
  return value.toFixed(1);
}

export function kindLabel(kind: string): string {
  return kind
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function relativeTime(timestamp: number, now = Date.now()): string {
  if (!timestamp) return "unknown";
  const seconds = Math.max(0, Math.floor(now / 1000 - timestamp));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function severityTone(severity: string): string {
  if (severity === "critical") return "bad";
  if (severity === "warning" || severity === "notice") return "warn";
  if (severity === "info") return "info";
  return "neutral";
}
