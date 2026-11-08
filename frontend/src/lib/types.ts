export type NodeKind = "note" | "folder";
export type Status = "todo" | "active" | "done" | "blocked";
export type Difficulty = "" | "easy" | "medium" | "hard" | "insane";
export type Theme = "dark" | "light";
export type ViewMode = "editor" | "split" | "preview";
export type SaveState = "idle" | "dirty" | "saving" | "saved" | "error";

export interface VaultStats {
  notes: number;
  folders: number;
  flags: number;
  targets: number;
  tags: number;
  pinned: number;
  trashed: number;
}

export interface NodeSummary {
  id: number;
  parent_id: number | null;
  title: string;
  kind: NodeKind;
  status: Status;
  difficulty: Difficulty;
  flag: string;
  tags: string;
  tag_list: string[];
  target: string;
  pinned: boolean;
  trashed: boolean;
  path: string;
  created_at: string;
  updated_at: string;
}

export interface TreeNode extends NodeSummary {
  children: TreeNode[];
}

export interface NodeDetail extends NodeSummary {
  content: string;
  preview_html: string;
  children?: NodeSummary[];
  has_preview?: boolean;
}

export interface BootData {
  version: string;
  theme: Theme;
  font_size: number;
  view_mode: ViewMode;
  restore_last_note: boolean;
  sync_preview_scroll: boolean;
  last_note: number | null;
  last_template: string;
  sidebar_width: number | null;
  split_sash: number | null;
  vault_path: string;
  stats: VaultStats;
  empty: boolean;
}

export interface SearchHit {
  node_id: number;
  title: string;
  path: string;
  snippet: string;
  rank: number;
}

export interface Snippet {
  title: string;
  command: string;
  description: string;
  tags: string;
  tag_list: string[];
  builtin: boolean;
  builtin_key: string;
  id: number | null;
}

export interface Template {
  key: string;
  name: string;
  description: string;
  content: string;
  tags: string;
  status: Status;
  default_title: string;
  glyph: string;
}

export interface FlagHit {
  flag: string;
  node_id: number;
  title: string;
  path: string;
  manual: boolean;
}

export interface TagCount {
  tag: string;
  count: number;
}

export interface Settings {
  theme: string;
  font_size: string;
  last_template: string;
  last_note: string;
  view_mode: string;
  restore_last_note: string;
  sidebar_width: string;
  split_sash: string;
  sync_preview_scroll: string;
  tree_expanded: string;
}

export interface ExportPayload {
  content: string;
  filename: string;
  mime: string;
}

export interface TrashedNode extends NodeSummary {
  trashed_at?: string;
}

export interface GraphNode {
  id: number;
  title: string;
  kind: "note" | "folder" | "reference";
  path: string;
  status: Status;
  flag: string;
  tags: string[];
  target: string;
  pinned: boolean;
  resolved: boolean;
}

export interface GraphEdge {
  source: number;
  target: number;
  kind: "parent" | "link";
  resolved: boolean;
}

export interface VaultGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Backlink {
  node_id: number;
  title: string;
  path: string;
  status: Status;
  target: string;
  updated_at: string;
  snippet: string;
}

export interface NoteLink {
  node_id: number;
  title: string;
  path: string;
  status: Status;
  alias: string;
}

export interface UnresolvedLink {
  target: string;
  alias: string;
}

export interface NoteLinks {
  backlinks: Backlink[];
  outlinks: NoteLink[];
  unresolved: UnresolvedLink[];
}

export interface TimelineEvent {
  node_id: number;
  title: string;
  path: string;
  kind: NodeKind;
  activity: "created" | "updated";
  at: string;
  status: Status;
  target: string;
  flag: string;
}

export interface FlagPattern {
  prefix: string;
  pattern_key: string;
  platform: string;
  example: string;
  hint: string;
  category: string;
}

export interface FlagSourceCount {
  prefix: string;
  platform: string;
  count: number;
}

export interface DuplicateFlag {
  flag: string;
  note_count: number;
}

export interface FlagInsights {
  unique_flags: number;
  manual_flags: number;
  detected_flags: number;
  by_source: FlagSourceCount[];
  duplicates: DuplicateFlag[];
  missing_flag_notes: number;
}
