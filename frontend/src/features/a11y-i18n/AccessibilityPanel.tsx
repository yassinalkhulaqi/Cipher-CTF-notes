/** Accessibility panel: audits, display controls, RTL preview, tour, snapshots. */

import type {
  AccessibilityStatus,
  AuditIssueView,
  EmptyStateView,
  TourStateView,
  TourStepView,
} from "./client";
import type {
  AccessibilityAction,
  AccessibilityState,
  PanelTab,
} from "./state";
import {
  canSaveSnapshot,
  directionForLocale,
  issueCountLabel,
  issueSeverityCounts,
  motionDurationLabel,
  motionLabel,
  nextTourOperation,
  preferencePatch,
  sortedIssues,
  statusSummary,
  tourProgress,
} from "./state";

export interface SelectOption {
  value: string;
  label: string;
}

export interface AccessibilityPanelProps {
  state: AccessibilityState;
  dispatch: (action: AccessibilityAction) => void;
  onApply: () => void;
  onAudit: () => void;
  onTour: (operation: string) => void;
  onSaveSnapshot: (name: string) => void;
  onLoadSnapshot: (name: string) => void;
  snapshotName: string;
  onSnapshotNameChange: (name: string) => void;
}

const TABS: readonly { id: PanelTab; label: string }[] = [
  { id: "controls", label: "Display" },
  { id: "audit", label: "Audit" },
  { id: "tour", label: "Tour" },
  { id: "snapshots", label: "Snapshots" },
];

const THEME_OPTIONS: readonly SelectOption[] = [
  { value: "light", label: "Light" },
  { value: "graphite", label: "Graphite" },
  { value: "system", label: "System" },
];

const DENSITY_OPTIONS: readonly SelectOption[] = [
  { value: "compact", label: "Compact" },
  { value: "default", label: "Default" },
  { value: "comfortable", label: "Comfortable" },
];

const MOTION_OPTIONS: readonly SelectOption[] = [
  { value: "full", label: "Full motion" },
  { value: "subtle", label: "Reduced motion" },
  { value: "off", label: "No motion" },
];

function SelectControl({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: readonly SelectOption[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="a11yi-field">
      <label className="a11yi-field__label" htmlFor={id}>
        {label}
      </label>
      <select
        id={id}
        className="a11yi-select v4-focus-ring"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function ToggleControl({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="a11yi-toggle">
      <input
        id={id}
        className="a11yi-toggle__input v4-focus-ring"
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <div className="a11yi-toggle__copy">
        <label className="a11yi-toggle__label" htmlFor={id}>
          {label}
        </label>
        {hint ? <span className="a11yi-toggle__hint">{hint}</span> : null}
      </div>
    </div>
  );
}

function EmptyCard({
  spec,
  onAction,
}: {
  spec: EmptyStateView | undefined;
  onAction: () => void;
}) {
  if (!spec) {
    return <div className="a11yi-empty v4-empty">Nothing to show.</div>;
  }
  return (
    <div className="a11yi-empty v4-empty" role="status">
      <strong className="a11yi-empty__title">{spec.title}</strong>
      <span className="a11yi-empty__body">{spec.body}</span>
      <button className="a11yi-btn v4-btn" type="button" onClick={onAction}>
        {spec.action_label}
      </button>
    </div>
  );
}

function IssueRow({ issue }: { issue: AuditIssueView }) {
  return (
    <li className="a11yi-issue" data-severity={issue.severity}>
      <span className="a11yi-issue__badge v4-chip">{issue.severity}</span>
      <div className="a11yi-issue__copy">
        <code className="a11yi-issue__target">{issue.target}</code>
        <span className="a11yi-issue__detail">{issue.detail}</span>
        <span className="a11yi-issue__suggestion">{issue.suggestion}</span>
      </div>
      <span className="a11yi-issue__rule">{issue.rule_id}</span>
    </li>
  );
}

function ControlGrid({
  props,
  locales,
  directions,
}: {
  props: AccessibilityPanelProps;
  locales: string[];
  directions: Record<string, string>;
}) {
  const { state, dispatch } = props;
  const localeOptions: SelectOption[] = locales.map((locale) => ({
    value: locale,
    label: `${locale} (${directionForLocale(directions, locale)})`,
  }));
  const preview = state.previewDirection;
  return (
    <div className="a11yi-controls" id="control-grid">
      <fieldset className="a11yi-fieldset">
        <legend className="a11yi-legend">Display preferences</legend>
        <div className="a11yi-control-grid">
          <SelectControl
            id="a11yi-theme"
            label="Theme"
            value={state.theme}
            options={THEME_OPTIONS}
            onChange={(theme) =>
              dispatch({
                type: "set-theme",
                theme: theme as AccessibilityState["theme"],
              })
            }
          />
          <SelectControl
            id="a11yi-density"
            label="Density"
            value={state.density}
            options={DENSITY_OPTIONS}
            onChange={(density) =>
              dispatch({
                type: "set-density",
                density: density as AccessibilityState["density"],
              })
            }
          />
          <SelectControl
            id="a11yi-motion"
            label="Motion"
            value={state.motion}
            options={MOTION_OPTIONS}
            onChange={(motion) =>
              dispatch({
                type: "set-motion",
                motion: motion as AccessibilityState["motion"],
              })
            }
          />
          <SelectControl
            id="a11yi-locale"
            label="Language"
            value={state.locale}
            options={localeOptions}
            onChange={(locale) =>
              dispatch({
                type: "set-locale",
                locale,
                direction: directionForLocale(directions, locale),
              })
            }
          />
        </div>
        <div className="a11yi-toggles">
          <ToggleControl
            id="a11yi-reduce-motion"
            label="Reduce motion"
            hint="Forces all animation durations to zero."
            checked={state.reduceMotion}
            onChange={(value) => dispatch({ type: "set-reduce-motion", value })}
          />
          <ToggleControl
            id="a11yi-high-contrast"
            label="High contrast"
            hint="Increases border and text weight."
            checked={state.highContrast}
            onChange={(value) => dispatch({ type: "set-high-contrast", value })}
          />
        </div>
        <div className="a11yi-control-actions">
          <button
            className="a11yi-btn v4-btn v4-btn--primary v4-focus-ring"
            type="button"
            onClick={props.onApply}
            disabled={state.busy}
          >
            Apply preferences
          </button>
          <span className="a11yi-dirty" data-dirty={state.dirty}>
            {state.dirty ? "Unsaved changes" : "Up to date"}
          </span>
        </div>
      </fieldset>
      <RtlPreview
        direction={preview}
        locale={state.locale}
        onToggle={(direction) => dispatch({ type: "set-preview", direction })}
      />
    </div>
  );
}

function RtlPreview({
  direction,
  locale,
  onToggle,
}: {
  direction: "ltr" | "rtl";
  locale: string;
  onToggle: (direction: "ltr" | "rtl") => void;
}) {
  return (
    <section
      className="a11yi-preview v4-panel"
      id="rtl-preview"
      aria-label="RTL preview"
    >
      <header className="a11yi-preview__header">
        <h3 className="a11yi-preview__title">Right-to-left preview</h3>
        <button
          className="a11yi-btn v4-btn v4-focus-ring"
          type="button"
          onClick={() => onToggle(direction === "ltr" ? "rtl" : "ltr")}
        >
          Mirror
        </button>
      </header>
      <div className="a11yi-preview__sample" dir={direction} lang={locale}>
        <p>1. Review the finding</p>
        <p>2. Attach evidence</p>
        <p>3. Publish the report</p>
      </div>
      <footer className="a11yi-preview__footer">
        <span className="v4-chip">{locale}</span>
        <span className="v4-chip">{direction}</span>
      </footer>
    </section>
  );
}

function AuditSection({
  state,
  onAudit,
}: {
  state: AccessibilityState;
  onAudit: () => void;
}) {
  const spec = state.status?.empty_states.issues;
  const counts = issueSeverityCounts(state.issues);
  return (
    <section
      className="a11yi-audit"
      id="audit-issues"
      aria-label="Accessibility audit"
    >
      <header className="a11yi-section__header">
        <h3 className="a11yi-section__title">Audit issues</h3>
        <button
          className="a11yi-btn v4-btn v4-focus-ring"
          type="button"
          onClick={onAudit}
          disabled={state.busy}
        >
          Run audit
        </button>
      </header>
      <div className="a11yi-severities" aria-live="polite">
        <span className="v4-chip">{issueCountLabel(state.issues.length)}</span>
        <span className="v4-chip">{counts.error} errors</span>
        <span className="v4-chip">{counts.warning} warnings</span>
        <span className="v4-chip">{counts.info} notices</span>
      </div>
      {state.issues.length === 0 ? (
        <EmptyCard spec={spec} onAction={onAudit} />
      ) : (
        <ul className="a11yi-issues">
          {sortedIssues(state.issues).map((issue) => (
            <IssueRow key={issue.fingerprint} issue={issue} />
          ))}
        </ul>
      )}
    </section>
  );
}

function TourSection({
  tour,
  step,
  onTour,
}: {
  tour: TourStateView | null;
  step: TourStepView | null;
  onTour: (operation: string) => void;
}) {
  if (!tour || !step) {
    return <EmptyCard spec={undefined} onAction={() => onTour("start")} />;
  }
  return (
    <section className="a11yi-tour v4-panel" aria-label="Onboarding tour">
      <header className="a11yi-tour__header">
        <h3 className="a11yi-tour__title">{step.title}</h3>
        <span className="v4-chip">
          {tour.index + 1} / {tour.total}
        </span>
      </header>
      <p className="a11yi-tour__body">{step.body}</p>
      <div
        className="a11yi-tour__progress"
        role="progressbar"
        aria-valuenow={tourProgress(tour)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <span
          className="a11yi-tour__bar"
          style={{ width: `${tourProgress(tour)}%` }}
        />
      </div>
      <p className="a11yi-tour__hint">Target: {step.target}</p>
      <div className="a11yi-tour__actions">
        <button
          className="a11yi-btn v4-btn v4-focus-ring"
          type="button"
          disabled={!tour.can_go_back}
          onClick={() => onTour("previous")}
        >
          Previous
        </button>
        <button
          className="a11yi-btn v4-btn v4-btn--primary v4-focus-ring"
          type="button"
          disabled={!tour.can_advance}
          onClick={() => onTour(nextTourOperation(tour))}
        >
          Next
        </button>
        <button
          className="a11yi-btn v4-btn v4-focus-ring"
          type="button"
          onClick={() => onTour("skip")}
        >
          Skip
        </button>
        <button
          className="a11yi-btn v4-btn v4-focus-ring"
          type="button"
          onClick={() => onTour("complete")}
        >
          Finish
        </button>
      </div>
    </section>
  );
}

function SnapshotSection({ props }: { props: AccessibilityPanelProps }) {
  const {
    state,
    snapshotName,
    onSnapshotNameChange,
    onSaveSnapshot,
    onLoadSnapshot,
  } = props;
  const canSave = canSaveSnapshot(state, snapshotName);
  return (
    <section className="a11yi-snapshots" aria-label="Preference snapshots">
      <header className="a11yi-section__header">
        <h3 className="a11yi-section__title">Saved snapshots</h3>
        <span className="v4-chip">{state.snapshots.length}</span>
      </header>
      <div className="a11yi-snapshot-form">
        <label className="a11yi-field__label" htmlFor="a11yi-snapshot-name">
          Snapshot name
        </label>
        <input
          id="a11yi-snapshot-name"
          className="a11yi-input v4-focus-ring"
          value={snapshotName}
          onChange={(event) => onSnapshotNameChange(event.target.value)}
          placeholder="e.g. night mode"
        />
        <button
          className="a11yi-btn v4-btn v4-btn--primary v4-focus-ring"
          type="button"
          disabled={!canSave}
          onClick={() => onSaveSnapshot(snapshotName)}
        >
          Save snapshot
        </button>
      </div>
      {state.snapshots.length === 0 ? (
        <EmptyCard
          spec={state.status?.empty_states.snapshots}
          onAction={() => onSaveSnapshot(snapshotName || "default")}
        />
      ) : (
        <ul className="a11yi-snapshot-list">
          {state.snapshots.map((name) => (
            <li key={name} className="a11yi-snapshot-row">
              <span>{name}</span>
              <button
                className="a11yi-btn v4-btn v4-focus-ring"
                type="button"
                onClick={() => onLoadSnapshot(name)}
              >
                Load
              </button>
            </li>
          ))}
        </ul>
      )}
      {state.lastSaved ? (
        <p className="a11yi-saved" role="status">
          Saved {state.lastSaved}
        </p>
      ) : null}
    </section>
  );
}

function MotionSummary({ status }: { status: AccessibilityStatus | null }) {
  if (!status) return null;
  return (
    <div className="a11yi-motion-summary">
      <span className="v4-chip v4-chip--accent">
        {motionLabel(status.preferences.motion)}
      </span>
      <span className="v4-chip">
        normal: {motionDurationLabel(status.motion)}
      </span>
      <span className="v4-chip">events: {status.event_count}</span>
    </div>
  );
}

export function AccessibilityPanel(props: AccessibilityPanelProps) {
  const { state, dispatch } = props;
  const status = state.status;
  const directions = status?.directions ?? {};
  const locales = status?.locales ?? ["en"];
  return (
    <section
      className="a11yi-panel v4-panel"
      aria-label="Accessibility and language"
    >
      <header className="a11yi-panel__header">
        <div>
          <h2 className="a11yi-panel__title">Accessibility &amp; language</h2>
          <p className="a11yi-panel__subtitle">
            {statusSummary(status)} · {preferencePatch(state).locale}
          </p>
          <MotionSummary status={status} />
        </div>
        <span className="a11yi-panel__badge v4-chip v4-chip--accent">v4</span>
      </header>
      <div
        className="a11yi-tabs"
        role="tablist"
        aria-label="Accessibility sections"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className="a11yi-tab v4-focus-ring"
            type="button"
            role="tab"
            id={`a11yi-tab-${tab.id}`}
            aria-selected={state.activeTab === tab.id}
            aria-controls={`a11yi-panel-${tab.id}`}
            onClick={() => dispatch({ type: "set-tab", tab: tab.id })}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div
        className="a11yi-panel__body"
        role="tabpanel"
        id={`a11yi-panel-${state.activeTab}`}
        aria-labelledby={`a11yi-tab-${state.activeTab}`}
      >
        {state.error ? (
          <p className="a11yi-error" role="alert">
            {state.error}
          </p>
        ) : null}
        {state.activeTab === "controls" ? (
          <ControlGrid
            props={props}
            locales={locales}
            directions={directions}
          />
        ) : null}
        {state.activeTab === "audit" ? (
          <AuditSection state={state} onAudit={props.onAudit} />
        ) : null}
        {state.activeTab === "tour" ? (
          <TourSection
            tour={state.tour}
            step={state.tourStep}
            onTour={props.onTour}
          />
        ) : null}
        {state.activeTab === "snapshots" ? (
          <SnapshotSection props={props} />
        ) : null}
      </div>
      <footer className="a11yi-panel__footer" aria-live="polite">
        <span>
          {state.lastAction
            ? `Last action: ${state.lastAction}`
            : "No changes yet"}
        </span>
        <span>{state.busy ? "Working…" : "Ready"}</span>
      </footer>
    </section>
  );
}

export default AccessibilityPanel;
