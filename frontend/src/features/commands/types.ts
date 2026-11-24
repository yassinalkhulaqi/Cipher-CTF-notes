/** Wire types for the V3 command center. Data only; never executable. */

import type { EntityKind, EntityRef } from "../../v3/types";

export type CommandGroup =
  | "navigation"
  | "create"
  | "inspect"
  | "edit"
  | "view"
  | "session"
  | "automation"
  | "system";

export type CommandEffect =
  | "navigate"
  | "open_pane"
  | "mutate"
  | "inspect"
  | "dialog"
  | "focus"
  | "macro";

export type ArgumentType =
  | "text"
  | "choice"
  | "number"
  | "boolean"
  | "entity_ref";

export type CommandStatus = "enabled" | "disabled" | "hidden";

export interface ArgumentSpec {
  name: string;
  arg_type: ArgumentType;
  required: boolean;
  default: string;
  choices: string[];
  help: string;
  max_length: number;
}

export interface CommandSpec {
  id: string;
  title: string;
  group: CommandGroup;
  description: string;
  keywords: string[];
  aliases: string[];
  arguments: ArgumentSpec[];
  capability: string;
  status: CommandStatus;
  effect: CommandEffect;
  order: number;
  target_kind: EntityKind | "";
  requires_selection: boolean;
  min_permission: number;
}

export interface CommandInvocation {
  command_id: string;
  arguments: Record<string, string>;
  source: string;
  context_ref: string;
}

export interface CommandHit {
  command: CommandSpec;
  score: number;
  signals: string[];
  matched_text: string;
}

export interface CommandGroupResult {
  group: CommandGroup;
  label: string;
  hits: CommandHit[];
}

export interface CommandContext {
  pane_id: string;
  workspace_id: string;
  entity: EntityRef | null;
  selection: EntityRef[];
  tags: string[];
  focus_active: boolean;
  capabilities: string[];
}

export interface UsageEvent {
  command_id: string;
  timestamp: number;
  pane_id: string;
  context_ref: string;
}

export interface MacroStep {
  command_id: string;
  arguments: Record<string, string>;
  context_mode: "inherit" | "explicit" | "pane";
  note: string;
}

export interface MacroRecord {
  id: string;
  name: string;
  steps: MacroStep[];
  description: string;
  tags: string[];
  created_at: number;
  author: string;
  version: number;
}

export interface NavNode {
  id: string;
  label: string;
  kind: string;
  parent: string;
  order: number;
  entity: EntityRef | null;
}

export interface NavPath {
  nodes: string[];
  cost: number;
}

export type FocusStatus = "active" | "paused" | "ended";

export interface FocusSession {
  id: string;
  label: string;
  started_at: number;
  status: FocusStatus;
  target: string;
  restore_pane: string;
  interruptions: number;
  ended_at: number;
}

export type PaneOrientation = "horizontal" | "vertical";

export interface PaneSpec {
  id: string;
  title: string;
  kind: string;
  context_ref: string;
  size: number;
  min_size: number;
  pinned: boolean;
  closable: boolean;
}

export interface PaneNode {
  pane?: PaneSpec;
  orientation?: PaneOrientation;
  ratio?: number;
  children?: PaneNode[];
}

export interface WorkspaceSnapshot {
  id: string;
  active_pane: string;
  tree: { root: PaneNode };
}
