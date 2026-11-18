import { type KeyboardAction } from "./types";

export interface KeyInput {
  key: string;
  ctrlKey?: boolean;
  metaKey?: boolean;
  shiftKey?: boolean;
  altKey?: boolean;
  selectionStart?: number;
  selectionEnd?: number;
  value?: string;
  slashOpen?: boolean;
  mentionOpen?: boolean;
  menuCount?: number;
  activeIndex?: number;
}

function action(
  kind: KeyboardAction["kind"],
  payload?: string,
): KeyboardAction {
  return payload === undefined ? { kind } : { kind, payload };
}

export function normalizeKey(key: string): string {
  const lowered = key.toLowerCase();
  const aliases: Record<string, string> = {
    spacebar: " ",
    space: " ",
    del: "delete",
    esc: "escape",
    ins: "insert",
    up: "arrowup",
    down: "arrowdown",
    left: "arrowleft",
    right: "arrowright",
    return: "enter",
  };
  return aliases[lowered] ?? lowered;
}

export function shortcutLabel(input: KeyInput): string {
  const parts: string[] = [];
  if (input.ctrlKey) parts.push("Ctrl");
  if (input.metaKey) parts.push("Meta");
  if (input.altKey) parts.push("Alt");
  if (input.shiftKey) parts.push("Shift");
  parts.push(input.key.length === 1 ? input.key.toUpperCase() : input.key);
  return parts.join("+");
}

export function resolveKeyboardAction(input: KeyInput): KeyboardAction {
  const key = normalizeKey(input.key);
  const mod = Boolean(input.ctrlKey || input.metaKey);

  if (input.mentionOpen) {
    if (key === "arrowdown") return action("move-down");
    if (key === "arrowup") return action("move-up");
    if (key === "enter" || key === "tab") return action("accept-mention");
    if (key === "escape") return action("close-slash");
  }

  if (input.slashOpen) {
    if (key === "arrowdown") return action("move-down");
    if (key === "arrowup") return action("move-up");
    if (key === "enter" || key === "tab") return action("accept-slash");
    if (key === "escape") return action("close-slash");
  }

  if (mod && key === "z") return action(input.shiftKey ? "redo" : "undo");
  if (mod && key === "y") return action("redo");
  if (mod && key === "b") return action("format", "bold");
  if (mod && key === "i") return action("format", "italic");
  if (mod && key === "e") return action("format", "code");
  if (mod && key === "k") return action("format", "link");
  if (mod && key === "d") return action("duplicate");

  if (key === "escape") return action("close-slash");
  if (key === "/") return action("open-slash");
  if (key === "@") return action("format", "mention");
  if (key === "tab" && input.shiftKey) return action("outdent");
  if (key === "tab") return action("indent");

  const start = input.selectionStart ?? 0;
  const end = input.selectionEnd ?? start;
  const value = input.value ?? "";

  if (key === "enter" && !input.shiftKey)
    return action("split", value.slice(start));
  if (key === "backspace" && start === 0 && end === 0) return action("merge");
  if (key === "delete" && start === value.length && end === start)
    return action("merge");
  if (key === "arrowup" && start === 0) return action("move-up");
  if (key === "arrowdown" && start === value.length) return action("move-down");

  return action("none");
}

export function shouldPreventDefault(
  input: KeyInput,
  resolved: KeyboardAction,
): boolean {
  if (resolved.kind === "none") return false;
  if (resolved.kind === "move-up" || resolved.kind === "move-down") {
    return Boolean(
      input.slashOpen || input.mentionOpen || input.selectionStart === 0,
    );
  }
  return resolved.kind !== "format" || Boolean(input.metaKey || input.ctrlKey);
}

export function slashQueryForValue(
  value: string,
  caret: number,
): string | null {
  const before = value.slice(0, caret);
  const match = /(?:^|\s)\/([^\s/]*)$/.exec(before);
  return match ? match[1] : null;
}

export function mentionQueryForValue(
  value: string,
  caret: number,
): string | null {
  const before = value.slice(0, caret);
  const match = /(?:^|\s)@([^\s@]*)$/.exec(before);
  return match ? match[1] : null;
}

export function replaceSlashToken(
  value: string,
  caret: number,
  replacement: string,
): string {
  const before = value.slice(0, caret);
  const after = value.slice(caret);
  const replaced = before.replace(/(?:^|\s)\/[^\s/]*$/, (token) => {
    const prefix = token.startsWith("/") ? "" : (token[0] ?? "");
    return `${prefix}${replacement}`;
  });
  return replaced + after;
}

export function replaceMentionToken(
  value: string,
  caret: number,
  replacement: string,
): string {
  const before = value.slice(0, caret);
  const after = value.slice(caret);
  const replaced = before.replace(/(?:^|\s)@[^\s@]*$/, (token) => {
    const prefix = token.startsWith("@") ? "" : (token[0] ?? "");
    return `${prefix}${replacement}`;
  });
  return replaced + after;
}

export function menuIndex(
  current: number,
  direction: "up" | "down",
  count: number,
): number {
  if (count <= 0) return 0;
  const delta = direction === "down" ? 1 : -1;
  return (((current + delta) % count) + count) % count;
}

export function keyForCommand(key: string): string {
  return normalizeKey(key);
}
