/** Saved-search draft validation and ordering. */

import type { SavedSearchDraftV2, SavedSearchV2 } from "./types";

export function draftFromSaved(item: SavedSearchV2): SavedSearchDraftV2 {
  return {
    id: item.id,
    name: item.name,
    query: item.query,
    description: item.description,
    tags: [...item.tags],
    pinned: item.pinned,
  };
}

export interface DraftValidation {
  ok: boolean;
  errors: Record<string, string>;
}

export function validateDraft(draft: SavedSearchDraftV2): DraftValidation {
  const errors: Record<string, string> = {};
  const name = draft.name.trim();
  if (!name) errors.name = "Name is required.";
  else if (name.length > 80)
    errors.name = "Name must be 80 characters or fewer.";
  if (!draft.query.trim()) errors.query = "Query is required.";
  else if (draft.query.length > 500) {
    errors.query = "Query must be 500 characters or fewer.";
  }
  if (draft.description.length > 240) {
    errors.description = "Description must be 240 characters or fewer.";
  }
  if (draft.tags.length > 12) errors.tags = "Use at most 12 tags.";
  if (draft.tags.some((tag) => !tag.trim()))
    errors.tags = "Tags cannot be blank.";
  return { ok: Object.keys(errors).length === 0, errors };
}

export function normalizeDraft(draft: SavedSearchDraftV2): SavedSearchDraftV2 {
  return {
    ...draft,
    id: draft.id.trim(),
    name: draft.name.trim(),
    query: draft.query.trim(),
    description: draft.description.trim(),
    tags: [
      ...new Set(
        draft.tags.map((tag) => tag.trim().toLowerCase()).filter(Boolean),
      ),
    ],
  };
}

export function sortSaved(items: SavedSearchV2[]): SavedSearchV2[] {
  return [...items].sort(
    (a, b) =>
      Number(b.pinned) - Number(a.pinned) ||
      b.use_count - a.use_count ||
      b.updated_at - a.updated_at ||
      a.name.toLowerCase().localeCompare(b.name.toLowerCase()) ||
      a.id.localeCompare(b.id),
  );
}

export function filterSaved(
  items: SavedSearchV2[],
  needle: string,
  tag = "",
): SavedSearchV2[] {
  const folded = needle.trim().toLowerCase();
  const chosen = tag.trim().toLowerCase();
  return items.filter((item) => {
    if (chosen && !item.tags.some((value) => value.toLowerCase() === chosen)) {
      return false;
    }
    if (!folded) return true;
    return `${item.name} ${item.description} ${item.query} ${item.tags.join(" ")}`
      .toLowerCase()
      .includes(folded);
  });
}

export function savedSummary(item: SavedSearchV2): string {
  const description = item.description || "No description";
  const tags = item.tags.length ? ` · ${item.tags.join(", ")}` : "";
  return `${item.name}: ${description}${tags}`;
}

export function savedTags(items: SavedSearchV2[]): string[] {
  return [...new Set(items.flatMap((item) => item.tags))].sort((a, b) =>
    a.localeCompare(b),
  );
}

export function mergeSaved(
  current: SavedSearchV2[],
  incoming: SavedSearchV2[],
): SavedSearchV2[] {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return sortSaved([...byId.values()]);
}

export function isDirty(
  draft: SavedSearchDraftV2,
  original: SavedSearchV2 | undefined,
): boolean {
  if (!original) return true;
  return (
    draft.name !== original.name ||
    draft.query !== original.query ||
    draft.description !== original.description ||
    draft.pinned !== original.pinned ||
    draft.tags.join("\u0000") !== original.tags.join("\u0000")
  );
}
