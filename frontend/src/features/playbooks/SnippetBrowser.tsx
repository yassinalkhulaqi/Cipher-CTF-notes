import { useMemo, useState } from "react";
import { Button } from "../../ui/Button";
import { EmptyState } from "../../ui/EmptyState";
import { Field } from "../../ui/Field";
import { Toolbar } from "../../ui/Toolbar";
import { filterSnippets, snippetFamilies } from "./helpers";
import type { SnippetRecord, SnippetUsage } from "./types";

export interface SnippetBrowserProps {
  snippets: SnippetRecord[];
  onUse: (key: string) => void;
  onCompose: (keys: string[]) => void;
  usage: SnippetUsage | null;
}

export function SnippetBrowser({
  snippets,
  onUse,
  onCompose,
  usage,
}: SnippetBrowserProps) {
  const [query, setQuery] = useState("");
  const [family, setFamily] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [tagDraft, setTagDraft] = useState("");

  const families = useMemo(() => snippetFamilies(snippets), [snippets]);
  const tags = useMemo(() => {
    const values = new Set<string>();
    for (const snippet of snippets) {
      for (const tag of snippet.tags) values.add(tag.toLocaleLowerCase());
    }
    return Array.from(values).sort();
  }, [snippets]);
  const wantedTags = useMemo(
    () =>
      tagDraft
        .split(/[\s,]+/)
        .map((tag) => tag.trim())
        .filter(Boolean),
    [tagDraft],
  );
  const visible = useMemo(
    () =>
      filterSnippets(snippets, query, wantedTags).filter((snippet) => {
        if (!family) return true;
        return (snippet.key.split(/[-_]/)[0] || "other") === family;
      }),
    [snippets, query, wantedTags, family],
  );

  const toggle = (key: string) => {
    setSelected((current) =>
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key],
    );
  };

  return (
    <section className="pb-snippets" aria-label="Snippet browser">
      <div className="pb-snippets__filters">
        <Field
          label="Search snippets"
          placeholder="nmap, smb, whois"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Field
          label="Tags"
          placeholder="recon network"
          value={tagDraft}
          onChange={(event) => setTagDraft(event.target.value)}
        />
        <label className="pb-field">
          <span>Family</span>
          <select
            value={family}
            onChange={(event) => setFamily(event.target.value)}
          >
            <option value="">All families</option>
            {Array.from(families.keys()).map((name) => (
              <option key={name} value={name}>
                {name} ({families.get(name)})
              </option>
            ))}
          </select>
        </label>
      </div>

      {tags.length > 0 ? (
        <Toolbar label="Snippet tags">
          {tags.map((tag) => (
            <Button
              key={tag}
              size="sm"
              variant={wantedTags.includes(tag) ? "primary" : "ghost"}
              onClick={() =>
                setTagDraft(
                  wantedTags.includes(tag)
                    ? wantedTags.filter((item) => item !== tag).join(" ")
                    : [...wantedTags, tag].join(" "),
                )
              }
            >
              #{tag}
            </Button>
          ))}
        </Toolbar>
      ) : null}

      {selected.length > 0 ? (
        <div className="pb-snippets__compose">
          <span>{selected.length} selected</span>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onCompose(selected)}
          >
            Compose command
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
            Clear
          </Button>
        </div>
      ) : null}

      {usage ? (
        <div className="pb-snippets__usage">
          <code>{usage.command}</code>
          {usage.warnings.length > 0 ? (
            <span className="pb-muted">
              {usage.warnings.map((item) => item.message).join(" · ")}
            </span>
          ) : null}
        </div>
      ) : null}

      {visible.length === 0 ? (
        <EmptyState
          title="No snippets match"
          description="Change the query or clear filters."
        />
      ) : (
        <div className="pb-snippet-grid">
          {visible.map((snippet) => (
            <article className="pb-snippet" key={snippet.key}>
              <header>
                <strong>{snippet.title}</strong>
                <code>{snippet.key}</code>
              </header>
              <p>{snippet.description || "No description"}</p>
              <pre>{snippet.command}</pre>
              <div className="pb-chip-row">
                {snippet.tags.map((tag) => (
                  <span className="pb-chip pb-chip--muted" key={tag}>
                    #{tag}
                  </span>
                ))}
              </div>
              <div className="pb-snippet__actions">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => onUse(snippet.key)}
                >
                  Use
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => toggle(snippet.key)}
                >
                  {selected.includes(snippet.key) ? "Deselect" : "Select"}
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
