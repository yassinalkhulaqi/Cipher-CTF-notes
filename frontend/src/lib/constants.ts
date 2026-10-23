import type { Difficulty, Status, ViewMode } from "./types";

export const PRODUCT = "RedScribe";
export const TAGLINE = "Local-first notes for CTFs, pentests, and security research.";

export const STATUSES: Status[] = ["todo", "active", "done", "blocked"];

export const STATUS_LABEL: Record<Status, string> = {
  todo: "Open",
  active: "Active",
  done: "Done",
  blocked: "Blocked",
};

export const STATUS_HINT: Record<Status, string> = {
  todo: "Not started yet",
  active: "Work in progress",
  done: "Completed",
  blocked: "Waiting on something",
};

export const DIFFICULTIES: { value: Difficulty; label: string }[] = [
  { value: "", label: "Unrated" },
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
  { value: "insane", label: "Insane" },
];

export const VIEW_MODES: { value: ViewMode; label: string }[] = [
  { value: "editor", label: "Editor" },
  { value: "split", label: "Split" },
  { value: "preview", label: "Preview" },
];

export const FONT_SIZES = Array.from({ length: 10 }, (_, index) => index + 9);

export const DEFAULT_SIDEBAR_WIDTH = 288;
export const MIN_SIDEBAR_WIDTH = 220;
export const MAX_SIDEBAR_WIDTH = 480;
export const DEFAULT_SPLIT = 50;
export const MIN_SPLIT = 25;
export const MAX_SPLIT = 80;

export const STARTER_SNIPPETS = [
  { title: "Quick note", template: "blank" },
  { title: "CTF challenge", template: "ctf" },
  { title: "Host recon", template: "host" },
];
