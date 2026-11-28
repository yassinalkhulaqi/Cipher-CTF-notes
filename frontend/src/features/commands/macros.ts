/** Data-only macro recorder and library for command sequences. */

import type { CommandInvocation, MacroRecord, MacroStep } from "./types";

const PLACEHOLDER = /\{\{\s*([a-z][a-z0-9_]*)\s*\}\}/g;
export const MAX_MACRO_STEPS = 64;

export class MacroError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MacroError";
  }
}

export function macroStepsAsData(
  macro: MacroRecord,
): Array<Record<string, string>> {
  return macro.steps.map((step) => ({
    command_id: step.command_id,
    arguments: JSON.stringify(step.arguments),
  }));
}

export function expandMacro(
  macro: MacroRecord,
  values: Record<string, string>,
): CommandInvocation[] {
  return macro.steps.map((step) => {
    const missing = Array.from(
      new Set(
        Object.values(step.arguments)
          .flatMap((value) =>
            Array.from(
              String(value).matchAll(PLACEHOLDER),
              (match) => match[1],
            ),
          )
          .filter((key) => !(key in values)),
      ),
    ).sort();
    if (missing.length) {
      throw new MacroError(
        `Macro '${macro.name}' needs: ${missing.join(", ")}`,
      );
    }
    const arguments_: Record<string, string> = {};
    for (const [name, template] of Object.entries(step.arguments)) {
      arguments_[name] = template.replace(
        PLACEHOLDER,
        (_, key: string) => values[key],
      );
    }
    return {
      command_id: step.command_id,
      arguments: arguments_,
      source: "macro",
      context_ref: "",
    };
  });
}

export class MacroRecorder {
  private name = "";
  private description = "";
  private startedAt = 0;
  private steps: MacroStep[] = [];
  private readonly now: () => number;

  constructor(now: () => number = () => Date.now() / 1000) {
    this.now = now;
  }

  get recording(): boolean {
    return this.name.length > 0;
  }

  get size(): number {
    return this.steps.length;
  }

  start(name: string, description = ""): void {
    if (this.recording)
      throw new MacroError("A macro recording is already in progress");
    if (!name.trim()) throw new MacroError("Macro name cannot be blank");
    this.name = name.trim();
    this.description = description;
    this.startedAt = this.now();
    this.steps = [];
  }

  capture(invocation: CommandInvocation, note = ""): MacroStep {
    if (!this.recording) throw new MacroError("No macro recording in progress");
    if (this.steps.length >= MAX_MACRO_STEPS)
      throw new MacroError("Macro step limit reached");
    const step: MacroStep = {
      command_id: invocation.command_id,
      arguments: { ...invocation.arguments },
      context_mode: "inherit",
      note,
    };
    this.steps.push(step);
    return step;
  }

  stop(id: string): MacroRecord {
    if (!this.recording) throw new MacroError("No macro recording in progress");
    if (!this.steps.length)
      throw new MacroError("Cannot stop a recording with no steps");
    const macro: MacroRecord = {
      id,
      name: this.name,
      steps: this.steps.map((step) => ({
        ...step,
        arguments: { ...step.arguments },
      })),
      description: this.description,
      tags: [],
      created_at: this.startedAt,
      author: "local",
      version: 1,
    };
    this.cancel();
    return macro;
  }

  cancel(): void {
    this.name = "";
    this.description = "";
    this.startedAt = 0;
    this.steps = [];
  }
}

export class MacroLibrary {
  private readonly macros = new Map<string, MacroRecord>();

  add(macro: MacroRecord): MacroRecord {
    if (this.macros.has(macro.id))
      throw new MacroError(`Macro already exists: ${macro.id}`);
    this.macros.set(macro.id, macro);
    return macro;
  }

  get(id: string): MacroRecord {
    const macro = this.macros.get(id);
    if (!macro) throw new MacroError(`Unknown macro: ${id}`);
    return macro;
  }

  findByName(name: string): MacroRecord | undefined {
    const needle = name.trim().toLowerCase();
    return Array.from(this.macros.values()).find(
      (macro) => macro.name.toLowerCase() === needle,
    );
  }

  remove(id: string): boolean {
    return this.macros.delete(id);
  }

  all(): MacroRecord[] {
    return Array.from(this.macros.values()).sort(
      (a, b) =>
        a.name.toLowerCase().localeCompare(b.name.toLowerCase()) ||
        a.id.localeCompare(b.id),
    );
  }

  load(macros: MacroRecord[]): void {
    this.macros.clear();
    for (const macro of macros) this.macros.set(macro.id, macro);
  }
}
