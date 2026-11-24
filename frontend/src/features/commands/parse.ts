/** Command-bar text parsing. Mirrors the Python command parser. */

import type { ArgumentSpec, CommandInvocation, CommandSpec } from "./types";

export class ParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ParseError";
  }
}

const COMMAND_ID = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){0,2}$/;
const ARGUMENT_NAME = /^[a-z][a-z0-9_]*$/;
const SEQUENCE_MARKER = /^\s*(?:(?:\d+[.)]|[-*])\s+)+/;

export interface Token {
  value: string;
  position: number;
  flag: boolean;
}

export interface ParsedInput {
  command_id: string;
  named: Record<string, string>;
  positional: string[];
  raw: string;
}

export function canonicalizeCommandId(raw: string): string {
  let candidate = raw.trim();
  while (candidate.startsWith("/") || candidate.startsWith(">")) {
    candidate = candidate.slice(1).trim();
  }
  candidate = candidate
    .replace(/[: ]/g, ".")
    .toLowerCase()
    .replace(/\.+/g, ".")
    .replace(/^\.+|\.+$/g, "");
  if (!COMMAND_ID.test(candidate))
    throw new ParseError(`Invalid command id: ${raw}`);
  return candidate;
}

export function tokenize(text: string): Token[] {
  const tokens: Token[] = [];
  const buffer: string[] = [];
  let start = 0;
  let index = 0;
  let quoted = false;
  while (index < text.length) {
    const char = text[index];
    if (char === '"' || char === "'") {
      quoted = !quoted;
      index += 1;
      continue;
    }
    if (char === "\\" && index + 1 < text.length) {
      const next = text[index + 1];
      if (
        quoted ||
        next === '"' ||
        next === "'" ||
        next === "\\" ||
        next === " "
      ) {
        buffer.push(next);
        index += 2;
        continue;
      }
    }
    if (/\s/.test(char) && !quoted) {
      if (buffer.length) {
        const value = buffer.join("");
        tokens.push({ value, position: start, flag: value.startsWith("--") });
        buffer.length = 0;
      }
      index += 1;
      start = index;
      continue;
    }
    buffer.push(char);
    index += 1;
  }
  if (quoted) throw new ParseError("Unterminated quote in command text");
  if (buffer.length) {
    const value = buffer.join("");
    tokens.push({ value, position: start, flag: value.startsWith("--") });
  }
  return tokens;
}

function splitNamed(token: Token): [string, string] | null {
  let value = token.value;
  if (value.startsWith("--")) value = value.slice(2);
  if (!value.includes("=")) return null;
  const separator = value.indexOf("=");
  const name = value.slice(0, separator);
  if (!ARGUMENT_NAME.test(name))
    throw new ParseError(`Invalid argument name at ${token.position}`);
  return [name, value.slice(separator + 1)];
}

export function parseCommand(text: string): ParsedInput {
  const tokens = tokenize(text);
  if (!tokens.length) throw new ParseError("Command text cannot be empty");
  const commandId = canonicalizeCommandId(tokens[0].value);
  const named: Record<string, string> = {};
  const positional: string[] = [];
  let index = 1;
  while (index < tokens.length) {
    const token = tokens[index];
    const pair = splitNamed(token);
    if (pair) {
      if (pair[0] in named)
        throw new ParseError(`Duplicate argument '${pair[0]}'`);
      named[pair[0]] = pair[1];
      index += 1;
      continue;
    }
    if (token.flag) {
      const name = token.value.slice(2);
      if (!ARGUMENT_NAME.test(name))
        throw new ParseError(`Invalid flag at ${token.position}`);
      if (name in named) throw new ParseError(`Duplicate argument '${name}'`);
      const next = tokens[index + 1];
      if (!next || next.flag) {
        named[name] = "true";
        index += 1;
      } else {
        named[name] = next.value;
        index += 2;
      }
      continue;
    }
    positional.push(token.value);
    index += 1;
  }
  return { command_id: commandId, named, positional, raw: text };
}

function coerce(value: string, spec: ArgumentSpec): string {
  if (spec.arg_type === "boolean") {
    const mapping: Record<string, string> = {
      yes: "true",
      no: "false",
      1: "true",
      0: "false",
    };
    return validateArgument(
      mapping[value.toLowerCase()] ?? value.toLowerCase(),
      spec,
    );
  }
  return validateArgument(value, spec);
}

export function validateArgument(value: string, spec: ArgumentSpec): string {
  if (value.length > spec.max_length) {
    throw new ParseError(
      `Argument '${spec.name}' exceeds ${spec.max_length} characters`,
    );
  }
  if (spec.arg_type === "choice" && !spec.choices.includes(value)) {
    throw new ParseError(
      `Argument '${spec.name}' must be one of: ${spec.choices.join(", ")}`,
    );
  }
  if (spec.arg_type === "number" && !Number.isFinite(Number(value))) {
    throw new ParseError(`Argument '${spec.name}' must be numeric`);
  }
  if (
    spec.arg_type === "boolean" &&
    !["true", "false"].includes(value.toLowerCase())
  ) {
    throw new ParseError(`Argument '${spec.name}' must be a boolean`);
  }
  if (spec.arg_type === "entity_ref" && !value.includes(":")) {
    throw new ParseError(
      `Argument '${spec.name}' must be a kind:value reference`,
    );
  }
  return value;
}

export function bindArguments(
  parsed: ParsedInput,
  spec: CommandSpec,
): CommandInvocation {
  if (
    parsed.command_id !== spec.id &&
    !spec.aliases.includes(parsed.command_id)
  ) {
    throw new ParseError(
      `Command '${parsed.command_id}' does not match '${spec.id}'`,
    );
  }
  const known = new Set(spec.arguments.map((argument) => argument.name));
  const unknown = Object.keys(parsed.named)
    .filter((name) => !known.has(name))
    .sort();
  if (unknown.length)
    throw new ParseError(`Unknown argument(s): ${unknown.join(", ")}`);
  const values: Record<string, string> = {};
  for (const [name, value] of Object.entries(parsed.named)) {
    const argument = spec.arguments.find((item) => item.name === name);
    if (argument) values[name] = coerce(value, argument);
  }
  const remaining = spec.arguments
    .map((argument) => argument.name)
    .filter((name) => !(name in values));
  if (parsed.positional.length > remaining.length) {
    throw new ParseError(
      `Command '${spec.id}' accepts at most ${remaining.length} positional values`,
    );
  }
  remaining.forEach((name, index) => {
    const argument = spec.arguments.find((item) => item.name === name);
    const value = parsed.positional[index];
    if (argument && value !== undefined) values[name] = coerce(value, argument);
  });
  const missing = spec.arguments
    .filter((argument) => argument.required && !(argument.name in values))
    .map((argument) => argument.name);
  if (missing.length)
    throw new ParseError(`Missing required argument(s): ${missing.join(", ")}`);
  for (const argument of spec.arguments) {
    if (!(argument.name in values) && argument.default)
      values[argument.name] = argument.default;
  }
  return {
    command_id: spec.id,
    arguments: values,
    source: "palette",
    context_ref: "",
  };
}

function quote(value: string): string {
  if (!value) return '""';
  if (/\s/.test(value) || /["'\\]/.test(value)) {
    return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }
  return value;
}

export function renderCommand(
  invocation: CommandInvocation,
  spec?: CommandSpec,
): string {
  const entries = Object.entries(invocation.arguments);
  if (spec) {
    const order = new Map(
      spec.arguments.map((argument, index) => [argument.name, index]),
    );
    entries.sort((a, b) => (order.get(a[0]) ?? 999) - (order.get(b[0]) ?? 999));
  }
  return [
    `/${invocation.command_id}`,
    ...entries.map(([name, value]) => `--${name} ${quote(value)}`),
  ].join(" ");
}

export function parseSequence(text: string): ParsedInput[] {
  return text
    .split("\n")
    .map((line) => line.replace(SEQUENCE_MARKER, "").trim())
    .filter((line) => line.length > 0)
    .map((line) => parseCommand(line));
}
