export interface MdToken {
  text: string;
  kind:
    | "text"
    | "syntax"
    | "heading"
    | "quote"
    | "code"
    | "link"
    | "code-inline"
    | "strong"
    | "em"
    | "strike"
    | "check";
}

export interface MdLine {
  tokens: MdToken[];
}

const INLINE =
  /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|~~[^~\n]+~~|\[[^\]\n]+\]\([^)\n]+\)|https?:\/\/[^\s)]+|\*[^*\n]+\*|_[^_\n]+_)/g;

function classify(token: string): MdToken["kind"] {
  if (token.startsWith("`")) return "code-inline";
  if (token.startsWith("**") || token.startsWith("__")) return "strong";
  if (token.startsWith("~~")) return "strike";
  if (token.startsWith("[")) return "link";
  if (token.startsWith("http")) return "link";
  return "em";
}

function inline(text: string, tokens: MdToken[]): void {
  if (!text) return;
  let last = 0;
  INLINE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = INLINE.exec(text)) !== null) {
    if (match.index > last) {
      tokens.push({ text: text.slice(last, match.index), kind: "text" });
    }
    tokens.push({ text: match[0], kind: classify(match[0]) });
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    tokens.push({ text: text.slice(last), kind: "text" });
  }
}

export function highlightMarkdown(source: string): MdLine[] {
  const lines = source.split("\n");
  let fence: string | null = null;
  return lines.map((line) => {
    const tokens: MdToken[] = [];
    const fenceMatch = /^(\s*)(`{3,}|~{3,})(.*)$/.exec(line);
    if (fenceMatch) {
      const marker = fenceMatch[2] ?? "```";
      if (fence === null) fence = marker[0] ?? "`";
      else if (marker.startsWith(fence)) fence = null;
      tokens.push({ text: fenceMatch[1] ?? "", kind: "text" });
      tokens.push({ text: marker, kind: "syntax" });
      if (fenceMatch[3]) tokens.push({ text: fenceMatch[3], kind: "code" });
      return { tokens };
    }
    if (fence !== null) {
      if (line) tokens.push({ text: line, kind: "code" });
      return { tokens };
    }
    if (!line) return { tokens };

    const heading = /^(#{1,6})(\s+)(.*)$/.exec(line);
    if (heading) {
      tokens.push({ text: heading[1] ?? "", kind: "syntax" });
      tokens.push({ text: heading[2] ?? " ", kind: "text" });
      inline(heading[3] ?? "", tokens);
      return {
        tokens: tokens.map((token) =>
          token.kind === "text" ? { ...token, kind: "heading" as const } : token,
        ),
      };
    }

    const quote = /^(\s*>+\s?)(.*)$/.exec(line);
    if (quote) {
      tokens.push({ text: quote[1] ?? ">", kind: "syntax" });
      const inner: MdToken[] = [];
      inline(quote[2] ?? "", inner);
      tokens.push(
        ...inner.map((token) =>
          token.kind === "text" ? { ...token, kind: "quote" as const } : token,
        ),
      );
      return { tokens };
    }

    const list =
      /^(\s*)([-+*]|\d{1,9}[.)])(\s+)(\[[ xX]\]\s+)?(.*)$/.exec(line);
    if (list) {
      tokens.push({ text: list[1] ?? "", kind: "text" });
      tokens.push({ text: list[2] ?? "-", kind: "syntax" });
      tokens.push({ text: list[3] ?? " ", kind: "text" });
      if (list[4]) tokens.push({ text: list[4], kind: "check" });
      inline(list[5] ?? "", tokens);
      return { tokens };
    }

    if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
      tokens.push({ text: line, kind: "syntax" });
      return { tokens };
    }

    inline(line, tokens);
    return { tokens };
  });
}
