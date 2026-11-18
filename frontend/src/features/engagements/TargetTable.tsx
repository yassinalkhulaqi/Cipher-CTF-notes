import { useMemo, useState } from "react";
import { Button } from "../../ui/Button";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { Dialog } from "../../ui/Dialog";
import { EmptyState } from "../../ui/EmptyState";
import { Field } from "../../ui/Field";
import { Toolbar } from "../../ui/Toolbar";
import {
  CRITICALITIES,
  SCOPE_STATUSES,
  TARGET_STATUSES,
  TARGET_KIND_OPTIONS,
  filterTargets,
  humanize,
  sortTargets,
  statusTone,
  targetLabel,
} from "./logic";
import { cx } from "../../lib/ux";
import type {
  Criticality,
  ScopeStatus,
  Target,
  TargetKind,
  TargetStatus,
} from "./types";

export interface TargetTableProps {
  targets: Target[];
  onCreate?: (data: Record<string, unknown>) => void | Promise<void>;
  onUpdate?: (
    id: number,
    data: Record<string, unknown>,
  ) => void | Promise<void>;
  onRemove?: (id: number) => void | Promise<void>;
  onScopeTransition?: (id: number, action: string) => void | Promise<void>;
}

interface TargetDraft {
  value: string;
  name: string;
  kind: TargetKind;
  criticality: Criticality;
  scope_status: ScopeStatus;
  status: TargetStatus;
  tags: string;
  notes: string;
}

const EMPTY_DRAFT: TargetDraft = {
  value: "",
  name: "",
  kind: "host",
  criticality: "medium",
  scope_status: "pending",
  status: "discovered",
  tags: "",
  notes: "",
};

export function TargetTable({
  targets,
  onCreate,
  onUpdate,
  onRemove,
  onScopeTransition,
}: TargetTableProps) {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<ScopeStatus | "">("");
  const [criticality, setCriticality] = useState<Criticality | "">("");
  const [editing, setEditing] = useState<Target | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<TargetDraft>(EMPTY_DRAFT);

  const rows = useMemo(
    () => sortTargets(filterTargets(targets, { query, scope, criticality })),
    [targets, query, scope, criticality],
  );

  const openCreate = () => {
    setDraft(EMPTY_DRAFT);
    setCreating(true);
  };

  const openEdit = (target: Target) => {
    setEditing(target);
    setDraft({
      value: target.value,
      name: target.name,
      kind: target.kind,
      criticality: target.criticality,
      scope_status: target.scope_status,
      status: target.status,
      tags: target.tags.join(", "),
      notes: target.notes,
    });
  };

  const close = () => {
    setCreating(false);
    setEditing(null);
  };

  const submit = async () => {
    const payload: Record<string, unknown> = {
      ...draft,
      tags: draft.tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    };
    if (editing) {
      await onUpdate?.(editing.id, payload);
    } else {
      await onCreate?.(payload);
    }
    close();
  };

  const columns: DataTableColumn<Target>[] = [
    {
      key: "value",
      header: "Target",
      sortable: true,
      sortValue: (row) => targetLabel(row),
      render: (row) => (
        <button
          type="button"
          className="eng-row-link"
          onClick={() => openEdit(row)}
        >
          <span className="eng-cell-stack">
            <strong>{targetLabel(row)}</strong>
            <span className="eng-cell-muted">{humanize(row.kind)}</span>
          </span>
        </button>
      ),
    },
    {
      key: "scope_status",
      header: "Scope",
      sortable: true,
      render: (row) => (
        <span
          className={cx(
            "eng-pill",
            `eng-pill--${statusTone(row.scope_status)}`,
          )}
        >
          {humanize(row.scope_status)}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      render: (row) => humanize(row.status),
    },
    {
      key: "criticality",
      header: "Criticality",
      sortable: true,
      render: (row) => humanize(row.criticality),
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <div className="eng-row-actions">
          {row.scope_status === "pending" ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onScopeTransition?.(row.id, "accept")}
            >
              Accept
            </Button>
          ) : null}
          {row.scope_status === "in_scope" ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onScopeTransition?.(row.id, "exclude")}
            >
              Exclude
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => onRemove?.(row.id)}>
            Remove
          </Button>
        </div>
      ),
    },
  ];

  return (
    <section className="eng-panel" aria-label="Targets">
      <header className="eng-panel__head">
        <div>
          <h3 className="eng-panel__title">Targets</h3>
          <p className="eng-panel__subtitle">{targets.length} tracked</p>
        </div>
        {onCreate ? (
          <Button size="sm" variant="primary" onClick={openCreate}>
            Add target
          </Button>
        ) : null}
      </header>
      <Toolbar label="Target filters" className="eng-toolbar">
        <Field
          label="Search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <label className="eng-select">
          <span>Scope</span>
          <select
            value={scope}
            onChange={(event) =>
              setScope(event.target.value as ScopeStatus | "")
            }
          >
            <option value="">All</option>
            {SCOPE_STATUSES.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="eng-select">
          <span>Criticality</span>
          <select
            value={criticality}
            onChange={(event) =>
              setCriticality(event.target.value as Criticality | "")
            }
          >
            <option value="">All</option>
            {CRITICALITIES.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
      </Toolbar>
      {rows.length === 0 ? (
        <EmptyState
          title="No targets"
          description="Add a target to begin mapping the engagement."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.id}
          label="Target table"
        />
      )}
      <Dialog
        open={creating || editing !== null}
        onClose={close}
        title={editing ? `Edit ${targetLabel(editing)}` : "Add target"}
        description="Scope decisions can be revised from the scope editor at any time."
        footer={
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void submit()}>
              Save target
            </Button>
          </>
        }
      >
        <div className="eng-form-grid">
          <Field
            label="Value"
            value={draft.value}
            onChange={(event) =>
              setDraft({ ...draft, value: event.target.value })
            }
          />
          <Field
            label="Name"
            value={draft.name}
            onChange={(event) =>
              setDraft({ ...draft, name: event.target.value })
            }
          />
          <label className="eng-select">
            <span>Kind</span>
            <select
              value={draft.kind}
              onChange={(event) =>
                setDraft({ ...draft, kind: event.target.value as TargetKind })
              }
            >
              {TARGET_KIND_OPTIONS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label className="eng-select">
            <span>Criticality</span>
            <select
              value={draft.criticality}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  criticality: event.target.value as Criticality,
                })
              }
            >
              {CRITICALITIES.map((item) => (
                <option key={item} value={item}>
                  {humanize(item)}
                </option>
              ))}
            </select>
          </label>
          <label className="eng-select">
            <span>Scope status</span>
            <select
              value={draft.scope_status}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  scope_status: event.target.value as ScopeStatus,
                })
              }
            >
              {SCOPE_STATUSES.map((item) => (
                <option key={item} value={item}>
                  {humanize(item)}
                </option>
              ))}
            </select>
          </label>
          <label className="eng-select">
            <span>Target status</span>
            <select
              value={draft.status}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  status: event.target.value as TargetStatus,
                })
              }
            >
              {TARGET_STATUSES.map((item) => (
                <option key={item} value={item}>
                  {humanize(item)}
                </option>
              ))}
            </select>
          </label>
          <Field
            label="Tags"
            value={draft.tags}
            onChange={(event) =>
              setDraft({ ...draft, tags: event.target.value })
            }
          />
          <label className="eng-textarea">
            <span>Notes</span>
            <textarea
              value={draft.notes}
              rows={3}
              onChange={(event) =>
                setDraft({ ...draft, notes: event.target.value })
              }
            />
          </label>
        </div>
      </Dialog>
    </section>
  );
}
