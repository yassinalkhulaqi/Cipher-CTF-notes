import { BLOCK_TYPES, type BlockType, type SlashCommand } from "./types";

const DESCRIPTIONS: Record<BlockType, string> = {
  paragraph: "Plain text paragraph",
  heading: "Section heading with levels 1-6",
  code: "Fenced code block with a language tag",
  quote: "Quoted passage",
  list: "Bulleted, ordered, or task list",
  table: "Structured table with headers and rows",
  callout: "Highlighted note, tip, warning, or danger",
  divider: "Horizontal rule between sections",
  image: "Image placeholder with alt text",
};

const KEYWORDS: Record<BlockType, string[]> = {
  paragraph: ["text", "plain", "body"],
  heading: ["h1", "title", "section", "h2"],
  code: ["snippet", "fence", "shell", "script"],
  quote: ["blockquote", "citation"],
  list: ["bullet", "ordered", "task", "todo", "checkbox"],
  table: ["grid", "columns", "rows"],
  callout: ["note", "warning", "tip", "danger", "admonition"],
  divider: ["rule", "hr", "separator"],
  image: ["picture", "photo", "alt", "placeholder"],
};

const TITLES: Record<BlockType, string> = {
  paragraph: "Text",
  heading: "Heading",
  code: "Code",
  quote: "Quote",
  list: "List",
  table: "Table",
  callout: "Callout",
  divider: "Divider",
  image: "Image",
};

export const SLASH_COMMANDS: SlashCommand[] = BLOCK_TYPES.map((blockType) => ({
  id: blockType,
  title: TITLES[blockType],
  description: DESCRIPTIONS[blockType],
  blockType,
  keywords: [blockType, ...KEYWORDS[blockType]],
  group:
    blockType === "heading" || blockType === "divider"
      ? "Structure"
      : "Content",
}));

function rank(command: SlashCommand, query: string): number {
  const needle = query.trim().toLowerCase();
  if (!needle) return 1;
  const title = command.title.toLowerCase();
  if (title === needle) return 100;
  if (title.startsWith(needle)) return 80;
  if (command.blockType === needle) return 75;
  if (title.includes(needle)) return 60;
  if (command.keywords.some((keyword) => keyword.startsWith(needle))) return 50;
  if (command.keywords.some((keyword) => keyword.includes(needle))) return 40;
  if (command.description.toLowerCase().includes(needle)) return 20;
  return 0;
}

export function filterSlashCommands(query: string, limit = 9): SlashCommand[] {
  const ranked = SLASH_COMMANDS.map((command) => ({
    command,
    score: rank(command, query),
  }))
    .filter((entry) => entry.score > 0)
    .sort(
      (left, right) =>
        right.score - left.score ||
        left.command.title.localeCompare(right.command.title),
    );
  return ranked.slice(0, Math.max(0, limit)).map((entry) => entry.command);
}

export function slashCommand(blockType: BlockType): SlashCommand | null {
  return (
    SLASH_COMMANDS.find((command) => command.blockType === blockType) ?? null
  );
}

export function slashCommandById(id: string): SlashCommand | null {
  return SLASH_COMMANDS.find((command) => command.id === id) ?? null;
}

export function groupedSlashCommands(
  query: string,
): Array<[string, SlashCommand[]]> {
  const groups = new Map<string, SlashCommand[]>();
  for (const command of filterSlashCommands(query)) {
    const entries = groups.get(command.group) ?? [];
    entries.push(command);
    groups.set(command.group, entries);
  }
  return Array.from(groups.entries());
}

export function slashCommandTitles(query: string): string[] {
  return filterSlashCommands(query).map((command) => command.title);
}

export function isSlashTrigger(value: string, caret = value.length): boolean {
  const before = value.slice(0, caret);
  return /(?:^|\s)\/[^\s/]*$/.test(before);
}

export function commandDescription(blockType: BlockType): string {
  return DESCRIPTIONS[blockType];
}
