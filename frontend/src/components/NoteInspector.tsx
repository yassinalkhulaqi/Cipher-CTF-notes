import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Clock3,
  Copy,
  Flag,
  Folder,
  Link2,
  ListTree,
  Pencil,
  SlidersHorizontal,
  Tag,
  Target,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import { STATUS_LABEL } from "../lib/constants";
import { flagFormat } from "../lib/flags";
import { extractOutline } from "../lib/outline";
import type { FlagPattern, NodeDetail } from "../lib/types";
import { copyText, formatDate, plural, relativeTime, wordCount } from "../lib/utils";
import { readingTime } from "../lib/ux";
import { useAppStore } from "../store/useAppStore";
import { useUiStore, type InspectorTab } from "../store/useUiStore";
import { BacklinkPanel } from "./BacklinkPanel";
import { StatusIcon } from "./StatusIcon";

interface NoteInspectorProps {
  note: NodeDetail;
  draft: string;
  onRevealLine: (line: number) => void;
}

const TABS: Array<{
  id: InspectorTab;
  label: string;
  icon: typeof ListTree;
}> = [
  { id: "outline", label: "Outline", icon: ListTree },
  { id: "links", label: "Links", icon: Link2 },
  { id: "properties", label: "Properties", icon: SlidersHorizontal },
];

export function NoteInspector({
  note,
  draft,
  onRevealLine,
}: NoteInspectorProps) {
  const setFilter = useAppStore((state) => state.setFilter);
  const setMobileSidebar = useUiStore((state) => state.setMobileSidebar);
  const openModal = useUiStore((state) => state.openModal);
  const toast = useUiStore((state) => state.toast);
  const tab = useUiStore((state) => state.inspectorTab);
  const setTab = useUiStore((state) => state.setInspectorTab);
  const setInspectorOpen = useUiStore((state) => state.setInspectorOpen);

  const [patterns, setPatterns] = useState<FlagPattern[]>([]);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .flagPatterns()
      .then((items) => {
        if (!cancelled) setPatterns(items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const outline = useMemo(() => extractOutline(draft), [draft]);
  const format = useMemo(
    () => flagFormat(note.flag, patterns),
    [note.flag, patterns],
  );
  const words = wordCount(draft);

  const copy = (value: string, label: string) => {
    void copyText(value).then(
      () => {
        setCopied(true);
        toast(`${label} copied`, "success");
      },
      () => toast(`Could not copy ${label.toLowerCase()}`, "error"),
    );
  };

  const filterByTag = (tag: string) => {
    setFilter(tag);
    setMobileSidebar(true);
  };

  return (
    <aside className="inspector" aria-label="Note inspector">
      <div className="inspector-head">
        <span className="inspector-title">Inspector</span>
        <button
          type="button"
          className="icon-btn sm"
          onClick={() => setInspectorOpen(false)}
          title="Close inspector"
          aria-label="Close inspector"
        >
          <X />
        </button>
      </div>

      <div className="inspector-tabs" role="tablist" aria-label="Inspector sections">
        {TABS.map((item) => {
          const Icon = item.icon;
          const active = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`inspector-tab-${item.id}`}
              aria-selected={active}
              aria-controls={`inspector-panel-${item.id}`}
              className={active ? "active" : ""}
              onClick={() => setTab(item.id)}
            >
              <Icon />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      <div
        className="inspector-body"
        role="tabpanel"
        id={`inspector-panel-${tab}`}
        aria-labelledby={`inspector-tab-${tab}`}
      >
        {tab === "outline" ? (
          outline.length ? (
            <div className="outline-list">
              {outline.map((item) => (
                <button
                  key={`${item.line}-${item.text}`}
                  type="button"
                  className={`outline-row level-${item.level}`}
                  style={{ paddingLeft: `${8 + (item.level - 1) * 11}px` }}
                  onClick={() => onRevealLine(item.line)}
                  title={`Jump to line ${item.line}`}
                >
                  <span className="outline-level">H{item.level}</span>
                  <span className="outline-text">{item.text}</span>
                  <span className="outline-line">{item.line}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="inspector-empty">
              <ListTree />
              <strong>No outline yet</strong>
              <p>Add Markdown headings to navigate this note by section.</p>
            </div>
          )
        ) : null}

        {tab === "links" ? (
          <BacklinkPanel
            key={note.id}
            noteId={note.id}
            className="backlinks-panel"
          />
        ) : null}

        {tab === "properties" ? (
          <div className="inspector-properties">
            <div className="prop-row">
              <span className="prop-key">Status</span>
              <span className="prop-value">
                <StatusIcon status={note.status} />
                {STATUS_LABEL[note.status]}
              </span>
            </div>
            <div className="prop-row">
              <span className="prop-key">Difficulty</span>
              <span className="prop-value">{note.difficulty || "—"}</span>
            </div>
            <div className="prop-row">
              <span className="prop-key">Target</span>
              <span className="prop-value">
                {note.target ? (
                  <button
                    type="button"
                    className="prop-copy"
                    onClick={() => copy(note.target, "Target")}
                    title="Copy target"
                  >
                    <Target />
                    <span>{note.target}</span>
                  </button>
                ) : (
                  "—"
                )}
              </span>
            </div>
            <div className="prop-row">
              <span className="prop-key">Folder</span>
              <span className="prop-value prop-path">
                <Folder />
                <span>{note.path || "Vault root"}</span>
              </span>
            </div>
            <div className="prop-row">
              <span className="prop-key">Tags</span>
              <span className="prop-value prop-tags">
                {note.tag_list.length ? (
                  note.tag_list.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      className="chip tag"
                      onClick={() => filterByTag(tag)}
                      title={`Filter vault by #${tag}`}
                    >
                      <Tag />
                      {tag}
                    </button>
                  ))
                ) : (
                  "—"
                )}
              </span>
            </div>
            <div className="prop-row">
              <span className="prop-key">Flag</span>
              <span className="prop-value prop-flag">
                {note.flag ? (
                  <button
                    type="button"
                    className="prop-copy flag-copy-button"
                    onClick={() => copy(note.flag, "Flag")}
                    title="Copy flag"
                  >
                    {copied ? <Check /> : <Copy />}
                    <code>{note.flag}</code>
                  </button>
                ) : (
                  "—"
                )}
              </span>
            </div>
            <div className={`flag-format ${format.tone}`}>
              <span className="flag-format-label">
                <Flag />
                {format.label}
              </span>
              <span className="flag-format-detail">{format.detail}</span>
            </div>
            <div className="prop-row">
              <span className="prop-key">Created</span>
              <span className="prop-value">{formatDate(note.created_at, true)}</span>
            </div>
            <div className="prop-row">
              <span className="prop-key">Updated</span>
              <span className="prop-value">
                <Clock3 />
                {relativeTime(note.updated_at)}
              </span>
            </div>
            <div className="prop-row">
              <span className="prop-key">Length</span>
              <span className="prop-value">
                {plural(words, "word")} · {readingTime(draft)}
              </span>
            </div>
            <button
              type="button"
              className="btn ghost sm block inspector-edit"
              onClick={() => openModal("properties")}
            >
              <Pencil />
              Edit properties
            </button>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
