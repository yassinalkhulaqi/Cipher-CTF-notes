export interface OutlineItem {
  line: number;
  level: number;
  text: string;
}

export function extractOutline(markdown: string): OutlineItem[] {
  const items: OutlineItem[] = [];
  const lines = markdown.split("\n");
  let fence: string | null = null;

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const fenceMatch = /^\s*(`{3,}|~{3,})/.exec(line);
    if (fenceMatch) {
      const marker = fenceMatch[1]?.[0] ?? "`";
      if (fence === null) fence = marker;
      else if (fence === marker) fence = null;
      continue;
    }
    if (fence !== null) continue;

    const heading = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if (!heading) continue;
    const text = (heading[2] ?? "").replace(/[*_`~[\]]/g, "").trim();
    if (!text) continue;
    items.push({ line: index + 1, level: heading[1]?.length ?? 1, text });
    if (items.length >= 200) break;
  }

  return items;
}
