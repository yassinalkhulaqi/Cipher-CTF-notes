import { foldText } from "./query";
import type {
  SavedQuery,
  SavedQueryDraft,
  SavedQueryValidation,
} from "./types";

export function draftFromSaved(item: SavedQuery): SavedQueryDraft {
  return {
    id: item.id,
    name: item.name,
    query: item.query,
    description: item.description,
    tags: [...item.tags],
    pinned: item.pinned,
  };
}

export function validateSavedDraft(
  draft: SavedQueryDraft,
): SavedQueryValidation {
  const errors: Record<string, string> = {};
  if (!draft.name.trim()) errors.name = "Name is required.";
  if (draft.name.length > 80)
    errors.name = "Name must be 80 characters or fewer.";
  if (!draft.query.trim()) errors.query = "Query is required.";
  if (draft.query.length > 500)
    errors.query = "Query must be 500 characters or fewer.";
  if (draft.description.length > 300) {
    errors.description = "Description must be 300 characters or fewer.";
  }
  if (draft.tags.length > 20) errors.tags = "Use at most 20 tags.";
  if (draft.tags.some((tag) => !tag.trim())) {
    errors.tags = "Tags cannot be blank.";
  }
  return { ok: Object.keys(errors).length === 0, errors };
}

export function normalizeDraft(draft: SavedQueryDraft): SavedQueryDraft {
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

export function sortSaved(items: SavedQuery[]): SavedQuery[] {
  return [...items].sort(
    (a, b) =>
      Number(b.pinned) - Number(a.pinned) ||
      b.use_count - a.use_count ||
      b.updated_at.localeCompare(a.updated_at) ||
      a.name.localeCompare(b.name),
  );
}

export function filterSaved(
  items: SavedQuery[],
  needle: string,
  tag?: string,
): SavedQuery[] {
  const query = foldText(needle);
  const selected = tag?.trim().toLowerCase() ?? "";
  return items.filter((item) => {
    if (
      selected &&
      !item.tags.some((value) => value.toLowerCase() === selected)
    ) {
      return false;
    }
    if (!query) return true;
    return foldText(
      `${item.name} ${item.description} ${item.query} ${item.tags.join(" ")}`,
    ).includes(query);
  });
}

export function groupSaved(items: SavedQuery[]): Map<string, SavedQuery[]> {
  const groups = new Map<string, SavedQuery[]>();
  for (const item of sortSaved(items)) {
    const keys = item.pinned
      ? ["Pinned"]
      : item.tags.length
        ? item.tags
        : ["Untagged"];
    for (const key of keys) {
      const bucket = groups.get(key) ?? [];
      bucket.push(item);
      groups.set(key, bucket);
    }
  }
  return groups;
}

export function savedSummary(item: SavedQuery): string {
  const description = item.description || "No description";
  const tags = item.tags.length ? ` · ${item.tags.join(", ")}` : "";
  return `${item.name}: ${description}${tags}`;
}

export function savedTags(items: SavedQuery[]): string[] {
  return [...new Set(items.flatMap((item) => item.tags))].sort((a, b) =>
    a.localeCompare(b),
  );
}

export function matchesDraft(draft: SavedQueryDraft, needle: string): boolean {
  return foldText(`${draft.name} ${draft.description} ${draft.query}`).includes(
    foldText(needle),
  );
}

export function mergeSaved(
  current: SavedQuery[],
  incoming: SavedQuery[],
): SavedQuery[] {
  const byId = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) byId.set(item.id, item);
  return sortSaved([...byId.values()]);
}

export function suggestSavedQueries(
  items: SavedQuery[],
  text: string,
  limit = 6,
): SavedQuery[] {
  const needle = foldText(text);
  if (!needle)
    return sortSaved(items)
      .filter((item) => item.pinned)
      .slice(0, limit);
  return sortSaved(items)
    .filter((item) => matchesDraft(draftFromSaved(item), needle))
    .slice(0, limit);
}

export function savedToCommand(item: SavedQuery): string {
  return `/search ${item.query}`;
}

export function draftIsDirty(
  draft: SavedQueryDraft,
  original: SavedQuery | undefined,
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
