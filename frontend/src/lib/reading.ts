export type ReadingTheme = "paper" | "graphite";

export interface ReadingPrefs {
  fontSize: number;
  lineLength: number;
  leading: number;
  theme: ReadingTheme;
  measure: boolean;
}

export const DEFAULT_READING_PREFS: ReadingPrefs = {
  fontSize: 19,
  lineLength: 68,
  leading: 1.75,
  theme: "paper",
  measure: true,
};

export const MIN_READING_FONT_SIZE = 14;
export const MAX_READING_FONT_SIZE = 28;
export const MIN_READING_LINE_LENGTH = 40;
export const MAX_READING_LINE_LENGTH = 90;
export const MIN_READING_LEADING = 1.4;
export const MAX_READING_LEADING = 2.2;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function normalizeReadingPrefs(
  input: Partial<ReadingPrefs> | null | undefined,
): ReadingPrefs {
  const source = input ?? {};
  const fontSize =
    typeof source.fontSize === "number"
      ? source.fontSize
      : DEFAULT_READING_PREFS.fontSize;
  const lineLength =
    typeof source.lineLength === "number"
      ? source.lineLength
      : DEFAULT_READING_PREFS.lineLength;
  const leading =
    typeof source.leading === "number"
      ? source.leading
      : DEFAULT_READING_PREFS.leading;
  return {
    fontSize: clamp(
      Math.round(fontSize),
      MIN_READING_FONT_SIZE,
      MAX_READING_FONT_SIZE,
    ),
    lineLength: clamp(
      Math.round(lineLength),
      MIN_READING_LINE_LENGTH,
      MAX_READING_LINE_LENGTH,
    ),
    leading: clamp(leading, MIN_READING_LEADING, MAX_READING_LEADING),
    theme: source.theme === "graphite" ? "graphite" : "paper",
    measure: source.measure ?? DEFAULT_READING_PREFS.measure,
  };
}

export interface ReadingStats {
  words: number;
  characters: number;
  sentences: number;
  paragraphs: number;
  headings: number;
  readingSeconds: number;
}

export function readingStats(
  markdown: string,
  wordsPerMinute = 200,
): ReadingStats {
  const prose = markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`[^`]*`/g, " ")
    .replace(/[#*_~`]/g, " ");
  const words = prose.split(/\s+/).filter((word) => word.length > 0).length;
  const characters = prose.replace(/\s+/g, "").length;
  const sentences = markdown.match(/[.!?]+(\s|$)/g) ?? [];
  const paragraphs = markdown
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter((block) => block.length > 0 && !block.startsWith("#")).length;
  const headings = (markdown.match(/^#{1,6}\s+.*$/gm) ?? []).length;
  const readingSeconds = Math.max(
    1,
    Math.ceil((words / Math.max(1, wordsPerMinute)) * 60),
  );
  return {
    words,
    characters,
    sentences: sentences.length,
    paragraphs,
    headings,
    readingSeconds,
  };
}

export interface ReadingAnchor {
  id: string;
  level: number;
  text: string;
  line: number;
}

export function buildReadingOutline(
  markdown: string,
  source = "note",
): ReadingAnchor[] {
  const lines = markdown.split("\n");
  const anchors: ReadingAnchor[] = [];
  lines.forEach((line, index) => {
    const match = /^(#{1,6})\s+(.+)$/.exec(line);
    if (!match) return;
    anchors.push({
      id: `${source}-h${index + 1}`,
      level: match[1]!.length,
      text: (match[2] ?? "").trim(),
      line: index + 1,
    });
  });
  return anchors;
}

export function readingExcerpt(markdown: string, maxWords = 40): string {
  const prose = markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`[^`]*`/g, " ")
    .replace(/[#*_~`]/g, " ");
  const words = prose.split(/\s+/).filter((word) => word.length > 0);
  if (words.length === 0) return "";
  if (words.length <= maxWords) return words.join(" ");
  const kept = words.slice(0, Math.max(1, maxWords - 1)).join(" ");
  return `${kept}…`;
}
