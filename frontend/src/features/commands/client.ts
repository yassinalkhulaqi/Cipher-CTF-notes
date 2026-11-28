/** Typed client for the commands namespace of API v3. */

import { V3Client } from "../../v3/apiClient";
import type {
  CommandContext,
  CommandGroupResult,
  CommandInvocation,
  CommandSpec,
  FocusSession,
  MacroRecord,
  NavNode,
  PaneSpec,
  UsageEvent,
  WorkspaceSnapshot,
} from "./types";

export interface ContextBody {
  pane?: string;
  ref?: string;
  selection?: string[];
  tags?: string[];
}

export interface ManifestData {
  commands: CommandSpec[];
  groups: string[];
  capabilities: Record<string, boolean>;
  permission: number;
}

export class CommandsClient {
  private readonly client: V3Client;

  constructor(client?: V3Client) {
    this.client = client ?? new V3Client();
  }

  manifest(): Promise<ManifestData> {
    return this.client.data<ManifestData>("commands", "manifest");
  }

  list(
    body: ContextBody = {},
  ): Promise<{ commands: CommandSpec[]; context: CommandContext }> {
    return this.client.data(
      "commands",
      "list",
      body as unknown as Record<string, unknown>,
    );
  }

  context(body: ContextBody = {}): Promise<{ context: CommandContext }> {
    return this.client.data(
      "commands",
      "context",
      body as unknown as Record<string, unknown>,
    );
  }

  suggest(
    query: string,
    body: ContextBody = {},
    limit = 12,
  ): Promise<{ groups: CommandGroupResult[]; context: CommandContext }> {
    return this.client.data("commands", "suggest", { ...body, query, limit });
  }

  execute(
    invocation: CommandInvocation,
    body: ContextBody = {},
  ): Promise<{ result: unknown; focus: unknown }> {
    return this.client.data("commands", "execute", { ...body, ...invocation });
  }

  usageRecent(limit = 10): Promise<{ recent: UsageEvent[] }> {
    return this.client.data("commands", "usage.recent", { limit });
  }

  usageFrequent(
    limit = 10,
  ): Promise<{ frequent: Array<{ command_id: string; count: number }> }> {
    return this.client.data("commands", "usage.frequent", { limit });
  }

  macros(): Promise<{
    macros: MacroRecord[];
    recorder: { recording: boolean; steps: number };
  }> {
    return this.client.data("commands", "macros.list");
  }

  startMacro(
    name: string,
  ): Promise<{ recorder: { recording: boolean; steps: number } }> {
    return this.client.data("commands", "macros.start", { name });
  }

  stopMacro(): Promise<{ macro: MacroRecord }> {
    return this.client.data("commands", "macros.stop");
  }

  runMacro(
    name: string,
    values: Record<string, string> = {},
  ): Promise<{ steps: CommandInvocation[] }> {
    return this.client.data("commands", "macros.run", { name, values });
  }

  deleteMacro(macroId: string): Promise<{ deleted: boolean }> {
    return this.client.data("commands", "macros.delete", { macro_id: macroId });
  }

  breadcrumbs(ref: string): Promise<{ crumbs: NavNode[] }> {
    return this.client.data("commands", "nav.breadcrumbs", { ref });
  }

  neighbors(ref: string, limit = 8): Promise<{ neighbors: NavNode[] }> {
    return this.client.data("commands", "nav.neighbors", { ref, limit });
  }

  focusStatus(): Promise<{
    focus: {
      active: boolean;
      paused: boolean;
      session: FocusSession | null;
      completed: number;
    };
  }> {
    return this.client.data("commands", "focus.status");
  }

  focusStart(
    label: string,
    target = "",
    restorePane = "",
  ): Promise<{ session: FocusSession }> {
    return this.client.data("commands", "focus.start", {
      label,
      target,
      restore_pane: restorePane,
    });
  }

  focusTransition(
    action: "pause" | "resume" | "end",
  ): Promise<{ session: FocusSession }> {
    return this.client.data(`commands`, `focus.${action}`);
  }

  workspaceSnapshot(): Promise<{
    workspace: WorkspaceSnapshot;
    panes: PaneSpec[];
  }> {
    return this.client.data("commands", "workspace.snapshot");
  }

  workspaceSplit(
    pane: string,
    orientation: string,
    newPane: string,
  ): Promise<{ pane: PaneSpec }> {
    return this.client.data("commands", "workspace.split", {
      pane,
      orientation,
      new_pane: newPane,
    });
  }

  workspaceResize(pane: string, size: number): Promise<{ pane: PaneSpec }> {
    return this.client.data("commands", "workspace.resize", { pane, size });
  }

  workspaceClose(pane: string): Promise<{ pane: PaneSpec }> {
    return this.client.data("commands", "workspace.close", { pane });
  }

  workspaceContext(pane: string, ref: string): Promise<{ pane: PaneSpec }> {
    return this.client.data("commands", "workspace.context", { pane, ref });
  }

  workspaceRestore(
    workspace: WorkspaceSnapshot,
  ): Promise<{ workspace: WorkspaceSnapshot }> {
    return this.client.data("commands", "workspace.restore", { workspace });
  }
}
