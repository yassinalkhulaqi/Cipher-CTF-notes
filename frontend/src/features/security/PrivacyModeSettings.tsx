import type { ConsentSummary, PrivacyMode } from "./types";
import { consentProgress, enabledControls, formatPercent } from "./helpers";

interface Props {
  modes: PrivacyMode[];
  selectedLevel: string;
  currentMode: PrivacyMode | null;
  consent: ConsentSummary | null;
  onSelectLevel: (level: string) => void;
  onToggleControl: (key: string, enabled: boolean) => void;
  onToggleConsent: (key: string, granted: boolean) => void;
}

export function PrivacyModeSettings({
  modes,
  selectedLevel,
  currentMode,
  consent,
  onSelectLevel,
  onToggleControl,
  onToggleConsent,
}: Props) {
  const active =
    currentMode || modes.find((mode) => mode.level === selectedLevel) || null;
  const progress = consentProgress(consent);

  return (
    <section
      className="security-panel privacy-settings"
      aria-label="Privacy mode settings"
    >
      <header className="security-panel__header">
        <div>
          <h2>Privacy Mode</h2>
          <p className="security-panel__subtitle">
            {active?.description ||
              "Choose a privacy level and adjust controls."}
          </p>
        </div>
        <div className="stat-chip">
          <span>Consent granted</span>
          <strong>{formatPercent(progress, 0)}</strong>
        </div>
      </header>

      <div
        className="privacy-levels"
        role="radiogroup"
        aria-label="Privacy levels"
      >
        {modes.map((mode) => {
          const selected = mode.level === selectedLevel;
          return (
            <label
              key={mode.level}
              className={`privacy-level ${selected ? "is-selected" : ""}`}
            >
              <input
                type="radio"
                name="privacy-level"
                value={mode.level}
                checked={selected}
                onChange={() => onSelectLevel(mode.level)}
              />
              <span className="privacy-level__body">
                <strong>{mode.label || mode.level}</strong>
                <small>{mode.description}</small>
              </span>
            </label>
          );
        })}
      </div>

      <div className="security-columns">
        <div className="security-column">
          <h3>Controls</h3>
          {!active ? (
            <p className="empty-state">
              Select a privacy level to view controls.
            </p>
          ) : (
            <ul className="control-list">
              {active.controls.map((control) => (
                <li key={control.key} className="control-item">
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={control.enabled}
                      onChange={(event) =>
                        onToggleControl(control.key, event.target.checked)
                      }
                    />
                    <span>
                      <strong>{control.label}</strong>
                      <small>{control.category}</small>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          {active ? (
            <p className="muted">
              Enabled controls: {enabledControls(active.controls).length} /{" "}
              {active.controls.length}
            </p>
          ) : null}
        </div>

        <div className="security-column">
          <h3>Consent flags</h3>
          {!consent?.items?.length ? (
            <p className="empty-state">Consent information unavailable.</p>
          ) : (
            <ul className="consent-list">
              {consent.items.map((item) => (
                <li key={item.flag.key} className="consent-item">
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={item.granted}
                      onChange={(event) =>
                        onToggleConsent(item.flag.key, event.target.checked)
                      }
                    />
                    <span>
                      <strong>{item.flag.label}</strong>
                      <small>{item.flag.description}</small>
                    </span>
                  </label>
                  {item.flag.required_for.length ? (
                    <p className="consent-item__meta">
                      Required for: {item.flag.required_for.join(", ")}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
