import { useMemo, useState } from "react";
import { Button } from "../../ui/Button";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { Dialog } from "../../ui/Dialog";
import { EmptyState } from "../../ui/EmptyState";
import { Field } from "../../ui/Field";
import { Toolbar } from "../../ui/Toolbar";
import { cx } from "../../lib/ux";
import {
  ASSET_KINDS,
  ASSET_STATUSES,
  CRITICALITIES,
  CREDENTIAL_KINDS,
  CREDENTIAL_STATUSES,
  SERVICE_STATUSES,
  filterAssets,
  filterCredentials,
  filterServices,
  humanize,
  statusTone,
} from "./logic";
import type {
  Asset,
  AssetKind,
  AssetStatus,
  Credential,
  CredentialKind,
  CredentialStatus,
  Criticality,
  Service,
  ServiceStatus,
  Target,
} from "./types";

interface EntityTableProps<T> {
  items: T[];
  targets: Target[];
  onCreate?: (data: Record<string, unknown>) => void | Promise<void>;
  onUpdate?: (
    id: number,
    data: Record<string, unknown>,
  ) => void | Promise<void>;
  onRemove?: (id: number) => void | Promise<void>;
}

function targetName(targets: Target[], id: number): string {
  const target = targets.find((item) => item.id === id);
  return target ? target.name || target.value : `Target ${id}`;
}

function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly T[];
  onChange: (value: T) => void;
}) {
  return (
    <label className="eng-select">
      <span>{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value as T)}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {humanize(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

export function AssetTable({
  items,
  targets,
  onCreate,
  onUpdate,
  onRemove,
}: EntityTableProps<Asset>) {
  const [targetId, setTargetId] = useState(0);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Asset | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({
    target_id: 0,
    name: "",
    kind: "server" as AssetKind,
    identifier: "",
    status: "identified" as AssetStatus,
    criticality: "medium" as Criticality,
    owner: "",
    notes: "",
  });
  const rows = useMemo(
    () => filterAssets(items, targetId, query),
    [items, targetId, query],
  );

  const openCreate = () => {
    setDraft({
      target_id: targets[0]?.id ?? 0,
      name: "",
      kind: "server",
      identifier: "",
      status: "identified",
      criticality: "medium",
      owner: "",
      notes: "",
    });
    setCreating(true);
  };

  const openEdit = (asset: Asset) => {
    setEditing(asset);
    setDraft({
      target_id: asset.target_id,
      name: asset.name,
      kind: asset.kind,
      identifier: asset.identifier,
      status: asset.status,
      criticality: asset.criticality,
      owner: asset.owner,
      notes: asset.notes,
    });
  };

  const close = () => {
    setCreating(false);
    setEditing(null);
  };

  const submit = async () => {
    if (editing) {
      await onUpdate?.(editing.id, { ...draft });
    } else {
      await onCreate?.({ ...draft });
    }
    close();
  };

  const columns: DataTableColumn<Asset>[] = [
    {
      key: "name",
      header: "Asset",
      sortable: true,
      render: (row) => (
        <button
          type="button"
          className="eng-row-link"
          onClick={() => openEdit(row)}
        >
          {row.name || row.identifier || `Asset ${row.id}`}
        </button>
      ),
    },
    {
      key: "target",
      header: "Target",
      render: (row) => targetName(targets, row.target_id),
    },
    {
      key: "kind",
      header: "Kind",
      sortable: true,
      render: (row) => humanize(row.kind),
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
      key: "criticality",
      header: "Criticality",
      sortable: true,
      render: (row) => humanize(row.criticality),
    },
    {
      key: "actions",
      header: "Actions",
      render: (row) => (
        <Button size="sm" variant="ghost" onClick={() => onRemove?.(row.id)}>
          Remove
        </Button>
      ),
    },
  ];

  return (
    <section className="eng-panel" aria-label="Assets">
      <header className="eng-panel__head">
        <div>
          <h3 className="eng-panel__title">Assets</h3>
          <p className="eng-panel__subtitle">{items.length} identified</p>
        </div>
        {onCreate ? (
          <Button size="sm" variant="primary" onClick={openCreate}>
            Add asset
          </Button>
        ) : null}
      </header>
      <Toolbar label="Asset filters" className="eng-toolbar">
        <Field
          label="Search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <label className="eng-select">
          <span>Target</span>
          <select
            value={targetId}
            onChange={(event) => setTargetId(Number(event.target.value))}
          >
            <option value={0}>All targets</option>
            {targets.map((target) => (
              <option key={target.id} value={target.id}>
                {target.name || target.value}
              </option>
            ))}
          </select>
        </label>
      </Toolbar>
      {rows.length === 0 ? (
        <EmptyState
          title="No assets"
          description="Add assets as targets are enumerated."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.id}
          label="Asset table"
        />
      )}
      <Dialog
        open={creating || editing !== null}
        onClose={close}
        title={editing ? `Edit ${editing.name}` : "Add asset"}
        footer={
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void submit()}>
              Save asset
            </Button>
          </>
        }
      >
        <div className="eng-form-grid">
          <label className="eng-select">
            <span>Target</span>
            <select
              value={draft.target_id}
              onChange={(event) =>
                setDraft({ ...draft, target_id: Number(event.target.value) })
              }
            >
              {targets.map((target) => (
                <option key={target.id} value={target.id}>
                  {target.name || target.value}
                </option>
              ))}
            </select>
          </label>
          <Field
            label="Name"
            value={draft.name}
            onChange={(event) =>
              setDraft({ ...draft, name: event.target.value })
            }
          />
          <Field
            label="Identifier"
            value={draft.identifier}
            onChange={(event) =>
              setDraft({ ...draft, identifier: event.target.value })
            }
          />
          <SelectField
            label="Kind"
            value={draft.kind}
            options={ASSET_KINDS}
            onChange={(kind) => setDraft({ ...draft, kind })}
          />
          <SelectField
            label="Status"
            value={draft.status}
            options={ASSET_STATUSES}
            onChange={(status) => setDraft({ ...draft, status })}
          />
          <SelectField
            label="Criticality"
            value={draft.criticality}
            options={CRITICALITIES}
            onChange={(criticality) => setDraft({ ...draft, criticality })}
          />
          <Field
            label="Owner"
            value={draft.owner}
            onChange={(event) =>
              setDraft({ ...draft, owner: event.target.value })
            }
          />
          <label className="eng-textarea">
            <span>Notes</span>
            <textarea
              rows={3}
              value={draft.notes}
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

export function ServiceTable({
  items,
  targets,
  onCreate,
  onUpdate,
  onRemove,
}: EntityTableProps<Service>) {
  const [targetId, setTargetId] = useState(0);
  const [port, setPort] = useState(0);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Service | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({
    target_id: 0,
    asset_id: 0,
    name: "",
    port: 0,
    protocol: "tcp",
    product: "",
    version: "",
    status: "discovered" as ServiceStatus,
    notes: "",
  });
  const rows = useMemo(
    () => filterServices(items, { targetId, port, query }),
    [items, targetId, port, query],
  );

  const openCreate = () => {
    setDraft({
      target_id: targets[0]?.id ?? 0,
      asset_id: 0,
      name: "",
      port: 0,
      protocol: "tcp",
      product: "",
      version: "",
      status: "discovered",
      notes: "",
    });
    setCreating(true);
  };

  const openEdit = (service: Service) => {
    setEditing(service);
    setDraft({
      target_id: service.target_id,
      asset_id: service.asset_id,
      name: service.name,
      port: service.port,
      protocol: service.protocol,
      product: service.product,
      version: service.version,
      status: service.status,
      notes: service.notes,
    });
  };

  const close = () => {
    setCreating(false);
    setEditing(null);
  };

  const submit = async () => {
    if (editing) {
      await onUpdate?.(editing.id, { ...draft });
    } else {
      await onCreate?.({ ...draft });
    }
    close();
  };

  const columns: DataTableColumn<Service>[] = [
    {
      key: "name",
      header: "Service",
      sortable: true,
      render: (row) => (
        <button
          type="button"
          className="eng-row-link"
          onClick={() => openEdit(row)}
        >
          {row.name || `Service ${row.id}`}
        </button>
      ),
    },
    {
      key: "endpoint",
      header: "Endpoint",
      render: (row) => row.endpoint || `${row.port}/${row.protocol}`,
    },
    {
      key: "target",
      header: "Target",
      render: (row) => targetName(targets, row.target_id),
    },
    {
      key: "product",
      header: "Product",
      render: (row) =>
        [row.product, row.version].filter(Boolean).join(" ") || "—",
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
      key: "actions",
      header: "Actions",
      render: (row) => (
        <Button size="sm" variant="ghost" onClick={() => onRemove?.(row.id)}>
          Remove
        </Button>
      ),
    },
  ];

  return (
    <section className="eng-panel" aria-label="Services">
      <header className="eng-panel__head">
        <div>
          <h3 className="eng-panel__title">Services</h3>
          <p className="eng-panel__subtitle">{items.length} observed</p>
        </div>
        {onCreate ? (
          <Button size="sm" variant="primary" onClick={openCreate}>
            Add service
          </Button>
        ) : null}
      </header>
      <Toolbar label="Service filters" className="eng-toolbar">
        <Field
          label="Search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <label className="eng-select">
          <span>Target</span>
          <select
            value={targetId}
            onChange={(event) => setTargetId(Number(event.target.value))}
          >
            <option value={0}>All targets</option>
            {targets.map((target) => (
              <option key={target.id} value={target.id}>
                {target.name || target.value}
              </option>
            ))}
          </select>
        </label>
        <label className="eng-select">
          <span>Port</span>
          <input
            type="number"
            min={0}
            value={port || ""}
            onChange={(event) => setPort(Number(event.target.value))}
          />
        </label>
      </Toolbar>
      {rows.length === 0 ? (
        <EmptyState
          title="No services"
          description="Record ports and products as they are discovered."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.id}
          label="Service table"
        />
      )}
      <Dialog
        open={creating || editing !== null}
        onClose={close}
        title={editing ? `Edit ${editing.name}` : "Add service"}
        footer={
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void submit()}>
              Save service
            </Button>
          </>
        }
      >
        <div className="eng-form-grid">
          <label className="eng-select">
            <span>Target</span>
            <select
              value={draft.target_id}
              onChange={(event) =>
                setDraft({ ...draft, target_id: Number(event.target.value) })
              }
            >
              {targets.map((target) => (
                <option key={target.id} value={target.id}>
                  {target.name || target.value}
                </option>
              ))}
            </select>
          </label>
          <Field
            label="Name"
            value={draft.name}
            onChange={(event) =>
              setDraft({ ...draft, name: event.target.value })
            }
          />
          <Field
            label="Port"
            type="number"
            value={draft.port || ""}
            onChange={(event) =>
              setDraft({ ...draft, port: Number(event.target.value) })
            }
          />
          <Field
            label="Protocol"
            value={draft.protocol}
            onChange={(event) =>
              setDraft({ ...draft, protocol: event.target.value })
            }
          />
          <Field
            label="Product"
            value={draft.product}
            onChange={(event) =>
              setDraft({ ...draft, product: event.target.value })
            }
          />
          <Field
            label="Version"
            value={draft.version}
            onChange={(event) =>
              setDraft({ ...draft, version: event.target.value })
            }
          />
          <SelectField
            label="Status"
            value={draft.status}
            options={SERVICE_STATUSES}
            onChange={(status) => setDraft({ ...draft, status })}
          />
          <label className="eng-textarea">
            <span>Notes</span>
            <textarea
              rows={3}
              value={draft.notes}
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

export function CredentialTable({
  items,
  targets,
  onCreate,
  onUpdate,
  onRemove,
}: EntityTableProps<Credential> & {
  onRotate?: (id: number, secretRef: string) => void | Promise<void>;
}) {
  const [targetId, setTargetId] = useState(0);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Credential | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({
    target_id: 0,
    username: "",
    secret_ref: "",
    kind: "password" as CredentialKind,
    status: "candidate" as CredentialStatus,
    notes: "",
  });
  const rows = useMemo(
    () => filterCredentials(items, { targetId, status, query }),
    [items, targetId, status, query],
  );

  const openCreate = () => {
    setDraft({
      target_id: targets[0]?.id ?? 0,
      username: "",
      secret_ref: "",
      kind: "password",
      status: "candidate",
      notes: "",
    });
    setCreating(true);
  };

  const openEdit = (credential: Credential) => {
    setEditing(credential);
    setDraft({
      target_id: credential.target_id,
      username: credential.username,
      secret_ref: credential.secret_ref,
      kind: credential.kind,
      status: credential.status,
      notes: credential.notes,
    });
  };

  const close = () => {
    setCreating(false);
    setEditing(null);
  };

  const submit = async () => {
    if (editing) {
      await onUpdate?.(editing.id, { ...draft });
    } else {
      await onCreate?.({ ...draft });
    }
    close();
  };

  const columns: DataTableColumn<Credential>[] = [
    {
      key: "username",
      header: "Credential",
      sortable: true,
      render: (row) => (
        <button
          type="button"
          className="eng-row-link"
          onClick={() => openEdit(row)}
        >
          {row.username || humanize(row.kind)}
        </button>
      ),
    },
    {
      key: "target",
      header: "Target",
      render: (row) => targetName(targets, row.target_id),
    },
    {
      key: "kind",
      header: "Kind",
      sortable: true,
      render: (row) => humanize(row.kind),
    },
    {
      key: "secret",
      header: "Secret ref",
      render: (row) => row.secret_ref || "—",
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
      key: "actions",
      header: "Actions",
      render: (row) => (
        <Button size="sm" variant="ghost" onClick={() => onRemove?.(row.id)}>
          Remove
        </Button>
      ),
    },
  ];

  return (
    <section className="eng-panel" aria-label="Credentials">
      <header className="eng-panel__head">
        <div>
          <h3 className="eng-panel__title">Credentials</h3>
          <p className="eng-panel__subtitle">
            {items.length} stored references
          </p>
        </div>
        {onCreate ? (
          <Button size="sm" variant="primary" onClick={openCreate}>
            Add credential
          </Button>
        ) : null}
      </header>
      <Toolbar label="Credential filters" className="eng-toolbar">
        <Field
          label="Search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <label className="eng-select">
          <span>Target</span>
          <select
            value={targetId}
            onChange={(event) => setTargetId(Number(event.target.value))}
          >
            <option value={0}>All targets</option>
            {targets.map((target) => (
              <option key={target.id} value={target.id}>
                {target.name || target.value}
              </option>
            ))}
          </select>
        </label>
        <label className="eng-select">
          <span>Status</span>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">All</option>
            {CREDENTIAL_STATUSES.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
      </Toolbar>
      {rows.length === 0 ? (
        <EmptyState
          title="No credentials"
          description="Credential values are stored as masked references."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.id}
          label="Credential table"
        />
      )}
      <Dialog
        open={creating || editing !== null}
        onClose={close}
        title={
          editing
            ? `Edit ${editing.username || "credential"}`
            : "Add credential"
        }
        description="Use a secret reference rather than pasting raw material."
        footer={
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void submit()}>
              Save credential
            </Button>
          </>
        }
      >
        <div className="eng-form-grid">
          <label className="eng-select">
            <span>Target</span>
            <select
              value={draft.target_id}
              onChange={(event) =>
                setDraft({ ...draft, target_id: Number(event.target.value) })
              }
            >
              {targets.map((target) => (
                <option key={target.id} value={target.id}>
                  {target.name || target.value}
                </option>
              ))}
            </select>
          </label>
          <Field
            label="Username"
            value={draft.username}
            onChange={(event) =>
              setDraft({ ...draft, username: event.target.value })
            }
          />
          <Field
            label="Secret reference"
            value={draft.secret_ref}
            onChange={(event) =>
              setDraft({ ...draft, secret_ref: event.target.value })
            }
          />
          <SelectField
            label="Kind"
            value={draft.kind}
            options={CREDENTIAL_KINDS}
            onChange={(kind) => setDraft({ ...draft, kind })}
          />
          <SelectField
            label="Status"
            value={draft.status}
            options={CREDENTIAL_STATUSES}
            onChange={(nextStatus) =>
              setDraft({ ...draft, status: nextStatus })
            }
          />
          <label className="eng-textarea">
            <span>Notes</span>
            <textarea
              rows={3}
              value={draft.notes}
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
