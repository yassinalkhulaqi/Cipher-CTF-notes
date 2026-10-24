import { useEffect, useState, type KeyboardEvent, type ReactNode } from "react";
import { FileText, Search } from "lucide-react";
import { api } from "../../lib/api";
import type { SearchHit } from "../../lib/types";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

function renderSnippet(snippet: string): ReactNode {
  const parts: ReactNode[] = [];
  const pattern = /\[([^\]]+)\]/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(snippet)) !== null) {
    if (match.index > cursor) parts.push(snippet.slice(cursor, match.index));
    parts.push(<mark key={`${match.index}-${match[1]}`}>{match[1]}</mark>);
    cursor = match.index + match[0].length;
  }
  if (cursor < snippet.length) parts.push(snippet.slice(cursor));
  return parts.length > 0 ? parts : snippet;
}

export function SearchModal() {
  const openNote = useAppStore((state) => state.openNote);
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchHit[]>([]);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const text = query.trim();
    if (!text) {
      setResults([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(() => {
      api
        .search(text)
        .then((hits) => {
          if (!cancelled) {
            setResults(hits);
            setSelected(0);
          }
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  useEffect(() => {
    document
      .querySelector(".search-hit.selected")
      ?.scrollIntoView({ block: "nearest" });
  }, [selected]);

  const execute = (hit: SearchHit | undefined) => {
    if (!hit) return;
    closeModal();
    void openNote(hit.node_id).catch((error: unknown) =>
      toast(
        error instanceof Error ? error.message : "Could not open note",
        "error",
      ),
    );
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSelected((current) =>
        results.length ? (current + 1) % results.length : 0,
      );
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setSelected((current) =>
        results.length ? (current - 1 + results.length) % results.length : 0,
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      execute(results[selected]);
    }
  };

  const trimmed = query.trim();

  return (
    <Modal
      size="palette"
      label="Full-text search"
      hideClose
      bodyClassName="palette-body"
      footer={
        <>
          <span className="modal-hint">
            <kbd>↑</kbd>
            <kbd>↓</kbd> navigate
          </span>
          <span className="modal-hint">
            <kbd>↵</kbd> open
          </span>
          <span className="modal-hint">
            <kbd>Esc</kbd> close
          </span>
        </>
      }
    >
      <div className="palette-input-row">
        <Search />
        <input
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search the body of every note…"
          spellCheck={false}
          autoComplete="off"
          aria-label="Full-text search"
        />
        {loading ? <span className="modal-hint">Searching…</span> : null}
      </div>
      <div className="palette-list">
        {!trimmed ? (
          <div className="palette-empty">
            Full-text search runs against the local SQLite index.
            <br />
            Start typing to search every note.
          </div>
        ) : results.length > 0 ? (
          <>
            <div className="list-label">
              {results.length} {results.length === 1 ? "result" : "results"}
            </div>
            {results.map((hit, index) => (
              <button
                key={hit.node_id}
                type="button"
                className={`search-hit ${selected === index ? "selected" : ""}`}
                onMouseMove={() => setSelected(index)}
                onClick={() => execute(hit)}
              >
                <span className="sh-title">
                  <FileText size={13} />
                  {hit.title}
                </span>
                <span className="sh-path">{hit.path || "Vault root"}</span>
                <span className="sh-snippet">{renderSnippet(hit.snippet)}</span>
              </button>
            ))}
          </>
        ) : loading ? (
          <div className="palette-empty">Searching the vault…</div>
        ) : (
          <div className="palette-empty">
            No notes contain “{trimmed}”.
            <br />
            Try a shorter phrase or a different spelling.
          </div>
        )}
      </div>
    </Modal>
  );
}
