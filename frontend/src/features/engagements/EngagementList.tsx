import { useMemo, useState } from "react";
import { Button } from "../../ui/Button";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { EmptyState } from "../../ui/EmptyState";
import { Field } from "../../ui/Field";
import { Toolbar } from "../../ui/Toolbar";
import { cx } from "../../lib/ux";
import {
  ENGAGEMENT_STATUSES,
  engagementTitle,
  filterEngagements,
  humanize,
  sortEngagements,
  statusTone,
} from "./logic";
import type { EngagementStatus, EngagementSummary } from "./types";

export interface EngagementListProps {
  engagements: EngagementSummary[];
  selectedId?: number | null;
  loading?: boolean;
  onSelect: (id: number) => void;
  onCreate?: () => void;
  onSeedDemo?: () => void;
}

export function EngagementList({
  engagements,
  selectedId,
  loading = false,
  onSelect,
  onCreate,
  onSeedDemo,
}: EngagementListProps) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<EngagementStatus | "">("");
  const [sort, setSort] = useState<"updated" | "name" | "status">("updated");

  const rows = useMemo(
    () =>
      sortEngagements(filterEngagements(engagements, { query, status }), sort),
    [engagements, query, sort, status],
  );

  const columns: DataTableColumn<EngagementSummary>[] = [
    {
      key: "name",
      header: "Engagement",
      sortable: true,
      sortValue: (row) => engagementTitle(row),
      render: (row) => (
        <button
          type="button"
          className="eng-row-link"
          onClick={() => onSelect(row.id)}
        >
          <span className="eng-cell-stack">
            <strong>{engagementTitle(row)}</strong>
            <span className="eng-cell-muted">{row.key}</span>
          </span>
        </button>
      ),
    },
    {
      key: "client",
      header: "Client",
      sortable: true,
      render: (row) => row.client || "—",
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      render: (row) => (
        <span className={cx("eng-pill", `eng-pill--${statusTone(row.status)}`)}>
          {humanize(row.status)}
        </span>
      ),
    },
    {
      key: "findings",
      header: "Findings",
      align: "right",
      sortable: true,
      sortValue: (row) => row.counts?.findings ?? 0,
      render: (row) => row.counts?.findings ?? "—",
    },
    {
      key: "updated_at",
      header: "Updated",
      sortable: true,
      render: (row) => row.updated_at.slice(0, 10) || "—",
    },
  ];

  return (
    <section className="eng-panel" aria-label="Engagements">
      <header className="eng-panel__head">
        <div>
          <h2 className="eng-panel__title">Engagements</h2>
          <p className="eng-panel__subtitle">
            {engagements.length} in workspace
          </p>
        </div>
        <div className="eng-panel__actions">
          {onSeedDemo ? (
            <Button size="sm" variant="ghost" onClick={onSeedDemo}>
              Seed demo
            </Button>
          ) : null}
          {onCreate ? (
            <Button size="sm" variant="primary" onClick={onCreate}>
              New engagement
            </Button>
          ) : null}
        </div>
      </header>
      <Toolbar label="Engagement filters" className="eng-toolbar">
        <Field
          label="Search"
          value={query}
          placeholder="Name, client, owner"
          onChange={(event) => setQuery(event.target.value)}
        />
        <label className="eng-select">
          <span>Status</span>
          <select
            value={status}
            onChange={(event) =>
              setStatus(event.target.value as EngagementStatus | "")
            }
          >
            <option value="">All</option>
            {ENGAGEMENT_STATUSES.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="eng-select">
          <span>Sort</span>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as typeof sort)}
          >
            <option value="updated">Recently updated</option>
            <option value="name">Name</option>
            <option value="status">Status</option>
          </select>
        </label>
      </Toolbar>
      {loading ? (
        <div className="eng-skeleton" aria-label="Loading engagements" />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No engagements found"
          description="Adjust the filters or create a new engagement to get started."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.id}
          label="Engagement list"
          empty="No engagements"
        />
      )}
      {selectedId ? (
        <p className="eng-panel__footnote">Selected engagement: {selectedId}</p>
      ) : null}
    </section>
  );
}
