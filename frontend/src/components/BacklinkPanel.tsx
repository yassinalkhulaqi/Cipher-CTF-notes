import { useCallback, useEffect, useState } from "react";
import { ArrowUpLeft, Link2, Link2Off, Unlink } from "lucide-react";
import { api } from "../lib/api";
import type { NoteLinks } from "../lib/types";
import { useAppStore } from "../store/useAppStore";
import { useUiStore } from "../store/useUiStore";

export function BacklinkPanel({ noteId }: { noteId: number }) {
  const openNote = useAppStore((state) => state.openNote);
  const toast = useUiStore((state) => state.toast);

  const [links, setLinks] = useState<NoteLinks | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((id: number) => {
    let cancelled = false;
    api
      .backlinks(id)
      .then((data) => {
        if (cancelled) return;
        setError(null);
        setLinks(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLinks(null);
        setError(
          err instanceof Error ? err.message : "Could not load backlinks",
        );
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(noteId), [noteId, load]);

  const open = (id: number) => {
    void openNote(id).catch((err: unknown) =>
      toast(
        err instanceof Error ? err.message : "Could not open note",
        "error",
      ),
    );
  };

  if (error) {
    return (
      <div className="backlinks backlinks-error" role="status">
        <Unlink />
        <span>{error}</span>
      </div>
    );
  }

  if (!links) {
    return <div className="backlinks" aria-busy="true" />;
  }

  const total =
    links.backlinks.length + links.outlinks.length + links.unresolved.length;
  if (total === 0) {
    return (
      <div className="backlinks" aria-label="No links for this note">
        <span className="backlinks-hint">
          <Link2Off />
          No links yet. Use <code>[[Note Title]]</code> to connect notes.
        </span>
      </div>
    );
  }

  return (
    <div className="backlinks" aria-label="Note links">
      {links.backlinks.length > 0 ? (
        <section className="backlinks-group">
          <h3>
            <ArrowUpLeft />
            Backlinks · {links.backlinks.length}
          </h3>
          <ul className="backlinks-list">
            {links.backlinks.map((link) => (
              <li key={link.node_id}>
                <button
                  type="button"
                  className="backlinks-row"
                  onClick={() => open(link.node_id)}
                  title={link.path ? `in ${link.path}` : undefined}
                >
                  <span className="backlinks-title">{link.title}</span>
                  {link.snippet ? (
                    <span className="backlinks-snippet">{link.snippet}</span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {links.outlinks.length > 0 ? (
        <section className="backlinks-group">
          <h3>
            <Link2 />
            Links from here · {links.outlinks.length}
          </h3>
          <div className="backlinks-chips">
            {links.outlinks.map((link) => (
              <button
                key={link.node_id}
                type="button"
                className="chip tag"
                onClick={() => open(link.node_id)}
                title={link.path ? `in ${link.path}` : undefined}
              >
                {link.alias || link.title}
              </button>
            ))}
          </div>
        </section>
      ) : null}
      {links.unresolved.length > 0 ? (
        <section className="backlinks-group">
          <h3 className="backlinks-warn">
            <Unlink />
            Unresolved · {links.unresolved.length}
          </h3>
          <div className="backlinks-chips">
            {links.unresolved.map((link) => (
              <span
                key={link.target}
                className="chip add"
                title="No note with this title exists yet"
              >
                {link.alias || link.target}
              </span>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
