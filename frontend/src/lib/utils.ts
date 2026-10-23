export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function debounce<Args extends unknown[]>(
  fn: (...args: Args) => void,
  wait: number,
): ((...args: Args) => void) & { cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const wrapped = (...args: Args) => {
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...args);
    }, wait);
  };
  wrapped.cancel = () => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };
  return wrapped;
}

export function plural(count: number, singular: string, pluralForm?: string): string {
  return `${count.toLocaleString()} ${count === 1 ? singular : (pluralForm ?? `${singular}s`)}`;
}

export function wordCount(text: string): number {
  const trimmed = text.trim();
  return trimmed ? (trimmed.match(/\S+/g)?.length ?? 0) : 0;
}

export function isMac(): boolean {
  return navigator.platform.toLowerCase().includes("mac");
}

export function modLabel(): string {
  return isMac() ? "Cmd" : "Ctrl";
}

export function formatDate(value: string, withTime = false): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function relativeTime(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diff = Date.now() - date.getTime();
  const minutes = Math.round(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(value);
}

export function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] ??
      character,
  );
}

export function uid(prefix = "id"): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}

export function downloadText(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 500);
}

export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

export function highlightMarkers(snippet: string): { text: string; match: boolean } {
  const open = snippet.indexOf("[");
  const close = open >= 0 ? snippet.indexOf("]", open + 1) : -1;
  if (open < 0 || close < 0) return { text: snippet, match: false };
  return {
    text: `${snippet.slice(0, open)}${snippet.slice(open + 1, close)}${snippet.slice(close + 1)}`,
    match: true,
  };
}
