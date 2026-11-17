export interface CommandDescriptor {
  id: string;
  title: string;
  group?: string;
  keywords?: string[];
  shortcut?: string;
  enabled?: boolean;
  run: () => void | Promise<void>;
  danger?: boolean;
}

export interface CommandConflict {
  shortcut: string;
  commands: CommandDescriptor[];
}

export type CommandListener = () => void;

const DEFAULT_GROUP = "General";

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

export function normalizeShortcut(shortcut: string): string {
  return shortcut.trim().toLowerCase().replace(/\s+/g, "");
}

function isEnabled(command: CommandDescriptor): boolean {
  return command.enabled !== false;
}

function isSubsequence(needle: string, haystack: string): boolean {
  let index = 0;
  for (const character of haystack) {
    if (character === needle[index]) index += 1;
    if (index === needle.length) return true;
  }
  return needle.length === 0;
}

function tokenScore(command: CommandDescriptor, token: string): number | null {
  const id = normalize(command.id);
  const title = normalize(command.title);
  const keywords = (command.keywords ?? []).map(normalize);
  const group = normalize(command.group ?? DEFAULT_GROUP);

  if (id === token || title === token) return 1000;
  if (title.startsWith(token) || id.startsWith(token)) return 800;
  if (keywords.includes(token)) return 700;
  if (group === token) return 600;
  if (title.includes(token) || id.includes(token)) return 500;
  if (keywords.some((keyword) => keyword.includes(token))) return 400;
  if (
    isSubsequence(token, title) ||
    isSubsequence(token, id) ||
    keywords.some((keyword) => isSubsequence(token, keyword))
  ) {
    return 200;
  }
  return null;
}

/**
 * Framework-free command registry. Regex-free fuzzy search keeps ranking
 * deterministic: stronger field matches always win, then insertion order.
 */
export class CommandRegistry {
  private readonly commands = new Map<string, CommandDescriptor>();
  private readonly listeners = new Set<CommandListener>();

  get size(): number {
    return this.commands.size;
  }

  register(command: CommandDescriptor): () => void {
    this.validate(command, new Set());
    this.commands.set(command.id, command);
    this.notify();
    return () => {
      this.unregister(command.id);
    };
  }

  registerMany(commands: readonly CommandDescriptor[]): () => void {
    const seen = new Set<string>();
    for (const command of commands) {
      this.validate(command, seen);
      seen.add(command.id);
    }
    for (const command of commands) {
      this.commands.set(command.id, command);
    }
    this.notify();
    return () => {
      let changed = false;
      for (const command of commands) {
        changed = this.commands.delete(command.id) || changed;
      }
      if (changed) this.notify();
    };
  }

  unregister(id: string): boolean {
    const removed = this.commands.delete(id);
    if (removed) this.notify();
    return removed;
  }

  clear(): void {
    if (this.commands.size === 0) return;
    this.commands.clear();
    this.notify();
  }

  get(id: string): CommandDescriptor | undefined {
    return this.commands.get(id);
  }

  has(id: string): boolean {
    return this.commands.has(id);
  }

  list(): CommandDescriptor[] {
    return [...this.commands.values()];
  }

  byGroup(): Record<string, CommandDescriptor[]> {
    const groups: Record<string, CommandDescriptor[]> = {};
    for (const command of this.commands.values()) {
      const group = command.group ?? DEFAULT_GROUP;
      (groups[group] ??= []).push(command);
    }
    return groups;
  }

  search(query: string): CommandDescriptor[] {
    const tokens = normalize(query).split(/\s+/).filter(Boolean);
    const entries = [...this.commands.values()]
      .filter(isEnabled)
      .map((command, index) => ({ command, index }));

    if (tokens.length === 0) {
      return entries.map((entry) => entry.command);
    }

    const needle = normalize(query);
    const ranked: Array<{
      command: CommandDescriptor;
      index: number;
      score: number;
    }> = [];

    for (const entry of entries) {
      let score = 0;
      let matched = true;
      for (const token of tokens) {
        const value = tokenScore(entry.command, token);
        if (value === null) {
          matched = false;
          break;
        }
        score += value;
      }
      if (!matched) continue;
      if (normalize(entry.command.title).includes(needle)) score += 50;
      if (normalize(entry.command.id) === needle) score += 50;
      ranked.push({ ...entry, score });
    }

    ranked.sort(
      (left, right) => right.score - left.score || left.index - right.index,
    );
    return ranked.map((entry) => entry.command);
  }

  resolveShortcut(shortcut: string): CommandDescriptor | null {
    const target = normalizeShortcut(shortcut);
    if (!target) return null;
    for (const command of this.commands.values()) {
      if (!isEnabled(command) || !command.shortcut) continue;
      if (normalizeShortcut(command.shortcut) === target) return command;
    }
    return null;
  }

  findConflicts(): CommandConflict[] {
    const byShortcut = new Map<string, CommandDescriptor[]>();
    for (const command of this.commands.values()) {
      if (!command.shortcut) continue;
      const key = normalizeShortcut(command.shortcut);
      if (!key) continue;
      const group = byShortcut.get(key) ?? [];
      group.push(command);
      byShortcut.set(key, group);
    }

    const conflicts: CommandConflict[] = [];
    for (const commands of byShortcut.values()) {
      if (commands.length < 2) continue;
      conflicts.push({
        shortcut: commands[0].shortcut ?? "",
        commands,
      });
    }
    return conflicts;
  }

  setEnabled(id: string, enabled: boolean): boolean {
    const command = this.commands.get(id);
    if (!command) return false;
    if (isEnabled(command) === enabled) return true;
    this.commands.set(id, { ...command, enabled });
    this.notify();
    return true;
  }

  enable(id: string): boolean {
    return this.setEnabled(id, true);
  }

  disable(id: string): boolean {
    return this.setEnabled(id, false);
  }

  subscribe(listener: CommandListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  notify(): void {
    this.listeners.forEach((listener) => {
      try {
        listener();
      } catch {
        // One faulty subscriber must not prevent the rest from updating.
      }
    });
  }

  private validate(command: CommandDescriptor, seen: Set<string>): void {
    if (!command.id.trim()) {
      throw new Error("Command id must not be empty");
    }
    if (this.commands.has(command.id) || seen.has(command.id)) {
      throw new Error(`Command "${command.id}" is already registered`);
    }
  }
}
