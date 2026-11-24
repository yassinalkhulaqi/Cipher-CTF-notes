/** Visual report designer with drag sections, pagination preview, and redaction. */

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import type { ChangeEvent, DragEvent } from "react";

import { V3Panel, V3Stat } from "../../v3/components/V3Panel";
import { ReportDesignerClient } from "./client";
import {
  FORMAT_LABELS,
  ZOOM_LEVELS,
  countFindings,
  countSectionFindings,
  designSignature,
  formatBytes,
  kindLabel,
  pageLabel,
  paginationStats,
  redactionSummary,
  severityClass,
  severityLabel,
  severityRank,
  tocLine,
  truncate,
  zoomLabel,
  zoomScale,
  zoomStep,
} from "./format";
import {
  DESIGN_FORMATS,
  designerReducer,
  initialDesignerState,
  specFromState,
  type TextField,
} from "./state";
import type { LayoutSection, RenderFormat, ThemeSummary } from "./types";

import "./report-designer.css";

export interface ReportDesignerProps {
  client: ReportDesignerClient;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function ReportDesigner({ client }: ReportDesignerProps) {
  const [state, dispatch] = useReducer(
    designerReducer,
    undefined,
    initialDesignerState,
  );
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [health, setHealth] = useState<string>("offline");
  const [dragIndex, setDragIndex] = useState<number>(-1);
  const dragged = useRef<number>(-1);
  const signature = designSignature(state);
  const spec = useMemo(() => specFromState(state), [signature]);

  useEffect(() => {
    let active = true;
    Promise.all([client.health(), client.themes()])
      .then(([status, themeList]) => {
        if (!active) return;
        setHealth(`${status.status} · ${status.formats.length} formats`);
        setThemes(themeList.summaries);
      })
      .catch((error: unknown) => {
        if (active) dispatch({ type: "error", value: messageOf(error) });
      });
    return () => {
      active = false;
    };
  }, [client]);

  useEffect(() => {
    let active = true;
    dispatch({ type: "status", value: "loading" });
    client
      .design(spec)
      .then((result) => {
        if (active) dispatch({ type: "preview", value: result });
      })
      .catch((error: unknown) => {
        if (active) dispatch({ type: "error", value: messageOf(error) });
      });
    return () => {
      active = false;
    };
  }, [client, spec]);

  const field = useCallback(
    (name: TextField) => (event: ChangeEvent<HTMLInputElement>) =>
      dispatch({ type: "field", field: name, value: event.target.value }),
    [],
  );

  const onDragStart = (index: number) => (event: DragEvent<HTMLDivElement>) => {
    dragged.current = index;
    setDragIndex(index);
    event.dataTransfer.effectAllowed = "move";
  };

  const onDrop = (index: number) => (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (dragged.current >= 0) {
      dispatch({ type: "dropSection", from: dragged.current, to: index });
    }
    dragged.current = -1;
    setDragIndex(-1);
  };

  const plan = state.preview?.pagination;
  const stats = plan ? paginationStats(plan) : { pages: 0, items: 0, fills: 0 };
  const preview = state.preview?.redaction_preview;
  const includedCount = state.findings.length - state.excluded.length;
  const scale = zoomScale(state.zoom);
  const documentSections =
    (state.preview?.document as { sections?: LayoutSection[] } | undefined)
      ?.sections ?? [];

  const renderPrintPage = (index: number) => (
    <div
      className="rd-page"
      data-page={index}
      key={index}
      style={{ transform: `scale(${scale})` }}
    >
      <div className="rd-page__chrome">
        <span>{state.title}</span>
        <span>{pageLabel(index, stats.pages)}</span>
      </div>
      {index === 1 ? (
        <div className="rd-page__cover">
          <div className="rd-page__glyph">◆</div>
          <h2>{state.title}</h2>
          <p>{state.subtitle}</p>
          <p>{state.client}</p>
          <p className="rd-page__classification">{state.classification}</p>
        </div>
      ) : (
        <div className="rd-page__content">
          {index === 2 && state.options.toc ? (
            <section className="rd-page__toc" data-section="toc">
              <h3>Table of Contents</h3>
              <ol>
                {state.sections
                  .filter((section) => section.visible && section.includeToc)
                  .map((section) => (
                    <li key={section.key}>
                      {section.title} — {pageLabel(2, stats.pages)}
                    </li>
                  ))}
              </ol>
            </section>
          ) : null}
          {state.sections
            .filter((section) => section.visible)
            .map((section) => (
              <section
                className="rd-page__section"
                data-section={section.key}
                key={section.key}
              >
                <h3>{section.title}</h3>
                <p>{truncate(section.body, 240)}</p>
              </section>
            ))}
          {state.options.findings_section && index === stats.pages ? (
            <section className="rd-page__findings" data-section="findings">
              <h3>Findings</h3>
              {state.findings
                .filter((finding) => !state.excluded.includes(finding.ref))
                .sort(
                  (a, b) => severityRank(b.severity) - severityRank(a.severity),
                )
                .map((finding) => (
                  <article
                    className={`rd-finding ${severityClass(finding.severity)}`}
                    key={finding.ref}
                  >
                    <h4>{finding.title}</h4>
                    <p className="rd-finding__meta">
                      {severityLabel(finding.severity)} · {finding.status}
                    </p>
                    <p>{truncate(finding.summary, 160)}</p>
                  </article>
                ))}
            </section>
          ) : null}
        </div>
      )}
    </div>
  );

  return (
    <div
      className="report-designer"
      data-density="comfortable"
      data-print-preview={state.printPreview}
      data-theme={state.theme}
    >
      <header className="rd-header">
        <div>
          <span className="rd-eyebrow">Report Designer · v3</span>
          <h1>Visual Report Studio</h1>
          <p>
            Design, paginate, redact, and export a client-ready deliverable.
          </p>
        </div>
        <div className="rd-header__actions">
          <label className="rd-field">
            <span>Theme</span>
            <select
              aria-label="Report theme"
              data-testid="theme-picker"
              value={state.theme}
              onChange={(event) =>
                dispatch({ type: "theme", value: event.target.value })
              }
            >
              {(themes.length
                ? themes
                : [
                    {
                      key: state.theme,
                      name: state.theme,
                      description: "",
                      glyph: "◆",
                      page_size: "",
                      orientation: "",
                    },
                  ]
              ).map((theme) => (
                <option value={theme.key} key={theme.key}>
                  {theme.name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => dispatch({ type: "togglePrintPreview" })}
          >
            {state.printPreview ? "Exit print preview" : "Print-ready preview"}
          </button>
          <button type="button" onClick={() => window.print()}>
            Print
          </button>
        </div>
      </header>

      {state.error ? (
        <div className="rd-error" role="alert">
          {state.error}
        </div>
      ) : null}

      <div className="rd-stats">
        <V3Stat
          label="Pages"
          value={stats.pages}
          hint={`${stats.items} blocks`}
        />
        <V3Stat
          label="Findings"
          value={includedCount}
          hint={`${state.findings.length} total`}
          tone="good"
        />
        <V3Stat
          label="Redactions"
          value={preview?.total_matches ?? 0}
          hint={health}
        />
        <V3Stat
          label="Fill"
          value={`${Math.round(stats.fills * 100)}%`}
          hint="page usage"
        />
      </div>

      <div className="rd-layout">
        <V3Panel
          title="Design"
          subtitle="Drag to reorder sections"
          kind="report"
          density="compact"
        >
          <div className="rd-fields">
            <label className="rd-field">
              <span>Title</span>
              <input
                aria-label="Report title"
                value={state.title}
                onChange={field("title")}
              />
            </label>
            <label className="rd-field">
              <span>Client</span>
              <input
                aria-label="Client"
                value={state.client}
                onChange={field("client")}
              />
            </label>
            <label className="rd-field">
              <span>Classification</span>
              <input
                aria-label="Classification"
                value={state.classification}
                onChange={field("classification")}
              />
            </label>
          </div>

          <div className="rd-section-list" data-testid="section-list">
            {state.sections.map((section, index) => (
              <div
                className={`rd-section-row ${dragIndex === index ? "is-dragging" : ""} ${
                  state.selectedSection === section.key ? "is-selected" : ""
                }`}
                data-section={section.key}
                draggable
                key={section.key}
                onDragStart={onDragStart(index)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={onDrop(index)}
                onClick={() => dispatch({ type: "select", key: section.key })}
              >
                <span className="rd-grip" aria-hidden="true">
                  ⠿
                </span>
                <div className="rd-section-row__body">
                  <strong>{section.title}</strong>
                  <small>
                    {kindLabel(section.kind)} · level {section.level}
                  </small>
                </div>
                <div className="rd-section-row__toggles">
                  <button
                    type="button"
                    aria-label={`Toggle visibility of ${section.title}`}
                    data-active={section.visible}
                    onClick={(event) => {
                      event.stopPropagation();
                      dispatch({ type: "toggleVisible", key: section.key });
                    }}
                  >
                    {section.visible ? "Show" : "Hide"}
                  </button>
                  <button
                    type="button"
                    aria-label={`Toggle table of contents for ${section.title}`}
                    data-active={section.includeToc}
                    onClick={(event) => {
                      event.stopPropagation();
                      dispatch({ type: "toggleToc", key: section.key });
                    }}
                  >
                    ToC
                  </button>
                  <button
                    type="button"
                    aria-label={`Toggle page break before ${section.title}`}
                    data-active={section.pageBreakBefore}
                    onClick={(event) => {
                      event.stopPropagation();
                      dispatch({ type: "togglePageBreak", key: section.key });
                    }}
                  >
                    Break
                  </button>
                  <button
                    type="button"
                    aria-label={`Move ${section.title} up`}
                    onClick={(event) => {
                      event.stopPropagation();
                      dispatch({
                        type: "moveSection",
                        key: section.key,
                        delta: -1,
                      });
                    }}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={`Move ${section.title} down`}
                    onClick={(event) => {
                      event.stopPropagation();
                      dispatch({
                        type: "moveSection",
                        key: section.key,
                        delta: 1,
                      });
                    }}
                  >
                    ↓
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="rd-buttons">
            <button
              type="button"
              onClick={() => dispatch({ type: "addSection", kind: "text" })}
            >
              Add text section
            </button>
            <button
              type="button"
              onClick={() => dispatch({ type: "addSection", kind: "appendix" })}
            >
              Add appendix
            </button>
            <button
              type="button"
              disabled={!state.selectedSection}
              onClick={() =>
                dispatch({ type: "removeSection", key: state.selectedSection })
              }
            >
              Remove selected
            </button>
          </div>

          <h3 className="rd-subhead">Findings</h3>
          <div className="rd-finding-list">
            {state.findings.map((finding) => {
              const included = !state.excluded.includes(finding.ref);
              return (
                <label
                  className="rd-finding-toggle"
                  key={finding.ref}
                  data-included={included}
                >
                  <input
                    type="checkbox"
                    aria-label={`Include ${finding.title}`}
                    checked={included}
                    onChange={() =>
                      dispatch({ type: "toggleFinding", ref: finding.ref })
                    }
                  />
                  <span className={severityClass(finding.severity)}>
                    {severityLabel(finding.severity)}
                  </span>
                  <span>{truncate(finding.title, 36)}</span>
                  <small>{finding.evidence.length} evidence</small>
                </label>
              );
            })}
          </div>
        </V3Panel>

        <V3Panel
          title="Pagination preview"
          subtitle={`${stats.pages} pages · ${state.status}`}
          kind="section"
          actions={
            <div className="rd-zoom" role="group" aria-label="Preview zoom">
              <button
                type="button"
                aria-label="Zoom out"
                onClick={() =>
                  dispatch({ type: "zoom", value: zoomStep(state.zoom, -1) })
                }
              >
                −
              </button>
              <span data-testid="zoom-label">{zoomLabel(state.zoom)}</span>
              <button
                type="button"
                aria-label="Zoom in"
                onClick={() =>
                  dispatch({ type: "zoom", value: zoomStep(state.zoom, 1) })
                }
              >
                +
              </button>
            </div>
          }
        >
          <div className="rd-pages" data-zoom={state.zoom}>
            {Array.from({ length: Math.max(1, stats.pages) }, (_, index) =>
              renderPrintPage(index + 1),
            )}
          </div>
          <div className="rd-toc-preview">
            <h3 className="rd-subhead">Resolved table of contents</h3>
            {state.preview?.toc.length ? (
              <ol>
                {state.preview.toc.map((entry) => (
                  <li key={entry.anchor}>
                    <a href={`#${entry.anchor}`}>
                      {tocLine(entry, stats.pages)}
                    </a>
                  </li>
                ))}
              </ol>
            ) : (
              <p>Waiting for a design preview…</p>
            )}
          </div>
        </V3Panel>

        <V3Panel
          title="Redaction & export"
          subtitle="Live preview of replacements"
          kind="finding"
          density="compact"
        >
          <div className="rd-redactions">
            {state.redactions.map((rule, index) => (
              <div
                className="rd-redaction"
                data-rule={rule.name}
                key={`${rule.name}-${index}`}
              >
                <label className="rd-redaction__head">
                  <input
                    type="checkbox"
                    aria-label={`Enable ${rule.name} redaction`}
                    checked={rule.enabled}
                    onChange={(event) =>
                      dispatch({
                        type: "updateRedaction",
                        index,
                        patch: { enabled: event.target.checked },
                      })
                    }
                  />
                  <input
                    aria-label={`${rule.name} rule name`}
                    value={rule.name}
                    onChange={(event) =>
                      dispatch({
                        type: "updateRedaction",
                        index,
                        patch: { name: event.target.value },
                      })
                    }
                  />
                </label>
                <input
                  aria-label={`${rule.name} pattern`}
                  value={rule.pattern}
                  onChange={(event) =>
                    dispatch({
                      type: "updateRedaction",
                      index,
                      patch: { pattern: event.target.value },
                    })
                  }
                />
                <div className="rd-redaction__row">
                  <input
                    aria-label={`${rule.name} replacement`}
                    value={rule.replacement}
                    onChange={(event) =>
                      dispatch({
                        type: "updateRedaction",
                        index,
                        patch: { replacement: event.target.value },
                      })
                    }
                  />
                  <button
                    type="button"
                    aria-label={`Remove ${rule.name}`}
                    onClick={() => dispatch({ type: "removeRedaction", index })}
                  >
                    ×
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="rd-buttons">
            <button
              type="button"
              onClick={() => dispatch({ type: "addRedaction" })}
            >
              Add rule
            </button>
            <button
              type="button"
              aria-pressed={state.showRedactions}
              onClick={() => dispatch({ type: "toggleRedactions" })}
            >
              {state.showRedactions ? "Hide matches" : "Show matches"}
            </button>
          </div>

          {state.showRedactions ? (
            <div className="rd-matches" data-testid="redaction-preview">
              <h3 className="rd-subhead">
                {preview ? redactionSummary(preview) : "No matches"}
              </h3>
              {(preview?.spans ?? []).map((span, index) => (
                <div
                  className="rd-match"
                  data-rule={span.rule}
                  key={`${span.rule}-${index}`}
                >
                  <span>{truncate(span.before, 18)}</span>
                  <mark>{span.matched}</mark>
                  <span>{truncate(span.after, 18)}</span>
                  <small>→ {truncate(span.replacement, 16)}</small>
                </div>
              ))}
              {!preview?.spans.length ? (
                <p>No sensitive values detected.</p>
              ) : null}
            </div>
          ) : null}

          <h3 className="rd-subhead">Export formats</h3>
          <div className="rd-formats">
            {DESIGN_FORMATS.map((format) => (
              <label key={format} data-active={state.formats.includes(format)}>
                <input
                  type="checkbox"
                  aria-label={`Export ${FORMAT_LABELS[format]}`}
                  checked={state.formats.includes(format)}
                  onChange={() => dispatch({ type: "toggleFormat", format })}
                />
                {FORMAT_LABELS[format]}
              </label>
            ))}
          </div>
          <div className="rd-outputs">
            {(state.preview?.outputs ?? []).map((output) => (
              <span key={output.format} data-format={output.format}>
                {output.filename} · {formatBytes(output.bytes)}
              </span>
            ))}
            {!state.preview?.outputs.length ? (
              <span>Run a design to see exports.</span>
            ) : null}
          </div>
          <button
            type="button"
            className="rd-primary"
            onClick={() => {
              const current = state.preview?.outputs.find(
                (output) => output.format === state.activeFormat,
              );
              if (current?.content)
                downloadOutput(
                  current.filename,
                  current.content,
                  current.format,
                );
            }}
          >
            Download {FORMAT_LABELS[state.activeFormat]}
          </button>
          <div
            className="rd-format-tabs"
            role="tablist"
            aria-label="Active export format"
          >
            {DESIGN_FORMATS.map((format: RenderFormat) => (
              <button
                type="button"
                role="tab"
                aria-selected={state.activeFormat === format}
                key={format}
                onClick={() =>
                  dispatch({ type: "activeFormat", value: format })
                }
              >
                {FORMAT_LABELS[format]}
              </button>
            ))}
          </div>
          <span className="rd-signature" data-testid="design-signature">
            {signature.slice(0, 12)}
          </span>
          <span className="rd-counts">
            {countFindings(state.findings)} candidates ·{" "}
            {countSectionFindings(documentSections)} section findings
          </span>
          <ul className="rd-zoom-levels" aria-label="Zoom presets">
            {ZOOM_LEVELS.map((level) => (
              <li key={level} data-level={level}>
                {zoomLabel(level)}
              </li>
            ))}
          </ul>
        </V3Panel>
      </div>
    </div>
  );
}

function downloadOutput(
  filename: string,
  content: string,
  format: RenderFormat,
): void {
  const mime =
    format === "html"
      ? "text/html"
      : format === "json"
        ? "application/json"
        : "text/plain";
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
