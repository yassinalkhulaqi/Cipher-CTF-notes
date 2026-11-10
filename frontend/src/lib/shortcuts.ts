export interface Shortcut {
  keys: string[];
  label: string;
  detail?: string;
}

export interface ShortcutGroup {
  title: string;
  items: Shortcut[];
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "Navigate",
    items: [
      {
        keys: ["Ctrl", "P"],
        label: "Quick switch",
        detail: "Fuzzy jump to any note",
      },
      { keys: ["Ctrl", "Shift", "F"], label: "Full-text search" },
      { keys: ["Ctrl", "Shift", "D"], label: "Dashboard" },
      { keys: ["Ctrl", "Shift", "S"], label: "Snippet library" },
      { keys: ["Ctrl", "Shift", "G"], label: "Vault graph" },
      {
        keys: ["Ctrl", "Shift", "T"],
        label: "Timeline",
        detail: "Recent vault activity",
      },
      { keys: ["Ctrl", "Shift", "Q"], label: "Quick capture" },
      { keys: ["Ctrl", "Shift", "I"], label: "Flag intelligence" },
      { keys: ["F1"], label: "Keyboard shortcuts" },
    ],
  },
  {
    title: "Notes",
    items: [
      {
        keys: ["Ctrl", "N"],
        label: "New note",
        detail: "Uses the last template",
      },
      { keys: ["Ctrl", "Shift", "N"], label: "New folder" },
      { keys: ["Ctrl", "S"], label: "Save now" },
      { keys: ["Ctrl", "Shift", "P"], label: "Pin or unpin note" },
      {
        keys: ["F2"],
        label: "Note properties",
        detail: "In the vault tree, F2 renames the focused item",
      },
      { keys: ["Delete"], label: "Move selection to trash" },
      { keys: ["Ctrl", "↑"], label: "Move note up" },
      { keys: ["Ctrl", "↓"], label: "Move note down" },
    ],
  },
  {
    title: "Workspace",
    items: [
      { keys: ["Ctrl", "E"], label: "Cycle editor, split, and preview" },
      { keys: ["Ctrl", "Shift", "J"], label: "Toggle note inspector" },
      { keys: ["Ctrl", "Shift", "B"], label: "Collapse or expand sidebar" },
      { keys: ["Ctrl", ","], label: "Settings" },
      { keys: ["Ctrl", "Shift", "L"], label: "Toggle focus mode" },
      { keys: ["Esc"], label: "Close dialog or command palette" },
    ],
  },
  {
    title: "Editor",
    items: [
      {
        keys: ["Ctrl", "F"],
        label: "Find in note",
        detail: "Search the open note",
      },
      {
        keys: ["Ctrl", "H"],
        label: "Find and replace",
        detail: "Replace text in the open note",
      },
      { keys: ["Ctrl", "B"], label: "Bold" },
      { keys: ["Ctrl", "I"], label: "Italic" },
      { keys: ["Ctrl", "K"], label: "Inline code" },
      { keys: ["Ctrl", "Shift", "X"], label: "Strikethrough" },
      { keys: ["Tab"], label: "Indent selection" },
      { keys: ["Shift", "Tab"], label: "Outdent selection" },
      { keys: ["Enter"], label: "Continue lists automatically" },
    ],
  },
];

export const COMMAND_SHORTCUTS: Shortcut[] = SHORTCUT_GROUPS.flatMap(
  (group) => group.items,
);
