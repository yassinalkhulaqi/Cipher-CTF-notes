/** Focus-session state machine with data-only snapshots. */

import type { FocusSession, FocusStatus } from "./types";

export class FocusError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FocusError";
  }
}

export function parseFocusStatus(value: string): FocusStatus {
  if (value === "active" || value === "paused" || value === "ended")
    return value;
  throw new FocusError(`Unknown focus status: ${value}`);
}

export class FocusManager {
  private currentSession: FocusSession | null = null;
  private readonly archived: FocusSession[] = [];
  private counter = 0;
  private readonly now: () => number;

  constructor(now: () => number = () => Date.now() / 1000) {
    this.now = now;
  }

  current(): FocusSession | null {
    return this.currentSession ? { ...this.currentSession } : null;
  }

  start(label: string, target = "", restorePane = ""): FocusSession {
    if (this.currentSession && this.currentSession.status !== "ended") {
      throw new FocusError("A focus session is already running");
    }
    if (!label.trim())
      throw new FocusError("Focus session label cannot be blank");
    this.counter += 1;
    this.currentSession = {
      id: `focus_${this.counter}`,
      label,
      started_at: this.now(),
      status: "active",
      target,
      restore_pane: restorePane,
      interruptions: 0,
      ended_at: 0,
    };
    return this.currentSession as FocusSession;
  }

  private replace(changes: Partial<FocusSession>): FocusSession {
    if (!this.currentSession) throw new FocusError("No active focus session");
    this.currentSession = { ...this.currentSession, ...changes };
    return this.currentSession as FocusSession;
  }

  pause(): FocusSession {
    if (!this.currentSession || this.currentSession.status !== "active") {
      throw new FocusError("Only an active session can be paused");
    }
    return this.replace({ status: "paused" });
  }

  resume(): FocusSession {
    if (!this.currentSession || this.currentSession.status !== "paused") {
      throw new FocusError("Only a paused session can be resumed");
    }
    return this.replace({ status: "active" });
  }

  interrupt(): FocusSession {
    if (!this.currentSession || this.currentSession.status === "ended") {
      throw new FocusError("No active focus session to interrupt");
    }
    return this.replace({
      interruptions: this.currentSession.interruptions + 1,
    });
  }

  end(): FocusSession {
    if (!this.currentSession || this.currentSession.status === "ended") {
      throw new FocusError("No active focus session to end");
    }
    const session = this.replace({ status: "ended", ended_at: this.now() });
    this.archived.push(session);
    return session;
  }

  history(): FocusSession[] {
    return this.archived.map((session) => ({ ...session }));
  }

  restoreTarget(): string {
    return this.currentSession?.restore_pane ?? "";
  }

  status(): {
    active: boolean;
    paused: boolean;
    session: FocusSession | null;
    completed: number;
  } {
    return {
      active: Boolean(
        this.currentSession && this.currentSession.status !== "ended",
      ),
      paused: this.currentSession?.status === "paused",
      session: this.current(),
      completed: this.archived.length,
    };
  }

  snapshot(): {
    counter: number;
    current: FocusSession | null;
    history: FocusSession[];
  } {
    return {
      counter: this.counter,
      current: this.current(),
      history: this.history(),
    };
  }

  restore(snapshot: {
    counter?: number;
    current?: FocusSession | null;
    history?: FocusSession[];
  }): void {
    this.counter = snapshot.counter ?? 0;
    this.currentSession = snapshot.current ? { ...snapshot.current } : null;
    this.archived.length = 0;
    this.archived.push(
      ...(snapshot.history ?? []).map((session) => ({ ...session })),
    );
  }
}
