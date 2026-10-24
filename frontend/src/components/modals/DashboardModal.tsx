import { useEffect, useState } from "react";
import {
  Copy,
  FileText,
  Flag,
  Folder,
  LayoutDashboard,
  Pin,
  Tag,
  Target,
} from "lucide-react";
import { api } from "../../lib/api";
import type { FlagHit, TagCount, VaultStats } from "../../lib/types";
import { copyText, plural } from "../../lib/utils";
import { useAppStore } from "../../store/useAppStore";
import { useUiStore } from "../../store/useUiStore";
import { Modal } from "./Modal";

export function DashboardModal() {
  const setFilter = useAppStore((state) => state.setFilter);
  const openNote = useAppStore((state) => state.openNote);
  const closeModal = useUiStore((state) => state.closeModal);
  const toast = useUiStore((state) => state.toast);

  const [stats, setStats] = useState<VaultStats | null>(null);
  const [flags, setFlags] = useState<FlagHit[]>([]);
  const [tags, setTags] = useState<TagCount[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.stats(), api.collectedFlags(), api.tagCounts()])
      .then(([nextStats, nextFlags, nextTags]) => {
        if (cancelled) return;
        setStats(nextStats);
        setFlags(nextFlags);
        setTags(nextTags);
      })
      .catch((error: unknown) =>
        toast(
          error instanceof Error ? error.message : "Could not load dashboard",
          "error",
        ),
      )
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [toast]);

  const open = (id: number) => {
    closeModal();
    void openNote(id).catch((error: unknown) =>
      toast(
        error instanceof Error ? error.message : "Could not open note",
        "error",
      ),
    );
  };

  const copy = (value: string) => {
    void copyText(value).then(
      () => toast("Flag copied", "success"),
      () => toast("Could not copy the flag", "error"),
    );
  };

  const cards = stats
    ? [
        { label: "Notes", value: stats.notes, icon: FileText },
        { label: "Folders", value: stats.folders, icon: Folder },
        { label: "Flags", value: stats.flags, icon: Flag },
        { label: "Targets", value: stats.targets, icon: Target },
        { label: "Tags", value: stats.tags, icon: Tag },
        { label: "Pinned", value: stats.pinned, icon: Pin },
      ]
    : [];

  return (
    <Modal
      title="Dashboard"
      subtitle="A live overview of your vault"
      icon={<LayoutDashboard />}
      className="dashboard-modal"
      label="Dashboard"
    >
      {loading ? (
        <div className="tree-skeleton">
          <span style={{ width: "68%" }} />
          <span style={{ width: "84%" }} />
          <span style={{ width: "52%" }} />
        </div>
      ) : (
        <>
          <div className="dash-grid">
            {cards.map((card) => {
              const Icon = card.icon;
              return (
                <div className="dash-card" key={card.label}>
                  <span className="dc-icon">
                    <Icon />
                  </span>
                  <span className="dc-value">{card.value}</span>
                  <span className="dc-label">{card.label}</span>
                </div>
              );
            })}
          </div>

          <div className="dash-columns">
            <section className="dash-section">
              <div className="dash-section-head">
                <span>
                  <Flag /> Collected flags
                </span>
                <span className="muted">{plural(flags.length, "flag")}</span>
              </div>
              {flags.length === 0 ? (
                <div className="dash-empty">
                  No flags yet. Add a flag in note properties and it will appear
                  here.
                </div>
              ) : (
                <div className="flag-list">
                  {flags.map((hit) => (
                    <div
                      className="flag-item"
                      key={`${hit.node_id}-${hit.flag}`}
                    >
                      <button
                        type="button"
                        className="flag-open"
                        onClick={() => open(hit.node_id)}
                        title={`Open ${hit.title}`}
                      >
                        <span className="fi-flag">{hit.flag}</span>
                        <span className="fi-title">{hit.title}</span>
                        <span className="fi-path">
                          {hit.path || "Vault root"}
                          {hit.manual ? " · manual" : ""}
                        </span>
                      </button>
                      <button
                        type="button"
                        className="icon-btn sm"
                        onClick={() => copy(hit.flag)}
                        title="Copy flag"
                        aria-label="Copy flag"
                      >
                        <Copy />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="dash-section">
              <div className="dash-section-head">
                <span>
                  <Tag /> Tag cloud
                </span>
                <span className="muted">{plural(tags.length, "tag")}</span>
              </div>
              {tags.length === 0 ? (
                <div className="dash-empty">
                  Tags will appear here as you add them to notes.
                </div>
              ) : (
                <div className="tag-cloud">
                  {tags.map((tag) => (
                    <button
                      type="button"
                      className="chip tag"
                      key={tag.tag}
                      onClick={() => {
                        setFilter(tag.tag);
                        closeModal();
                      }}
                      title={`Filter the sidebar by ${tag.tag}`}
                    >
                      {tag.tag}
                      <span className="count">{tag.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </Modal>
  );
}
