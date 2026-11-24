/** Saved-search management panel with inline draft validation. */

import { useState } from "react";

import { formatCount, relativeTime } from "../format";
import {
  draftFromSaved,
  isDirty,
  normalizeDraft,
  validateDraft,
} from "../saved";
import type { SavedSearchDraftV2, SavedSearchV2 } from "../types";

export interface SavedSearchManagerProps {
  items: SavedSearchV2[];
  activeId?: string;
  onLoad: (item: SavedSearchV2) => void;
  onSave: (draft: SavedSearchDraftV2) => void;
  onDelete: (id: string) => void;
  onPin?: (id: string) => void;
  currentQuery?: string;
}

const EMPTY_DRAFT: SavedSearchDraftV2 = {
  id: "",
  name: "",
  query: "",
  description: "",
  tags: [],
  pinned: false,
};

export function SavedSearchManager({
  items,
  activeId = "",
  onLoad,
  onSave,
  onDelete,
  onPin,
  currentQuery = "",
}: SavedSearchManagerProps) {
  const [draft, setDraft] = useState<SavedSearchDraftV2>({
    ...EMPTY_DRAFT,
    query: currentQuery,
  });
  const [submitted, setSubmitted] = useState(false);
  const original = items.find((item) => item.id === draft.id);
  const validation = validateDraft(draft);
  const dirty = isDirty(draft, original);

  const submit = () => {
    setSubmitted(true);
    if (!validation.ok) return;
    onSave(normalizeDraft(draft));
    setDraft({ ...EMPTY_DRAFT, query: currentQuery });
    setSubmitted(false);
  };

  return (
    <section className="si-saved" data-testid="search-saved-manager">
      <h3>Saved searches</h3>
      <ul className="si-saved__list">
        {items.map((item) => (
          <li
            className="si-saved__item"
            data-active={item.id === activeId}
            data-testid="search-saved-item"
            key={item.id}
          >
            <button
              className="si-button si-button--link v3-focusable"
              onClick={() => onLoad(item)}
              type="button"
            >
              {item.pinned ? "★ " : ""}
              {item.name}
            </button>
            <code className="si-saved__query">{item.query}</code>
            <span className="si-saved__meta">
              used {formatCount(item.use_count)} ·{" "}
              {relativeTime(item.updated_at)}
            </span>
            <span className="si-saved__actions">
              <button
                aria-label={`Edit ${item.name}`}
                className="si-button si-button--tiny v3-focusable"
                onClick={() => setDraft(draftFromSaved(item))}
                type="button"
              >
                Edit
              </button>
              {onPin && (
                <button
                  aria-label={`Pin ${item.name}`}
                  className="si-button si-button--tiny v3-focusable"
                  onClick={() => onPin(item.id)}
                  type="button"
                >
                  {item.pinned ? "Unpin" : "Pin"}
                </button>
              )}
              <button
                aria-label={`Delete ${item.name}`}
                className="si-button si-button--tiny v3-focusable"
                data-testid="search-saved-delete"
                onClick={() => onDelete(item.id)}
                type="button"
              >
                Delete
              </button>
            </span>
          </li>
        ))}
        {!items.length && (
          <li className="si-saved__empty">No saved searches yet.</li>
        )}
      </ul>
      <form
        className="si-saved__form"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <label>
          Name
          <input
            aria-label="Saved search name"
            className="si-input v3-focusable"
            data-testid="search-saved-name"
            onChange={(event) =>
              setDraft({ ...draft, name: event.target.value })
            }
            value={draft.name}
          />
        </label>
        {submitted && validation.errors.name && (
          <span className="si-saved__error">{validation.errors.name}</span>
        )}
        <label>
          Query
          <input
            aria-label="Saved search query"
            className="si-input v3-focusable"
            data-testid="search-saved-query"
            onChange={(event) =>
              setDraft({ ...draft, query: event.target.value })
            }
            value={draft.query}
          />
        </label>
        {submitted && validation.errors.query && (
          <span className="si-saved__error">{validation.errors.query}</span>
        )}
        <label>
          Tags (comma separated)
          <input
            aria-label="Saved search tags"
            className="si-input v3-focusable"
            onChange={(event) =>
              setDraft({
                ...draft,
                tags: event.target.value
                  .split(",")
                  .map((tag) => tag.trim())
                  .filter(Boolean),
              })
            }
            value={draft.tags.join(", ")}
          />
        </label>
        <button
          className="si-button v3-focusable"
          data-testid="search-saved-submit"
          disabled={submitted && !validation.ok}
          type="submit"
        >
          {original ? (dirty ? "Update" : "Unchanged") : "Save query"}
        </button>
      </form>
    </section>
  );
}
