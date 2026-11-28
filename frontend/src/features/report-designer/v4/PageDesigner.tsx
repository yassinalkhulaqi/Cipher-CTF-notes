/** The v4 report page designer: sections, themes, geometry and paginated preview. */

import { useMemo, useReducer } from "react";
import type { ChangeEvent, CSSProperties, ReactNode } from "react";

import type {
  ExportFormatV4,
  PageSizeV4,
  PaginatedPageV4,
  ReportLayoutV4,
  ReportSectionV4,
  SectionKindV4,
  ThemeDescriptorV4,
} from "./client";
import {
  SECTION_KINDS,
  ZOOM_MODES,
  canMoveSection,
  describeState,
  initialDesignerState,
  pageDimensions,
  pageSummary,
  reduceDesigner,
  sectionTitle,
  selectedSection,
  statusTone,
  visiblePage,
  zoomScale,
  type DesignerActionV4,
} from "./state";
import "./report-designer.css";

const DEFAULT_THEMES: readonly ThemeDescriptorV4[] = [
  {
    name: "classic",
    parent: "base",
    lineage: ["base", "classic"],
    description: "Editorial",
  },
  {
    name: "modern",
    parent: "classic",
    lineage: ["base", "classic", "modern"],
    description: "Executive",
  },
  {
    name: "compact",
    parent: "base",
    lineage: ["base", "compact"],
    description: "Dense",
  },
  {
    name: "ink",
    parent: "modern",
    lineage: ["base", "classic", "modern", "ink"],
    description: "Monochrome",
  },
  {
    name: "client",
    parent: "compact",
    lineage: ["base", "compact", "client"],
    description: "Branded",
  },
];

const PAGE_SIZES: readonly PageSizeV4[] = ["a4", "letter", "a5"];
const FORMATS: readonly ExportFormatV4[] = ["html", "markdown"];

export interface PageDesignerProps {
  initialLayout?: Partial<ReportLayoutV4>;
  initialThemes?: ThemeDescriptorV4[];
  initialPages?: PaginatedPageV4[];
  onSave?: (layout: ReportLayoutV4) => void;
  onRender?: (layout: ReportLayoutV4, format: ExportFormatV4) => void;
}

export function sectionRowLabel(
  section: ReportSectionV4,
  index: number,
): string {
  return `${index + 1}. ${section.title} · ${section.entries.length} entries`;
}

export function lineRows(
  page: PaginatedPageV4 | undefined,
): Array<{ key: string; text: string }> {
  if (!page) return [];
  return page.lines.map((line, index) => ({
    key: `${page.number}-${index}`,
    text: line || "\u00a0",
  }));
}

export function themeOptions(themes: ThemeDescriptorV4[]): string[] {
  return themes.length > 0
    ? themes.map((theme) => theme.name)
    : DEFAULT_THEMES.map((theme) => theme.name);
}

export function PageDesigner({
  initialLayout,
  initialThemes,
  initialPages,
  onSave,
  onRender,
}: PageDesignerProps) {
  const [state, dispatch] = useReducer(reduceDesigner, undefined, () => {
    let seeded = initialDesignerState({
      ...initialLayout,
      sections: [...(initialLayout?.sections ?? [])],
    });
    if (initialThemes)
      seeded = reduceDesigner(seeded, {
        type: "set-themes",
        themes: initialThemes,
      });
    if (initialPages)
      seeded = reduceDesigner(seeded, {
        type: "set-pages",
        pages: initialPages,
      });
    return seeded;
  });
  const memoized = useMemo(
    () => ({
      summary: pageSummary(state.pages),
      current: visiblePage(state),
      dimensions: pageDimensions(state.layout, state.zoom),
      selected: selectedSection(state),
      description: describeState(state),
      themes: themeOptions(state.themes),
    }),
    [state],
  );

  const selectedIndex = state.selectedSection;
  const canMoveUp = canMoveSection(state, selectedIndex, -1);
  const canMoveDown = canMoveSection(state, selectedIndex, 1);
  const pageStyle: CSSProperties = {
    width: `${memoized.dimensions.width}px`,
    minHeight: `${memoized.dimensions.height}px`,
  };

  function changeTheme(event: ChangeEvent<HTMLSelectElement>): void {
    dispatch({ type: "select-theme", theme: event.target.value });
  }

  function addSection(event: ChangeEvent<HTMLSelectElement>): void {
    const kind = event.target.value as SectionKindV4;
    event.target.value = "";
    if (SECTION_KINDS.includes(kind)) dispatch({ type: "add-section", kind });
  }

  function move(direction: -1 | 1): void {
    if (direction === -1 && !canMoveUp) return;
    if (direction === 1 && !canMoveDown) return;
    dispatch({ type: "move-section", index: selectedIndex, direction });
  }

  function button(
    label: string,
    action: DesignerActionV4,
    testId: string,
    disabled = false,
  ): ReactNode {
    return (
      <button
        type="button"
        className="v4-btn rd4__action"
        data-testid={testId}
        disabled={disabled}
        onClick={() => dispatch(action)}
      >
        {label}
      </button>
    );
  }

  return (
    <section
      className="rd4"
      data-testid="rd4-root"
      aria-label="Report designer"
    >
      <header className="rd4__header">
        <div>
          <p className="rd4__eyebrow">v4 report studio</p>
          <h1 className="rd4__title">Page designer</h1>
          <p className="rd4__lede">
            Compose sections, choose a theme and inspect deterministic
            pagination before export.
          </p>
        </div>
        <div className="rd4__header-actions">
          <span
            className={`v4-chip rd4__status rd4__status--${statusTone(state.status)}`}
          >
            {state.status}
          </span>
          <button
            type="button"
            className="v4-btn"
            data-testid="rd4-save"
            onClick={() => onSave?.(state.layout)}
          >
            Save layout
          </button>
          <button
            type="button"
            className="v4-btn v4-btn--primary"
            data-testid="rd4-render"
            onClick={() => onRender?.(state.layout, state.format)}
          >
            Render {state.format}
          </button>
        </div>
      </header>

      <div className="rd4__toolbar" role="toolbar" aria-label="Page settings">
        <label className="rd4__field">
          <span className="rd4__field-label">Report title</span>
          <input
            className="rd4__input"
            data-testid="rd4-title"
            value={state.layout.title}
            onChange={(event) =>
              dispatch({ type: "set-title", title: event.target.value })
            }
          />
        </label>
        <label className="rd4__field">
          <span className="rd4__field-label">Theme</span>
          <select
            className="rd4__input"
            data-testid="rd4-theme"
            value={state.layout.theme}
            onChange={changeTheme}
          >
            {memoized.themes.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="rd4__group">
          <legend className="rd4__field-label">Page size</legend>
          <div className="rd4__segmented">
            {PAGE_SIZES.map((size) =>
              button(
                size.toUpperCase(),
                { type: "set-page-size", pageSize: size },
                `rd4-size-${size}`,
              ),
            )}
          </div>
        </fieldset>
        <fieldset className="rd4__group">
          <legend className="rd4__field-label">Orientation</legend>
          <div className="rd4__segmented">
            {button(
              "Portrait",
              { type: "set-orientation", orientation: "portrait" },
              "rd4-portrait",
            )}
            {button(
              "Landscape",
              { type: "set-orientation", orientation: "landscape" },
              "rd4-landscape",
            )}
          </div>
        </fieldset>
      </div>

      <div className="rd4__workspace">
        <aside className="rd4__sections v4-panel" data-testid="rd4-sections">
          <div className="rd4__panel-head">
            <h2 className="rd4__panel-title">Sections</h2>
            <span className="v4-chip">{state.layout.sections.length}</span>
          </div>
          <ol className="rd4__section-list">
            {state.layout.sections.map((section, index) => (
              <li
                key={`${section.kind}-${index}`}
                className="rd4__section-item"
              >
                <button
                  type="button"
                  data-testid={`rd4-section-${index}`}
                  className={`rd4__section-button ${selectedIndex === index ? "rd4__section-button--active" : ""}`}
                  onClick={() => dispatch({ type: "select-section", index })}
                >
                  <span className="v4-chip v4-chip--accent">
                    {section.kind}
                  </span>
                  <span className="rd4__section-name">
                    {sectionRowLabel(section, index)}
                  </span>
                </button>
                <div className="rd4__section-tools">
                  <button
                    type="button"
                    className="rd4__icon-button"
                    data-testid={`rd4-break-${index}`}
                    aria-pressed={section.page_break_before}
                    title="Toggle page break before"
                    onClick={() => dispatch({ type: "toggle-break", index })}
                  >
                    {section.page_break_before ? "break" : "flow"}
                  </button>
                  <button
                    type="button"
                    className="rd4__icon-button"
                    data-testid={`rd4-up-${index}`}
                    disabled={!canMoveSection(state, index, -1)}
                    onClick={() => move(-1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="rd4__icon-button"
                    data-testid={`rd4-down-${index}`}
                    disabled={!canMoveSection(state, index, 1)}
                    onClick={() => move(1)}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="rd4__icon-button"
                    data-testid={`rd4-remove-${index}`}
                    onClick={() => dispatch({ type: "remove-section", index })}
                  >
                    ×
                  </button>
                </div>
              </li>
            ))}
          </ol>
          {state.layout.sections.length === 0 ? (
            <p className="v4-empty" data-testid="rd4-empty">
              No sections yet. Add one to begin.
            </p>
          ) : null}
          <label className="rd4__field rd4__add">
            <span className="rd4__field-label">Add section</span>
            <select
              className="rd4__input"
              data-testid="rd4-add-kind"
              onChange={addSection}
              defaultValue=""
            >
              <option value="" disabled>
                Choose a kind
              </option>
              {SECTION_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {sectionTitle(kind)}
                </option>
              ))}
            </select>
          </label>
          <div className="rd4__selection" data-testid="rd4-selection">
            <span className="rd4__field-label">Selected</span>
            <strong>{memoized.selected?.title ?? "None"}</strong>
            <span>{memoized.selected?.entries.length ?? 0} entries</span>
          </div>
        </aside>

        <main className="rd4__preview" data-testid="rd4-preview">
          <div className="rd4__preview-bar">
            <div className="rd4__segmented" aria-label="Zoom modes">
              {ZOOM_MODES.map((zoom) =>
                button(
                  zoom === "fit" ? "Fit" : `${zoom}%`,
                  { type: "set-zoom", zoom },
                  `rd4-zoom-${zoom}`,
                ),
              )}
            </div>
            <div className="rd4__pagination" aria-label="Page navigation">
              <button
                type="button"
                className="v4-btn"
                data-testid="rd4-prev"
                disabled={state.previewPage <= 1}
                onClick={() =>
                  dispatch({ type: "set-page", page: state.previewPage - 1 })
                }
              >
                Previous
              </button>
              <span className="v4-chip" data-testid="rd4-page-indicator">
                {state.previewPage} / {Math.max(1, memoized.summary.total)}
              </span>
              <button
                type="button"
                className="v4-btn"
                data-testid="rd4-next"
                disabled={state.previewPage >= memoized.summary.total}
                onClick={() =>
                  dispatch({ type: "set-page", page: state.previewPage + 1 })
                }
              >
                Next
              </button>
            </div>
            <label className="rd4__field">
              <span className="rd4__field-label">Format</span>
              <select
                className="rd4__input"
                data-testid="rd4-format"
                value={state.format}
                onChange={(event) =>
                  dispatch({
                    type: "set-format",
                    format: event.target.value as ExportFormatV4,
                  })
                }
              >
                {FORMATS.map((format) => (
                  <option key={format} value={format}>
                    {format}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="rd4__canvas v4-scroll">
            <article
              className="rd4__sheet"
              data-testid="rd4-sheet"
              style={pageStyle}
            >
              <div className="rd4__sheet-meta">{memoized.dimensions.label}</div>
              <h2 className="rd4__sheet-title">
                {memoized.current?.title || state.layout.title}
              </h2>
              <div className="rd4__lines" data-testid="rd4-lines">
                {lineRows(memoized.current).map((row) => (
                  <div key={row.key} className="rd4__line">
                    {row.text}
                  </div>
                ))}
              </div>
              <footer className="rd4__sheet-footer">
                Page {memoized.current?.number ?? 0} of {memoized.summary.total}
              </footer>
            </article>
          </div>

          <div className="rd4__stats" data-testid="rd4-stats">
            <span className="rd4__stat">Pages: {memoized.summary.total}</span>
            <span className="rd4__stat">Lines: {memoized.summary.lines}</span>
            <span className="rd4__stat">
              Findings: {memoized.summary.byKind.findings}
            </span>
            <span className="rd4__stat">
              Zoom: {Math.round(zoomScale(state.zoom) * 100)}%
            </span>
          </div>
        </main>
      </div>

      <footer className="rd4__footer">
        <span className="rd4__description">{memoized.description}</span>
        <span
          className={`rd4__message rd4__message--${statusTone(state.status)}`}
        >
          {state.message || "Ready to design"}
        </span>
      </footer>
    </section>
  );
}

export default PageDesigner;
