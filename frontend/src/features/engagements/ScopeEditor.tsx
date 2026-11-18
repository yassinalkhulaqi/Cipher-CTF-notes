import { useMemo, useState } from "react";
import { Button } from "../../ui/Button";
import { Banner } from "../../ui/Banner";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { EmptyState } from "../../ui/EmptyState";
import { Field } from "../../ui/Field";
import { Toolbar } from "../../ui/Toolbar";
import { cx } from "../../lib/ux";
import {
  SCOPE_RULE_KINDS,
  evaluateScope,
  humanize,
  scopeActionTone,
} from "./logic";
import type { ScopeAction, ScopeRule, ScopeRuleKind } from "./types";

export interface ScopeEditorProps {
  rules: ScopeRule[];
  onAdd?: (data: Record<string, unknown>) => void | Promise<void>;
  onRemove?: (id: number) => void | Promise<void>;
}

export function ScopeEditor({ rules, onAdd, onRemove }: ScopeEditorProps) {
  const [kind, setKind] = useState<ScopeRuleKind>("domain");
  const [value, setValue] = useState("");
  const [action, setAction] = useState<ScopeAction>("include");
  const [notes, setNotes] = useState("");
  const [probe, setProbe] = useState("");

  const evaluation = useMemo(() => evaluateScope(rules, probe), [rules, probe]);

  const submit = async () => {
    if (!value.trim()) return;
    await onAdd?.({ kind, value: value.trim(), action, notes: notes.trim() });
    setValue("");
    setNotes("");
  };

  const columns: DataTableColumn<ScopeRule>[] = [
    {
      key: "kind",
      header: "Kind",
      sortable: true,
      render: (row) => humanize(row.kind),
    },
    {
      key: "value",
      header: "Pattern",
      sortable: true,
      render: (row) => row.value,
    },
    {
      key: "action",
      header: "Action",
      sortable: true,
      render: (row) => (
        <span
          className={cx("eng-pill", `eng-pill--${scopeActionTone(row.action)}`)}
        >
          {humanize(row.action)}
        </span>
      ),
    },
    { key: "notes", header: "Notes", render: (row) => row.notes || "—" },
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
    <section className="eng-panel" aria-label="Scope editor">
      <header className="eng-panel__head">
        <div>
          <h3 className="eng-panel__title">Scope rules</h3>
          <p className="eng-panel__subtitle">
            {rules.length} patterns evaluated top to bottom
          </p>
        </div>
      </header>
      <Toolbar label="Scope probe" className="eng-toolbar">
        <Field
          label="Probe value"
          value={probe}
          placeholder="corp.example.com:443"
          onChange={(event) => setProbe(event.target.value)}
        />
      </Toolbar>
      {probe.trim() ? (
        <Banner
          tone={
            evaluation.decision === "excluded"
              ? "danger"
              : evaluation.decision === "included"
                ? "success"
                : "info"
          }
          title={`Decision: ${humanize(evaluation.decision)}`}
        >
          {evaluation.matched.length
            ? `Matched ${evaluation.matched.map((rule) => rule.value).join(", ")}`
            : "No rule matched; value remains unspecified."}
        </Banner>
      ) : null}
      {rules.length === 0 ? (
        <EmptyState
          title="No scope rules"
          description="Add include and exclude patterns to formalize the rules of engagement."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rules}
          getRowKey={(row) => row.id}
          label="Scope rule table"
        />
      )}
      <form
        className="eng-form-grid eng-scope-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label className="eng-select">
          <span>Kind</span>
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as ScopeRuleKind)}
          >
            {SCOPE_RULE_KINDS.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
        <Field
          label="Value"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
        <label className="eng-select">
          <span>Action</span>
          <select
            value={action}
            onChange={(event) => setAction(event.target.value as ScopeAction)}
          >
            <option value="include">Include</option>
            <option value="exclude">Exclude</option>
          </select>
        </label>
        <Field
          label="Notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />
        <Button type="submit" variant="primary" disabled={!value.trim()}>
          Add rule
        </Button>
      </form>
    </section>
  );
}
