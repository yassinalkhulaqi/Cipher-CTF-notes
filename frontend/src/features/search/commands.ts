import { foldText } from "./query";
import type {
  CommandArgumentSuggestion,
  CommandCompletion,
  ParsedCommand,
  SavedQuery,
} from "./types";

export const COMMAND_NAMES = [
  "search",
  "find",
  "goto",
  "open",
  "tag",
  "untag",
  "bookmark",
  "pin",
  "saved",
  "filter",
  "sort",
  "reindex",
] as const;

const DESCRIPTIONS: Record<string, string> = {
  search: "Search every note with full-text ranking.",
  find: "Find notes containing the supplied text.",
  goto: "Jump to a note id or title.",
  open: "Open the best matching note.",
  tag: "Apply a tag to matching notes.",
  untag: "Remove a tag from matching notes.",
  bookmark: "Bookmark the selected note.",
  pin: "Pin the selected note to the top.",
  saved: "Run or manage a saved query.",
  filter: "Apply a filter to the current result set.",
  sort: "Change result ordering.",
  reindex: "Rebuild the search index.",
};

const OPTIONS = [
  "--limit",
  "--sort",
  "--group-by",
  "--facet",
  "--tag",
  "--pinned",
  "--exact",
] as const;

const EXAMPLES: Record<string, string[]> = {
  search: ["/search nmap ports", '/search "sql injection" tag:web'],
  find: ["/find credentials", "/find flag --facet=tag"],
  goto: ["/goto 42", "/goto 'Nmap notes'"],
  tag: ["/tag nmap recon", "/tag tag:web triaged"],
  saved: ["/saved weekly-review", "/saved list"],
  reindex: ["/reindex"],
};

export function commandDescription(name: string): string {
  return DESCRIPTIONS[name] ?? "Run a registered command.";
}

export function commandExamples(name: string): string[] {
  return EXAMPLES[name] ?? [`/ ${name}`];
}

interface ParsedArgument {
  name: string;
  value: string;
  position: number;
  quoted: boolean;
}

interface RawToken {
  text: string;
  start: number;
  end: number;
  quoted: boolean;
}

function parseTokens(text: string): RawToken[] {
  const tokens: RawToken[] = [];
  let index = 0;
  while (index < text.length) {
    while (index < text.length && /\s/.test(text[index])) index += 1;
    if (index >= text.length) break;
    const start = index;
    let value = "";
    let quoted = false;
    if (text[index] === '"' || text[index] === "'") {
      const quote = text[index];
      quoted = true;
      index += 1;
      while (index < text.length && text[index] !== quote) {
        if (text[index] === "\\" && index + 1 < text.length) index += 1;
        value += text[index];
        index += 1;
      }
      if (index < text.length) index += 1;
    } else {
      while (index < text.length && !/\s/.test(text[index])) {
        value += text[index];
        index += 1;
      }
    }
    tokens.push({ text: value, start, end: index, quoted });
  }
  return tokens;
}

export function canonicalCommandName(value: string): string {
  const normalized = value.trim().replace(/^\//, "").toLowerCase();
  if (normalized === "s") return "search";
  if (normalized === "f") return "find";
  if (normalized === "g") return "goto";
  if (normalized === "save") return "saved";
  return normalized;
}

export function parseCommand(text: string): ParsedCommand {
  const raw = text.trim();
  const tokens = parseTokens(raw);
  const first = tokens[0];
  const name = first ? canonicalCommandName(first.text) : "";
  const issues: ParsedCommand["issues"] = [];
  if (!raw.startsWith("/")) {
    issues.push({
      code: "command_prefix",
      message: "Commands start with /",
      position: 0,
    });
  }
  if (!name) {
    issues.push({
      code: "command_name",
      message: "Command name is required",
      position: 0,
    });
  } else if (!(COMMAND_NAMES as readonly string[]).includes(name)) {
    issues.push({
      code: "unknown_command",
      message: `Unknown command: ${name}`,
      position: first.start,
    });
  }
  const arguments_: ParsedArgument[] = [];
  const options: Record<string, string> = {};
  for (const token of tokens.slice(1)) {
    if (token.text.startsWith("--")) {
      const option = token.text.slice(2);
      const separator = option.indexOf("=");
      if (separator >= 0) {
        options[option.slice(0, separator)] = option.slice(separator + 1);
      } else {
        options[option] = "true";
      }
      continue;
    }
    arguments_.push({
      name: `arg${arguments_.length + 1}`,
      value: token.text,
      position: token.start,
      quoted: token.quoted,
    });
  }
  const limit = Number(options.limit);
  if (
    options.limit !== undefined &&
    (!Number.isFinite(limit) || limit < 1 || limit > 200)
  ) {
    issues.push({
      code: "invalid_limit",
      message: "Limit must be between 1 and 200",
      position: 0,
    });
  }
  const query = arguments_.map((argument) => argument.value).join(" ");
  const plan = {
    name: name || "unknown",
    action: name === "find" ? "search" : name,
    query,
    filters: Object.entries(options)
      .filter(([key]) => key === "tag" || key === "facet")
      .map(([key, value]) => `${key}:${value}`),
    target: arguments_[0]?.value ?? "",
    message: commandDescription(name),
    metadata: { options: { ...options }, arguments: arguments_.length },
  };
  return {
    raw,
    ok: issues.length === 0,
    node: {
      name,
      arguments: arguments_,
      options,
      raw,
      leading: raw.startsWith("/") ? "/" : "",
      text: raw.replace(/^\//, ""),
    },
    issues,
    tokens: tokens.map((token) => ({
      ...token,
      kind: token.text.startsWith("--") ? "option" : "argument",
    })),
    plan,
  };
}

function suggestion(
  label: string,
  kind: CommandArgumentSuggestion["kind"],
  description: string,
  insertText: string,
  score: number,
  metadata: Record<string, unknown> = {},
): CommandArgumentSuggestion {
  return {
    label,
    value: insertText,
    kind,
    description,
    score,
    insert_text: insertText,
    start: 0,
    end: 0,
    metadata,
  };
}

export function commandSuggestions(
  text: string,
  saved: SavedQuery[] = [],
  limit = 10,
): CommandArgumentSuggestion[] {
  const parsed = parseCommand(text);
  const tokens = text.split(/\s+/);
  const current = tokens[tokens.length - 1] ?? "";
  const folded = foldText(current);
  if (tokens.length <= 1 || !current) {
    return COMMAND_NAMES.filter((name) =>
      name.startsWith(folded.replace(/^\//, "")),
    )
      .slice(0, limit)
      .map((name) =>
        suggestion(
          `/${name}`,
          "command",
          commandDescription(name),
          `/${name} `,
          100,
        ),
      );
  }
  if (current.startsWith("--")) {
    return OPTIONS.filter((option) => option.startsWith(folded))
      .slice(0, limit)
      .map((option) =>
        suggestion(option, "option", `Set ${option}`, `${option}=`, 80),
      );
  }
  if (parsed.node?.name === "saved") {
    return saved
      .filter((item) => foldText(item.name).includes(folded))
      .slice(0, limit)
      .map((item) =>
        suggestion(
          item.name,
          "saved",
          item.description || item.query,
          item.name,
          70,
          {
            id: item.id,
          },
        ),
      );
  }
  const examples = commandExamples(parsed.node?.name ?? "");
  return examples
    .filter((example) => foldText(example).includes(folded))
    .slice(0, limit)
    .map((example, index) =>
      suggestion(example, "example", "Example invocation", example, 60 - index),
    );
}

export function completeCommand(
  text: string,
  saved: SavedQuery[] = [],
): CommandCompletion {
  const cursor = text.length;
  const prefix = text.split(/\s+/).pop() ?? "";
  const context = prefix.startsWith("--")
    ? "option"
    : text.trim().split(/\s+/).length <= 1
      ? "command"
      : "argument";
  return {
    text,
    cursor,
    prefix,
    context,
    suggestions: commandSuggestions(text, saved),
  };
}

export function formatCommandIssue(
  issue: ParsedCommand["issues"][number],
): string {
  return `${issue.message} (${issue.code})`;
}

export function commandFromSaved(item: SavedQuery): string {
  return `/search ${item.query}`;
}

export function commandIsMutating(parsed: ParsedCommand): boolean {
  if (!parsed.ok) return false;
  const name = parsed.node?.name ?? "";
  return ["tag", "untag", "bookmark", "pin", "reindex"].includes(name);
}

export function commandNeedsConfirmation(parsed: ParsedCommand): boolean {
  return commandIsMutating(parsed);
}
