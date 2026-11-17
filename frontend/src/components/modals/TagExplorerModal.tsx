import { useEffect, useMemo, useState } from "react";
import {
  ArrowDownAZ,
  ArrowDownWideNarrow,
  Hash,
  Search,
  Tag,
} from "lucide-react";
import { api } from "../../lib/api";
import { focusFilter } from "../../lib/events";
import type { TagCount } from "../../lib/types";
import { plural } from "../../lib/utils";
import { EmptyState } from "../EmptyState";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

type SortMode = "count" | "name";

/**
 * Browse every tag in the vault with live counts. Selecting a tag narrows
 * the sidebar tree to matching notes (the sidebar filter matches tags), so
 * the explorer doubles as a filter picker.
 */
export function TagExplorerModal() {
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);
  const setFilter = useAppStore((state) => state.setFilter);

  const [tags, setTags] = useState<TagCount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortMode>("count");

  useEffect(() => {
    let cancelled = false;
    api
      .tagCounts()
      .then((items) => {
        if (!cancelled) setTags(items);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load tags");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = needle
      ? tags.filter((item) => item.tag.toLowerCase().includes(needle))
      : tags;
    return [...filtered].sort((a, b) =>
      sort === "count"
        ? b.count - a.count || a.tag.localeCompare(b.tag)
        : a.tag.localeCompare(b.tag),
    );
  }, [tags, query, sort]);

  const applyTag = (tag: string) => {
    setFilter(tag);
    closeModal();
    window.setTimeout(() => focusFilter(), 60);
    toast(`Filtering vault by #${tag}`, "success");
  };

  const totalTagged = useMemo(
    () => tags.reduce((sum, item) => sum + item.count, 0),
    [tags],
  );

  return (
    <Modal
      title="Tag explorer"
      subtitle={
        loading
          ? "Loading tags…"
          : `${plural(tags.length, "tag")} · ${plural(totalTagged, "tagged note")}`
      }
      icon={<Tag />}
      className="tag-explorer-modal"
      bodyClassName="tag-explorer-body"
      label="Tag explorer"
      footer={
        <>
          <span className="modal-hint">
            Click a tag to filter the sidebar; clear with <kbd>Esc</kbd> in the
            filter box.
          </span>
          <span className="grow" />
          <button type="button" className="btn ghost" onClick={closeModal}>
            Close
          </button>
        </>
      }
    >
      <div className="tag-explorer-toolbar">
        <div className="sidebar-search tag-explorer-search">
          <Search />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter tags…"
            spellCheck={false}
            autoComplete="off"
            aria-label="Filter tags"
            autoFocus
          />
        </div>
        <button
          type="button"
          className="icon-btn"
          onClick={() =>
            setSort((current) => (current === "count" ? "name" : "count"))
          }
          title={
            sort === "count"
              ? "Sorted by usage; switch to A–Z"
              : "Sorted A–Z; switch to usage"
          }
          aria-label={sort === "count" ? "Sort by name" : "Sort by usage"}
        >
          {sort === "count" ? <ArrowDownAZ /> : <ArrowDownWideNarrow />}
        </button>
      </div>

      <div className="tag-explorer-list" role="list" aria-busy={loading}>
        {loading ? (
          <div
            className="tag-explorer-loading"
            role="status"
            aria-label="Loading tags"
          >
            {Array.from({ length: 8 }, (_, index) => (
              <div className="skeleton-line tag-skeleton-row" key={index} />
            ))}
          </div>
        ) : error ? (
          <EmptyState
            icon={Hash}
            title="Could not load tags"
            description={error}
            compact
          />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={Hash}
            title={query.trim() ? "No tags match" : "No tags yet"}
            description={
              query.trim()
                ? "Try a different filter."
                : "Add tags to notes — they show up here automatically."
            }
            compact
          />
        ) : (
          visible.map((item) => (
            <button
              key={item.tag}
              type="button"
              role="listitem"
              className="tag-row"
              onClick={() => applyTag(item.tag)}
            >
              <Hash className="tag-hash" aria-hidden="true" />
              <span className="tag-name">{item.tag}</span>
              <span className="tag-count" aria-label={`${item.count} notes`}>
                {item.count}
              </span>
            </button>
          ))
        )}
      </div>
    </Modal>
  );
}
