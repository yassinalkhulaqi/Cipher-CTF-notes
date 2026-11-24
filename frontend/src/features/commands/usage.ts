/** Recent/frequent command ranking data model for the palette. */

import type { CommandInvocation, UsageEvent } from "./types";

export class UsageModel {
  private readonly events = new Map<string, UsageEvent[]>();
  private readonly halfLife: number;
  private readonly now: () => number;

  constructor(
    halfLifeSeconds = 86400,
    now: () => number = () => Date.now() / 1000,
  ) {
    if (halfLifeSeconds <= 0)
      throw new Error("half_life_seconds must be positive");
    this.halfLife = halfLifeSeconds;
    this.now = now;
  }

  record(
    invocation: CommandInvocation,
    paneId = "",
    contextRef = "",
    timestamp?: number,
  ): UsageEvent {
    const event: UsageEvent = {
      command_id: invocation.command_id,
      timestamp: timestamp ?? this.now(),
      pane_id: paneId,
      context_ref: contextRef,
    };
    const existing = this.events.get(event.command_id) ?? [];
    existing.push(event);
    this.events.set(event.command_id, existing);
    return event;
  }

  count(commandId: string): number {
    return (this.events.get(commandId) ?? []).length;
  }

  recent(limit = 10): UsageEvent[] {
    if (limit < 1) throw new Error("limit must be positive");
    const flat = Array.from(this.events.values()).flat();
    const seen = new Set<string>();
    const result: UsageEvent[] = [];
    for (const event of flat.sort(
      (a, b) =>
        b.timestamp - a.timestamp || a.command_id.localeCompare(b.command_id),
    )) {
      if (seen.has(event.command_id)) continue;
      seen.add(event.command_id);
      result.push(event);
      if (result.length === limit) break;
    }
    return result;
  }

  frequent(limit = 10): Array<{ command_id: string; count: number }> {
    if (limit < 1) throw new Error("limit must be positive");
    return Array.from(this.events.entries())
      .map(([command_id, values]) => ({
        command_id,
        count: values.length,
        last: Math.max(...values.map((event) => event.timestamp)),
      }))
      .sort(
        (a, b) =>
          b.count - a.count ||
          b.last - a.last ||
          a.command_id.localeCompare(b.command_id),
      )
      .slice(0, limit)
      .map(({ command_id, count }) => ({ command_id, count }));
  }

  recencyScore(commandId: string, now = this.now()): number {
    const values = this.events.get(commandId) ?? [];
    if (!values.length) return 0;
    const last = Math.max(...values.map((event) => event.timestamp));
    return Math.exp((-Math.log(2) * Math.max(0, now - last)) / this.halfLife);
  }

  frequencyScore(commandId: string): number {
    const count = this.count(commandId);
    return count ? Math.min(1, Math.log1p(count) / Math.log1p(20)) : 0;
  }

  score(commandId: string, now = this.now()): number {
    return (
      0.6 * this.recencyScore(commandId, now) +
      0.4 * this.frequencyScore(commandId)
    );
  }

  prune(before: number): number {
    let removed = 0;
    for (const [commandId, values] of Array.from(this.events.entries())) {
      const kept = values.filter((event) => event.timestamp >= before);
      removed += values.length - kept.length;
      if (kept.length) this.events.set(commandId, kept);
      else this.events.delete(commandId);
    }
    return removed;
  }

  clear(): void {
    this.events.clear();
  }

  size(): number {
    return Array.from(this.events.values()).reduce(
      (total, values) => total + values.length,
      0,
    );
  }

  snapshot(): { half_life_seconds: number; events: UsageEvent[] } {
    const events = Array.from(this.events.values())
      .flat()
      .sort(
        (a, b) =>
          a.timestamp - b.timestamp || a.command_id.localeCompare(b.command_id),
      );
    return { half_life_seconds: this.halfLife, events };
  }

  load(snapshot: { events?: UsageEvent[] }): void {
    this.events.clear();
    for (const event of snapshot.events ?? []) {
      const values = this.events.get(event.command_id) ?? [];
      values.push({ ...event });
      this.events.set(event.command_id, values);
    }
  }
}
