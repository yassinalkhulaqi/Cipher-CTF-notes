import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  Code2,
  Copy,
  Pencil,
  Plus,
  Search,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { api } from "../../lib/api";
import type { Snippet } from "../../lib/types";
import { copyText, plural } from "../../lib/utils";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

const SNIPPETS_CHANGED = "redscribe:snippets-changed";

function snippetKey(snippet: Snippet): string {
  return snippet.builtin
    ? `builtin:${snippet.builtin_key}`
    : `custom:${snippet.id}`;
}

function categoryOf(snippet: Snippet): string {
  return snippet.tag_list[0] ?? "misc";
}

function renderCommand(command: string): ReactNode {
  return command.split(/(\{\{[^}]+\}\})/g).map((part, index) =>
    /^\{\{[^}]+\}\}$/.test(part) ? (
      <span className="ph" key={`${part}-${index}`}>
        {part}
      </span>
    ) : (
      part
    ),
  );
}

export function SnippetsModal() {
  const note = useAppStore((state) => state.note);
  const draft = useAppStore((state) => state.draft);
  const setDraft = useAppStore((state) => state.setDraft);
  const openSnippetForm = useUiStore((state) => state.openSnippetForm);
  const askConfirm = useUiStore((state) => state.askConfirm);
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);

  const [snippets, setSnippets] = useState<Snippet[]>([]);
  const [filter, setFilter] = useState("");
  const [category, setCategory] = useState("all");
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api
      .listSnippets()
      .then((items) => setSnippets(items))
      .catch((error: unknown) =>
        toast(
          error instanceof Error ? error.message : "Could not load snippets",
          "error",
        ),
      )
      .finally(() => setLoading(false));
  }, [toast]);

  useEffect(() => {
    load();
    const reload = () => load();
    window.addEventListener(SNIPPETS_CHANGED, reload);
    return () => window.removeEventListener(SNIPPETS_CHANGED, reload);
  }, [load]);

  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const snippet of snippets) {
      const key = categoryOf(snippet);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [
      { key: "all", count: snippets.length },
      ...Array.from(counts.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, count]) => ({ key, count })),
    ];
  }, [snippets]);

  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return snippets.filter((snippet) => {
      if (category !== "all" && categoryOf(snippet) !== category) return false;
      if (!needle) return true;
      return `${snippet.title} ${snippet.command} ${snippet.description} ${snippet.tags}`
        .toLowerCase()
        .includes(needle);
    });
  }, [snippets, filter, category]);

  useEffect(() => {
    if (filtered.length === 0) {
      setSelectedKey(null);
      return;
    }
    if (!filtered.some((snippet) => snippetKey(snippet) === selectedKey)) {
      setSelectedKey(snippetKey(filtered[0] as Snippet));
    }
  }, [filtered, selectedKey]);

  const current =
    filtered.find((snippet) => snippetKey(snippet) === selectedKey) ??
    filtered[0] ??
    null;

  const copyRaw = () => {
    if (!current) return;
    void copyText(current.command).then(
      () => toast("Command copied", "success"),
      () => toast("Could not copy the command", "error"),
    );
  };

  const copyResolved = async () => {
    if (!current) return;
    try {
      const resolved = await api.resolveSnippet(
        current.command,
        note?.target ?? "",
      );
      await copyText(resolved.command);
      toast("Resolved command copied", "success");
    } catch (error) {
      toast(
        error instanceof Error
          ? error.message
          : "Could not resolve the snippet",
        "error",
      );
    }
  };

  const insert = async () => {
    if (!current) return;
    if (!note) {
      toast("Open a note before inserting a snippet", "error");
      return;
    }
    try {
      const resolved = await api.resolveSnippet(
        current.command,
        note.target ?? "",
      );
      const prefix = draft.trimEnd();
      setDraft(
        prefix ? `${prefix}\n\n${resolved.command}\n` : `${resolved.command}\n`,
      );
      closeModal();
      toast("Inserted into note", "success");
    } catch (error) {
      toast(
        error instanceof Error ? error.message : "Could not insert the snippet",
        "error",
      );
    }
  };

  const remove = () => {
    if (!current || current.id === null) return;
    const id = current.id;
    askConfirm({
      title: "Delete snippet",
      message: `Delete “${current.title}”? This cannot be undone.`,
      confirmLabel: "Delete snippet",
      danger: true,
      action: async () => {
        try {
          await api.deleteSnippet(id);
          window.dispatchEvent(new Event(SNIPPETS_CHANGED));
          toast("Snippet deleted", "success");
        } catch (error) {
          toast(
            error instanceof Error ? error.message : "Could not delete snippet",
            "error",
          );
        }
      },
    });
  };

  return (
    <Modal
      title="Snippet library"
      subtitle={`${plural(snippets.length, "command")}`}
      icon={<Code2 />}
      className="snippets-modal"
      bodyClassName="snippets-layout"
      label="Snippet library"
    >
      <aside className="snippets-side">
        <div className="snippets-filter">
          <div className="tag-input-wrap">
            <div className="sidebar-search" style={{ margin: 0, flex: 1 }}>
              <Search />
              <input
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Filter…"
                spellCheck={false}
                autoComplete="off"
                aria-label="Filter snippets"
              />
            </div>
            <button
              type="button"
              className="icon-btn sm"
              onClick={() => openSnippetForm(null)}
              title="New snippet"
              aria-label="New snippet"
            >
              <Plus />
            </button>
          </div>
        </div>
        <div className="snippet-cats">
          {categories.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`snippet-cat ${category === item.key ? "selected" : ""}`}
              onClick={() => setCategory(item.key)}
            >
              {item.key === "all" ? "All snippets" : item.key}
              <span className="count">{item.count}</span>
            </button>
          ))}
        </div>
      </aside>

      <div className="snippets-main">
        <div className="snippet-list">
          {loading ? (
            <div className="tree-skeleton">
              <span style={{ width: "70%" }} />
              <span style={{ width: "52%" }} />
              <span style={{ width: "61%" }} />
            </div>
          ) : filtered.length === 0 ? (
            <div className="empty">
              <Search />
              <div>
                <strong>No snippets found</strong>
                <br />
                Try another filter or create a custom snippet.
              </div>
              <button
                type="button"
                className="btn ghost tiny"
                onClick={() => openSnippetForm(null)}
              >
                <Plus /> New snippet
              </button>
            </div>
          ) : (
            filtered.map((snippet) => {
              const key = snippetKey(snippet);
              return (
                <button
                  key={key}
                  type="button"
                  className={`snippet-item ${current && snippetKey(current) === key ? "selected" : ""}`}
                  onClick={() => setSelectedKey(key)}
                >
                  <span className="si-title">
                    {snippet.builtin ? <Sparkles /> : <Code2 />}
                    {snippet.title}
                  </span>
                  <span className="si-command">{snippet.command}</span>
                </button>
              );
            })
          )}
        </div>

        <div className="snippet-detail">
          {current ? (
            <>
              <div className="sd-title">{current.title}</div>
              <div className="sd-desc">
                {current.description || "No description for this snippet."}
              </div>
              <pre className="sd-cmd">{renderCommand(current.command)}</pre>
              <div className="chips" style={{ marginTop: 10 }}>
                {current.tag_list.map((tag) => (
                  <span className="chip tag" key={tag}>
                    {tag}
                  </span>
                ))}
                {current.builtin ? (
                  <span className="chip">Built-in</span>
                ) : null}
              </div>
              <div className="sd-actions">
                <button
                  type="button"
                  className="btn ghost sm"
                  onClick={copyRaw}
                >
                  <Copy /> Copy
                </button>
                <button
                  type="button"
                  className="btn ghost sm"
                  onClick={() => void copyResolved()}
                >
                  <Wand2 /> Resolve
                </button>
                <button
                  type="button"
                  className="btn primary sm"
                  onClick={() => void insert()}
                >
                  <Plus /> Insert
                </button>
                {!current.builtin ? (
                  <>
                    <button
                      type="button"
                      className="icon-btn sm"
                      onClick={() => openSnippetForm(current.id)}
                      title="Edit snippet"
                      aria-label="Edit snippet"
                    >
                      <Pencil />
                    </button>
                    <button
                      type="button"
                      className="icon-btn sm"
                      onClick={remove}
                      title="Delete snippet"
                      aria-label="Delete snippet"
                    >
                      <Trash2 />
                    </button>
                  </>
                ) : null}
              </div>
              {!note ? (
                <div className="modal-hint" style={{ marginTop: 10 }}>
                  Open a note to insert this command with its target filled in.
                </div>
              ) : null}
            </>
          ) : (
            <div className="empty">
              <Code2 />
              <div>Select a snippet to preview its command.</div>
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
}
