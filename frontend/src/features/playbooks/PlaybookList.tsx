import { useMemo, useState } from "react";
import { Banner } from "../../ui/Banner";
import { Button } from "../../ui/Button";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { EmptyState } from "../../ui/EmptyState";
import { Field } from "../../ui/Field";
import { Toolbar } from "../../ui/Toolbar";
import { statusLabel } from "./helpers";
import type { PlaybookSummary } from "./types";
import type { PlaybooksController } from "./usePlaybooks";

export interface PlaybookListProps {
  controller: PlaybooksController;
}

const STAT_KEYS: Array<[string, string]> = [
  ["playbooks", "Playbooks"],
  ["active", "Active"],
  ["steps", "Steps"],
  ["checklists", "Checklist items"],
  ["variables", "Variables"],
  ["tags", "Tags"],
];

export function PlaybookList({ controller }: PlaybookListProps) {
  const [tagDraft, setTagDraft] = useState("");
  const { filters, setFilters, visible, stats } = controller;

  const categories = useMemo(() => {
    const values = new Set(
      controller.playbooks.map((item) => item.category || "general"),
    );
    return Array.from(values).sort();
  }, [controller.playbooks]);

  const allTags = useMemo(() => {
    const values = new Set<string>();
    for (const playbook of controller.playbooks) {
      for (const tag of playbook.tags) values.add(tag.toLocaleLowerCase());
    }
    return Array.from(values).sort();
  }, [controller.playbooks]);

  const columns: DataTableColumn<PlaybookSummary>[] = useMemo(
    () => [
      {
        key: "title",
        header: "Playbook",
        sortable: true,
        sortValue: (row) => row.title,
        render: (row) => (
          <div className="pb-list__title-cell">
            <button
              type="button"
              className="pb-list__link"
              onClick={() => void controller.select(row.key)}
            >
              {row.title}
            </button>
            <span className="pb-list__key">{row.key}</span>
          </div>
        ),
      },
      {
        key: "category",
        header: "Category",
        sortable: true,
        sortValue: (row) => row.category,
        render: (row) => (
          <span className="pb-chip pb-chip--muted">
            {row.category || "general"}
          </span>
        ),
      },
      {
        key: "status",
        header: "Status",
        sortable: true,
        sortValue: (row) => row.status,
        render: (row) => (
          <span className={`pb-chip pb-chip--${row.status}`}>
            {statusLabel(row.status)}
          </span>
        ),
      },
      {
        key: "steps",
        header: "Steps",
        sortable: true,
        sortValue: (row) => row.step_count ?? 0,
        align: "right",
        render: (row) => String(row.step_count ?? 0),
      },
      {
        key: "version",
        header: "Version",
        sortable: true,
        sortValue: (row) => row.version,
        render: (row) => <code>{row.version}</code>,
      },
      {
        key: "updated",
        header: "Updated",
        sortable: true,
        sortValue: (row) => row.updated_at,
        render: (row) => (
          <span className="pb-list__muted">{row.updated_at.slice(0, 10)}</span>
        ),
      },
    ],
    [controller],
  );

  const toggleTag = (tag: string) => {
    const active = filters.tags.includes(tag);
    setFilters({
      tags: active
        ? filters.tags.filter((item) => item !== tag)
        : [...filters.tags, tag],
    });
  };

  const addTag = () => {
    const tag = tagDraft.trim().toLocaleLowerCase().replace(/^#/, "");
    if (!tag || filters.tags.includes(tag)) return;
    setFilters({ tags: [...filters.tags, tag] });
    setTagDraft("");
  };

  const sort = { key: filters.sort, direction: filters.direction };

  return (
    <section className="pb-list" aria-label="Playbook library">
      <header className="pb-section-header">
        <div>
          <h2>Playbooks</h2>
          <p className="pb-section-subtitle">
            Reusable, versioned investigation workflows with checklists and dry
            runs.
          </p>
        </div>
        <div className="pb-stat-row">
          {STAT_KEYS.map(([key, label]) => (
            <div className="pb-stat" key={key}>
              <strong>{stats[key] ?? 0}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </header>

      {controller.error ? (
        <Banner tone="danger" title="Playbook error">
          {controller.error}
        </Banner>
      ) : null}
      {controller.notice ? (
        <Banner tone="success" title="Done">
          {controller.notice}
        </Banner>
      ) : null}

      <div className="pb-list__filters">
        <Field
          label="Search"
          placeholder="Search playbooks, steps, commands"
          value={filters.query}
          onChange={(event) => setFilters({ query: event.target.value })}
        />
        <label className="pb-field">
          <span>Category</span>
          <select
            value={filters.category}
            onChange={(event) => setFilters({ category: event.target.value })}
          >
            <option value="">All categories</option>
            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </label>
        <label className="pb-field">
          <span>Status</span>
          <select
            value={filters.status}
            onChange={(event) => setFilters({ status: event.target.value })}
          >
            <option value="">Any status</option>
            <option value="active">Active</option>
            <option value="draft">Draft</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <Field
          label="Add tag"
          placeholder="recon"
          value={tagDraft}
          onChange={(event) => setTagDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addTag();
            }
          }}
        />
      </div>

      {allTags.length > 0 ? (
        <Toolbar label="Filter by tag" className="pb-list__tags">
          {allTags.map((tag) => (
            <Button
              key={tag}
              size="sm"
              variant={filters.tags.includes(tag) ? "primary" : "ghost"}
              onClick={() => toggleTag(tag)}
            >
              #{tag}
            </Button>
          ))}
        </Toolbar>
      ) : null}

      <DataTable
        label="Playbooks"
        rows={visible}
        columns={columns}
        getRowKey={(row) => row.key}
        sort={sort}
        onSortChange={(next) =>
          setFilters({
            sort: (next?.key ??
              "title") as PlaybooksController["filters"]["sort"],
            direction: next?.direction ?? "asc",
          })
        }
        empty={
          <EmptyState
            title="No playbooks found"
            description="Try a different query, category, status, or tag."
          />
        }
      />
    </section>
  );
}
