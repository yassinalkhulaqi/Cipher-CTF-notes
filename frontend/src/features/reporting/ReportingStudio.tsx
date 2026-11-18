import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useState,
  type ChangeEvent,
} from "react";
import { ReportingClient } from "./client";
import {
  displayName,
  evidenceLabel,
  formatBytes,
  formatConfidence,
  formatCount,
  manifestLines,
  previewRows,
  riskClass,
  severityBar,
  severityClass,
  severityLabel,
  summarizeSeverity,
  truncate,
} from "./format";
import {
  REPORT_FORMATS,
  builderReducer,
  configFromState,
  initialBuilderState,
  previewSignature,
  splitList,
  type BuilderTextField,
} from "./state";
import type {
  ProfileSummary,
  ReportFormat,
  ReportSection,
  ReportingHealth,
  TemplateSummary,
} from "./types";

export interface ReportingStudioProps {
  client: ReportingClient;
}

type StudioTab = "build" | "validate" | "redact";

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function ReportingStudio({ client }: ReportingStudioProps) {
  const [state, dispatch] = useReducer(builderReducer, undefined, () =>
    initialBuilderState(),
  );
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [profiles, setProfiles] = useState<ProfileSummary[]>([]);
  const [health, setHealth] = useState<ReportingHealth | null>(null);
  const [outline, setOutline] = useState<ReportSection[]>([]);
  const [tab, setTab] = useState<StudioTab>("build");
  const signature = previewSignature(state);
  const config = useMemo(() => configFromState(state), [signature]);

  useEffect(() => {
    let active = true;
    Promise.all([client.health(), client.templates(), client.profiles()])
      .then(([status, templateList, profileList]) => {
        if (!active) return;
        setHealth(status);
        setTemplates(templateList);
        setProfiles(profileList);
      })
      .catch((error: unknown) => {
        if (active) dispatch({ type: "error", value: errorText(error) });
      });
    return () => {
      active = false;
    };
  }, [client]);

  useEffect(() => {
    let active = true;
    client
      .preview(config, state.generatedAt)
      .then((preview) => {
        if (active) dispatch({ type: "preview", value: preview });
      })
      .catch((error: unknown) => {
        if (active) dispatch({ type: "error", value: errorText(error) });
      });
    return () => {
      active = false;
    };
  }, [client, config, state.generatedAt]);

  useEffect(() => {
    let active = true;
    client
      .sections(state.template)
      .then((data) => {
        if (active) setOutline(data.sections);
      })
      .catch((error: unknown) => {
        if (active) dispatch({ type: "error", value: errorText(error) });
      });
    return () => {
      active = false;
    };
  }, [client, state.template]);

  const field = useCallback(
    (name: BuilderTextField) =>
      (
        event: ChangeEvent<
          HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
        >,
      ) =>
        dispatch({ type: "field", field: name, value: event.target.value }),
    [],
  );

  const listField = useCallback(
    (name: "scope" | "tags" | "statuses") =>
      (event: ChangeEvent<HTMLTextAreaElement>) =>
        dispatch({
          type: "list",
          field: name,
          value: splitList(event.target.value),
        }),
    [],
  );

  const renderReport = useCallback(async () => {
    dispatch({ type: "busy", value: true });
    try {
      const rendered = await client.render(
        configFromState(state),
        state.format,
        state.profile,
        state.generatedAt,
      );
      dispatch({ type: "rendered", value: rendered });
    } catch (error) {
      dispatch({ type: "error", value: errorText(error) });
    }
  }, [client, state]);

  const validateReport = useCallback(async () => {
    dispatch({ type: "busy", value: true });
    try {
      const report = await client.validate(
        configFromState(state),
        state.generatedAt,
      );
      dispatch({ type: "validation", value: report });
      dispatch({ type: "busy", value: false });
    } catch (error) {
      dispatch({ type: "error", value: errorText(error) });
    }
  }, [client, state]);

  const previewRedaction = useCallback(async () => {
    try {
      const result = await client.redact(state.redactionText, { context: 24 });
      dispatch({ type: "redaction", value: result });
    } catch (error) {
      dispatch({ type: "error", value: errorText(error) });
    }
  }, [client, state.redactionText]);

  const moveSection = useCallback(
    async (index: number, offset: number) => {
      const target = index + offset;
      if (!outline.length || target < 0 || target >= outline.length) return;
      const reordered = outline.slice();
      const current = reordered[index];
      reordered[index] = reordered[target];
      reordered[target] = current;
      try {
        const data = await client.reorder(
          reordered,
          "",
          reordered.map((section) => section.identifier),
        );
        setOutline(data.sections);
      } catch (error) {
        dispatch({ type: "error", value: errorText(error) });
      }
    },
    [client, outline],
  );

  const download = useCallback(() => {
    const rendered = state.rendered;
    if (!rendered) return;
    const blob = new Blob([rendered.content], {
      type: rendered.mime || "text/plain",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = rendered.filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [state.rendered]);

  const bar = severityBar(state.preview?.severity ?? null);
  const rows = previewRows(state.preview);
  const issues = state.validation?.issues ?? [];

  return (
    <section className="reporting-studio" data-namespace="reporting">
      <header className="studio-header">
        <div>
          <span className="studio-eyebrow">V2 · Reporting Studio</span>
          <h1>Compose deterministic engagement reports</h1>
          <p>
            {health
              ? `${health.templates.length} templates · ${health.formats.length} formats · ${health.profiles.length} print profiles`
              : "Loading reporting capabilities…"}
          </p>
        </div>
        <div className="studio-actions">
          <button type="button" onClick={() => setTab("build")}>
            Build
          </button>
          <button type="button" onClick={() => setTab("validate")}>
            Validate
          </button>
          <button type="button" onClick={() => setTab("redact")}>
            Redact
          </button>
          <button type="button" onClick={() => dispatch({ type: "reset" })}>
            Reset
          </button>
        </div>
      </header>

      {state.error ? (
        <div className="studio-error" role="alert">
          {state.error}
        </div>
      ) : null}

      <div className="studio-grid">
        <form
          className="studio-form"
          onSubmit={(event) => event.preventDefault()}
        >
          <fieldset>
            <legend>Document</legend>
            <label>
              Title
              <input value={state.title} onChange={field("title")} />
            </label>
            <label>
              Template
              <select value={state.template} onChange={field("template")}>
                {templates.length ? (
                  templates.map((template) => (
                    <option key={template.key} value={template.key}>
                      {template.name}
                    </option>
                  ))
                ) : (
                  <option value={state.template}>{state.template}</option>
                )}
              </select>
            </label>
            <label>
              Client
              <input value={state.client} onChange={field("client")} />
            </label>
            <label>
              Author
              <input value={state.author} onChange={field("author")} />
            </label>
            <label>
              Classification
              <input
                value={state.classification}
                onChange={field("classification")}
              />
            </label>
            <label>
              Generated at
              <input
                placeholder="ISO-8601 timestamp"
                value={state.generatedAt}
                onChange={field("generatedAt")}
              />
            </label>
          </fieldset>

          <fieldset>
            <legend>Filters</legend>
            <label>
              Tags
              <textarea
                value={state.tags.join(", ")}
                onChange={listField("tags")}
              />
            </label>
            <label>
              Statuses
              <textarea
                value={state.statuses.join(", ")}
                onChange={listField("statuses")}
              />
            </label>
            <label>
              Scope
              <textarea
                value={state.scope.join("\n")}
                onChange={listField("scope")}
              />
            </label>
            <label>
              Minimum severity
              <select
                value={state.minimumSeverity}
                onChange={field("minimumSeverity")}
              >
                {["info", "low", "medium", "high", "critical"].map((value) => (
                  <option key={value} value={value}>
                    {severityLabel(value)}
                  </option>
                ))}
              </select>
            </label>
          </fieldset>

          <fieldset>
            <legend>Output</legend>
            <label>
              Format
              <select
                value={state.format}
                onChange={(event) =>
                  dispatch({
                    type: "format",
                    value: event.target.value as ReportFormat,
                  })
                }
              >
                {REPORT_FORMATS.map((format) => (
                  <option key={format} value={format}>
                    {displayName(format)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Print profile
              <select value={state.profile} onChange={field("profile")}>
                {profiles.length ? (
                  profiles.map((profile) => (
                    <option
                      key={String(profile.name)}
                      value={String(profile.name)}
                    >
                      {displayName(String(profile.name))}
                    </option>
                  ))
                ) : (
                  <option value={state.profile}>{state.profile}</option>
                )}
              </select>
            </label>
            <label>
              Page size
              <input value={state.pageSize} onChange={field("pageSize")} />
            </label>
            <label>
              Orientation
              <select value={state.orientation} onChange={field("orientation")}>
                <option value="portrait">Portrait</option>
                <option value="landscape">Landscape</option>
              </select>
            </label>
            <label>
              Closing notes
              <textarea value={state.notes} onChange={field("notes")} />
            </label>
            <label className="studio-check">
              <input
                type="checkbox"
                checked={state.includeEvidence}
                onChange={(event) =>
                  dispatch({
                    type: "toggle",
                    field: "includeEvidence",
                    value: event.target.checked,
                  })
                }
              />
              Include evidence
            </label>
            <label className="studio-check">
              <input
                type="checkbox"
                checked={state.includeAppendices}
                onChange={(event) =>
                  dispatch({
                    type: "toggle",
                    field: "includeAppendices",
                    value: event.target.checked,
                  })
                }
              />
              Include appendices
            </label>
            <label className="studio-check">
              <input
                type="checkbox"
                checked={state.redactSensitive}
                onChange={(event) =>
                  dispatch({
                    type: "toggle",
                    field: "redactSensitive",
                    value: event.target.checked,
                  })
                }
              />
              Redact sensitive values
            </label>
          </fieldset>

          <div className="studio-buttons">
            <button type="button" disabled={state.busy} onClick={renderReport}>
              {state.busy ? "Working…" : "Render report"}
            </button>
            <button
              type="button"
              disabled={state.busy}
              onClick={validateReport}
            >
              Validate
            </button>
            <button type="button" disabled={!state.rendered} onClick={download}>
              Download
            </button>
          </div>
        </form>

        <aside className="studio-preview">
          <div className="studio-summary">
            <span
              className={`risk-badge ${riskClass(state.preview?.severity.risk_level ?? "info")}`}
            >
              {state.preview?.severity.risk_level ?? "idle"}
            </span>
            <strong>
              {formatCount(state.preview?.finding_count ?? 0)} findings
            </strong>
            <span>{summarizeSeverity(state.preview?.severity ?? null)}</span>
          </div>

          <div className="severity-bar" aria-label="Severity distribution">
            {bar.map((item) => (
              <div
                key={item.name}
                className={severityClass(item.name)}
                style={{ width: `${item.percent}%` }}
                title={`${severityLabel(item.name)}: ${formatCount(item.count)}`}
              />
            ))}
          </div>

          {tab === "build" ? (
            <>
              <h2>Outline</h2>
              <ol className="studio-outline">
                {rows.map((row) => (
                  <li key={row.identifier} data-level={row.level}>
                    <span>{row.title}</span>
                    <small>{formatCount(row.finding_count)}</small>
                  </li>
                ))}
              </ol>
              <h2>Section order</h2>
              <ul className="studio-sections">
                {outline.map((section, index) => (
                  <li key={section.identifier}>
                    <span>{section.title}</span>
                    <button
                      type="button"
                      onClick={() => void moveSection(index, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => void moveSection(index, 1)}
                    >
                      ↓
                    </button>
                  </li>
                ))}
              </ul>
              <h2>Evidence</h2>
              <dl className="studio-evidence">
                {Object.entries(state.preview?.evidence ?? {}).map(
                  ([key, value]) => (
                    <div key={key}>
                      <dt>{evidenceLabel(key)}</dt>
                      <dd>{formatCount(value)}</dd>
                    </div>
                  ),
                )}
              </dl>
              <h2>Warnings</h2>
              <ul className="studio-warnings">
                {(state.preview?.warnings ?? []).map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </>
          ) : null}

          {tab === "validate" ? (
            <div className="studio-validation">
              <h2>Validation</h2>
              <p>
                {state.validation
                  ? `${formatCount(state.validation.errors)} errors · ${formatCount(state.validation.warnings)} warnings`
                  : "Run validation to inspect the report configuration."}
              </p>
              <ul>
                {issues.map((issue) => (
                  <li
                    key={`${issue.code}-${issue.path}`}
                    className={issue.severity}
                  >
                    <strong>{issue.code}</strong>
                    <span>{issue.message}</span>
                    <code>{issue.path}</code>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {tab === "redact" ? (
            <div className="studio-redaction">
              <h2>Redaction preview</h2>
              <textarea
                value={state.redactionText}
                onChange={field("redactionText")}
                placeholder="flag{example} 10.0.0.1"
              />
              <button type="button" onClick={() => void previewRedaction()}>
                Preview redaction
              </button>
              <pre>{state.redaction?.text || "No redaction preview yet."}</pre>
              <ul>
                {(state.redaction?.applied ?? []).map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
              {(state.redaction?.preview ?? []).map((span, index) => (
                <div key={`${span.rule}-${index}`} className="redaction-span">
                  <strong>{span.rule}</strong>
                  <span>{truncate(span.matched, 60)}</span>
                  <code>{span.replacement}</code>
                </div>
              ))}
            </div>
          ) : null}

          {state.rendered ? (
            <div className="studio-output">
              <h2>Output</h2>
              <p>
                {state.rendered.filename} · {state.rendered.mime} ·{" "}
                {formatBytes(state.rendered.content.length)}
              </p>
              <p>Confidence gate: {formatConfidence(1)}</p>
              <ul>
                {manifestLines(state.rendered.manifest).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <pre>{truncate(state.rendered.content, 2400)}</pre>
            </div>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

export default ReportingStudio;
