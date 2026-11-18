import { useMemo, useState } from "react";
import { Button } from "../../ui/Button";
import { Banner } from "../../ui/Banner";
import { DataTable, type DataTableColumn } from "../../ui/DataTable";
import { Dialog } from "../../ui/Dialog";
import { EmptyState } from "../../ui/EmptyState";
import { Field } from "../../ui/Field";
import { Toolbar } from "../../ui/Toolbar";
import { cx } from "../../lib/ux";
import {
  CONFIDENCES,
  FINDING_STATUSES,
  SEVERITIES,
  compareSeverity,
  filterFindings,
  formatScore,
  humanize,
  parseCsvList,
  serializeCsvList,
  severityTone,
  sortFindings,
  statusTone,
  transitionLabel,
  validateFindingDraft,
} from "./logic";
import type { Confidence, Finding, FindingStatus, Severity } from "./types";

export interface FindingEditorProps {
  findings: Finding[];
  onCreate?: (data: Record<string, unknown>) => void | Promise<void>;
  onUpdate?: (
    id: number,
    data: Record<string, unknown>,
  ) => void | Promise<void>;
  onTransition?: (
    id: number,
    action: string,
    data: Record<string, unknown>,
  ) => void | Promise<void>;
  onDuplicate?: (id: number, canonicalId: number) => void | Promise<void>;
  onRemove?: (id: number) => void | Promise<void>;
}

interface FindingDraft {
  title: string;
  summary: string;
  severity: Severity;
  confidence: Confidence;
  cvss_vector: string;
  cwe: string;
  cwes: string;
  cves: string;
  status: FindingStatus;
  target_id: number;
  asset_id: number;
  service_id: number;
  owner: string;
  impact: string;
  remediation: string;
  reproduction_steps: string;
  references: string;
  tags: string;
}

const EMPTY_DRAFT: FindingDraft = {
  title: "",
  summary: "",
  severity: "medium",
  confidence: "medium",
  cvss_vector: "",
  cwe: "",
  cwes: "",
  cves: "",
  status: "draft",
  target_id: 0,
  asset_id: 0,
  service_id: 0,
  owner: "",
  impact: "",
  remediation: "",
  reproduction_steps: "",
  references: "",
  tags: "",
};

export function FindingEditor({
  findings,
  onCreate,
  onUpdate,
  onTransition,
  onDuplicate,
  onRemove,
}: FindingEditorProps) {
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState<Severity | "">("");
  const [status, setStatus] = useState<FindingStatus | "">("");
  const [confidence, setConfidence] = useState<Confidence | "">("");
  const [openOnly, setOpenOnly] = useState(false);
  const [editing, setEditing] = useState<Finding | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<FindingDraft>(EMPTY_DRAFT);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const rows = useMemo(
    () =>
      sortFindings(
        filterFindings(findings, {
          query,
          severity,
          status,
          confidence,
          openOnly,
        }),
        "severity",
      ),
    [findings, query, severity, status, confidence, openOnly],
  );

  const openCreate = () => {
    setDraft(EMPTY_DRAFT);
    setErrors({});
    setCreating(true);
  };

  const openEdit = (finding: Finding) => {
    setEditing(finding);
    setErrors({});
    setDraft({
      title: finding.title,
      summary: finding.summary,
      severity: finding.severity,
      confidence: finding.confidence,
      cvss_vector: finding.cvss_vector,
      cwe: finding.cwe,
      cwes: serializeCsvList(finding.cwes),
      cves: serializeCsvList(finding.cves),
      status: finding.status,
      target_id: finding.target_id,
      asset_id: finding.asset_id,
      service_id: finding.service_id,
      owner: finding.owner,
      impact: finding.impact,
      remediation: finding.remediation,
      reproduction_steps: finding.reproduction_steps,
      references: serializeCsvList(finding.references),
      tags: serializeCsvList(finding.tags),
    });
  };

  const close = () => {
    setCreating(false);
    setEditing(null);
    setErrors({});
  };

  const submit = async () => {
    const validation = validateFindingDraft(draft);
    setErrors(validation);
    if (Object.keys(validation).length > 0) return;
    const payload: Record<string, unknown> = {
      ...draft,
      target_id: draft.target_id || undefined,
      asset_id: draft.asset_id || undefined,
      service_id: draft.service_id || undefined,
      cwes: parseCsvList(draft.cwes),
      cves: parseCsvList(draft.cves),
      references: parseCsvList(draft.references),
      tags: parseCsvList(draft.tags),
    };
    if (editing) {
      await onUpdate?.(editing.id, payload);
    } else {
      await onCreate?.(payload);
    }
    close();
  };

  const columns: DataTableColumn<Finding>[] = [
    {
      key: "title",
      header: "Finding",
      sortable: true,
      render: (row) => (
        <button
          type="button"
          className="eng-row-link"
          onClick={() => openEdit(row)}
        >
          <span className="eng-cell-stack">
            <strong>{row.title}</strong>
            <span className="eng-cell-muted">
              {row.target_name || `Finding ${row.id}`} ·{" "}
              {formatScore(row.cvss_score)}
            </span>
          </span>
        </button>
      ),
    },
    {
      key: "severity",
      header: "Severity",
      sortable: true,
      sortValue: (row) => compareSeverity(row.severity, "info"),
      render: (row) => (
        <span
          className={cx("eng-pill", `eng-pill--${severityTone(row.severity)}`)}
        >
          {humanize(row.severity)}
        </span>
      ),
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
      key: "confidence",
      header: "Confidence",
      sortable: true,
      render: (row) => humanize(row.confidence),
    },
    {
      key: "cwe",
      header: "CWE / CVE",
      render: (row) =>
        [row.cwe, ...row.cves].filter(Boolean).join(" · ") || "—",
    },
    {
      key: "actions",
      header: "Lifecycle",
      render: (row) => (
        <div className="eng-row-actions">
          {(row.allowed_actions ?? []).slice(0, 2).map((action) => (
            <Button
              key={action}
              size="sm"
              variant="ghost"
              onClick={() => onTransition?.(row.id, action, {})}
            >
              {transitionLabel(action)}
            </Button>
          ))}
          {onRemove ? (
            <Button size="sm" variant="ghost" onClick={() => onRemove(row.id)}>
              Remove
            </Button>
          ) : null}
        </div>
      ),
    },
  ];

  const selectedDuplicates = editing?.duplicate_candidates ?? [];

  return (
    <section className="eng-panel" aria-label="Findings">
      <header className="eng-panel__head">
        <div>
          <h3 className="eng-panel__title">Findings</h3>
          <p className="eng-panel__subtitle">{findings.length} recorded</p>
        </div>
        {onCreate ? (
          <Button size="sm" variant="primary" onClick={openCreate}>
            Add finding
          </Button>
        ) : null}
      </header>
      <Toolbar label="Finding filters" className="eng-toolbar">
        <Field
          label="Search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <label className="eng-select">
          <span>Severity</span>
          <select
            value={severity}
            onChange={(event) =>
              setSeverity(event.target.value as Severity | "")
            }
          >
            <option value="">All</option>
            {SEVERITIES.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="eng-select">
          <span>Status</span>
          <select
            value={status}
            onChange={(event) =>
              setStatus(event.target.value as FindingStatus | "")
            }
          >
            <option value="">All</option>
            {FINDING_STATUSES.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="eng-select">
          <span>Confidence</span>
          <select
            value={confidence}
            onChange={(event) =>
              setConfidence(event.target.value as Confidence | "")
            }
          >
            <option value="">All</option>
            {CONFIDENCES.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="eng-checkbox">
          <input
            type="checkbox"
            checked={openOnly}
            onChange={(event) => setOpenOnly(event.target.checked)}
          />
          <span>Open only</span>
        </label>
      </Toolbar>
      {rows.length === 0 ? (
        <EmptyState
          title="No findings"
          description="Record findings with severity, evidence, and remediation."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(row) => row.id}
          label="Finding table"
        />
      )}
      <Dialog
        open={creating || editing !== null}
        onClose={close}
        title={editing ? `Edit ${editing.title}` : "Add finding"}
        description="Severity, confidence, and CVSS are kept independent to preserve analyst judgment."
        footer={
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void submit()}>
              Save finding
            </Button>
          </>
        }
      >
        <div className="eng-form-grid">
          <Field
            label="Title"
            value={draft.title}
            error={errors.title}
            onChange={(event) =>
              setDraft({ ...draft, title: event.target.value })
            }
          />
          <label className="eng-select">
            <span>Severity</span>
            <select
              value={draft.severity}
              onChange={(event) =>
                setDraft({ ...draft, severity: event.target.value as Severity })
              }
            >
              {SEVERITIES.map((item) => (
                <option key={item} value={item}>
                  {humanize(item)}
                </option>
              ))}
            </select>
          </label>
          <label className="eng-select">
            <span>Confidence</span>
            <select
              value={draft.confidence}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  confidence: event.target.value as Confidence,
                })
              }
            >
              {CONFIDENCES.map((item) => (
                <option key={item} value={item}>
                  {humanize(item)}
                </option>
              ))}
            </select>
          </label>
          <label className="eng-select">
            <span>Status</span>
            <select
              value={draft.status}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  status: event.target.value as FindingStatus,
                })
              }
            >
              {FINDING_STATUSES.map((item) => (
                <option key={item} value={item}>
                  {humanize(item)}
                </option>
              ))}
            </select>
          </label>
          <Field
            label="CVSS vector"
            value={draft.cvss_vector}
            error={errors.cvss_vector}
            placeholder="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"
            onChange={(event) =>
              setDraft({ ...draft, cvss_vector: event.target.value })
            }
          />
          <Field
            label="CWE"
            value={draft.cwe}
            onChange={(event) =>
              setDraft({ ...draft, cwe: event.target.value })
            }
          />
          <Field
            label="Additional CWEs"
            value={draft.cwes}
            onChange={(event) =>
              setDraft({ ...draft, cwes: event.target.value })
            }
          />
          <Field
            label="CVEs"
            value={draft.cves}
            onChange={(event) =>
              setDraft({ ...draft, cves: event.target.value })
            }
          />
          <Field
            label="Target ID"
            type="number"
            value={draft.target_id || ""}
            onChange={(event) =>
              setDraft({ ...draft, target_id: Number(event.target.value) })
            }
          />
          <Field
            label="Asset ID"
            type="number"
            value={draft.asset_id || ""}
            onChange={(event) =>
              setDraft({ ...draft, asset_id: Number(event.target.value) })
            }
          />
          <Field
            label="Service ID"
            type="number"
            value={draft.service_id || ""}
            onChange={(event) =>
              setDraft({ ...draft, service_id: Number(event.target.value) })
            }
          />
          <Field
            label="Owner"
            value={draft.owner}
            onChange={(event) =>
              setDraft({ ...draft, owner: event.target.value })
            }
          />
          <Field
            label="Tags"
            value={draft.tags}
            onChange={(event) =>
              setDraft({ ...draft, tags: event.target.value })
            }
          />
          <label className="eng-textarea">
            <span>Summary</span>
            <textarea
              rows={3}
              value={draft.summary}
              onChange={(event) =>
                setDraft({ ...draft, summary: event.target.value })
              }
            />
          </label>
          <label className="eng-textarea">
            <span>Reproduction steps</span>
            <textarea
              rows={4}
              value={draft.reproduction_steps}
              onChange={(event) =>
                setDraft({ ...draft, reproduction_steps: event.target.value })
              }
            />
          </label>
          <label className="eng-textarea">
            <span>Impact</span>
            <textarea
              rows={3}
              value={draft.impact}
              onChange={(event) =>
                setDraft({ ...draft, impact: event.target.value })
              }
            />
          </label>
          <label className="eng-textarea">
            <span>Remediation</span>
            <textarea
              rows={3}
              value={draft.remediation}
              onChange={(event) =>
                setDraft({ ...draft, remediation: event.target.value })
              }
            />
          </label>
          <Field
            label="References"
            value={draft.references}
            onChange={(event) =>
              setDraft({ ...draft, references: event.target.value })
            }
          />
        </div>
        {errors.reproduction_steps ? (
          <Banner tone="warning" title="Evidence required">
            {errors.reproduction_steps}
          </Banner>
        ) : null}
        {editing?.cvss ? (
          <div className="eng-cvss">
            <strong>
              CVSS {editing.cvss.version}: {formatScore(editing.cvss.score)}
            </strong>
            <span>{editing.cvss.severity}</span>
            <code>{editing.cvss.vector}</code>
          </div>
        ) : null}
        {selectedDuplicates.length ? (
          <div className="eng-duplicates">
            <strong>Possible duplicates</strong>
            <ul>
              {selectedDuplicates.map((match) => (
                <li key={match.candidate_id}>
                  <span>
                    #{match.candidate_id} · {formatScore(match.score)} ·{" "}
                    {match.reasons.join(", ")}
                  </span>
                  {onDuplicate ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        onDuplicate(editing?.id ?? 0, match.candidate_id)
                      }
                    >
                      Mark duplicate
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {editing && (editing.allowed_actions ?? []).length ? (
          <div className="eng-transitions">
            <strong>Lifecycle actions</strong>
            <div className="eng-row-actions">
              {(editing.allowed_actions ?? []).map((action) => (
                <Button
                  key={action}
                  size="sm"
                  variant="secondary"
                  onClick={() => onTransition?.(editing.id, action, {})}
                >
                  {transitionLabel(action)}
                </Button>
              ))}
            </div>
          </div>
        ) : null}
      </Dialog>
    </section>
  );
}
