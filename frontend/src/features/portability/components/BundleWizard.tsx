import type { BundlePlan, WizardStep } from "../types";
import {
  passphraseScore,
  strengthLabel,
  strengthTone,
  validatePlan,
  wizardPercent,
} from "../pure";

interface Props {
  plan: BundlePlan;
  wizard: WizardStep[];
  busy: boolean;
  onChange: (value: Partial<BundlePlan>) => void;
  onNext: () => void;
}

const FAMILIES = [
  "note",
  "finding",
  "evidence",
  "report",
  "target",
  "playbook",
];

export function BundleWizard({ plan, wizard, busy, onChange, onNext }: Props) {
  const problems = validatePlan(plan);
  const score = passphraseScore(plan.passphrase);
  return (
    <section
      className="portability-card portability-wizard"
      aria-label="Bundle wizard"
    >
      <header className="portability-card__header">
        <div>
          <h3>Create encrypted bundle</h3>
          <p className="portability-card__subtitle">
            Choose what moves, protect it with a passphrase, then inspect before
            writing.
          </p>
        </div>
        <span className="portability-badge" data-tone="info">
          {wizardPercent(wizard)}% prepared
        </span>
      </header>

      <ol className="portability-steps" aria-label="Bundle wizard steps">
        {wizard.map((step, index) => (
          <li
            key={step.id}
            className="portability-step"
            data-status={step.status}
          >
            <span className="portability-step__index" aria-hidden="true">
              {index + 1}
            </span>
            <span className="portability-step__text">
              <strong>{step.label}</strong>
              <small>{step.description}</small>
            </span>
          </li>
        ))}
      </ol>

      <div className="portability-form">
        <label className="portability-field">
          <span>Bundle label</span>
          <input
            type="text"
            value={plan.label}
            placeholder="Incident handoff — March"
            onChange={(event) => onChange({ label: event.target.value })}
          />
        </label>
        <label className="portability-field">
          <span>Authoring device</span>
          <input
            type="text"
            value={plan.deviceId}
            onChange={(event) => onChange({ deviceId: event.target.value })}
          />
        </label>
        <fieldset className="portability-fieldset">
          <legend>Entity families</legend>
          <div className="portability-chips">
            {FAMILIES.map((family) => {
              const selected = plan.scope.includes(family);
              return (
                <button
                  key={family}
                  type="button"
                  className="portability-chip"
                  data-selected={selected}
                  aria-pressed={selected}
                  onClick={() =>
                    onChange({
                      scope: selected
                        ? plan.scope.filter((item) => item !== family)
                        : [...plan.scope, family],
                    })
                  }
                >
                  {family}
                </button>
              );
            })}
          </div>
        </fieldset>
        <label className="portability-field">
          <span>Passphrase</span>
          <input
            type="password"
            value={plan.passphrase}
            autoComplete="new-password"
            onChange={(event) => onChange({ passphrase: event.target.value })}
          />
        </label>
        <div className="portability-strength" aria-live="polite">
          <span>Passphrase strength</span>
          <div className="portability-strength__track">
            <div
              className="portability-strength__fill"
              data-tone={strengthTone(score)}
              style={{
                width: `${Math.min(100, plan.passphrase.length * 6)}%`,
              }}
            />
          </div>
          <strong>{strengthLabel(score)}</strong>
        </div>
        <div className="portability-toggles">
          <label>
            <input
              type="checkbox"
              checked={plan.includeDeleted}
              onChange={(event) =>
                onChange({ includeDeleted: event.target.checked })
              }
            />
            Include deleted records
          </label>
          <label>
            <input
              type="checkbox"
              checked={plan.includeLinks}
              onChange={(event) =>
                onChange({ includeLinks: event.target.checked })
              }
            />
            Include typed links
          </label>
          <label>
            <input
              type="checkbox"
              checked={plan.dryRun}
              onChange={(event) => onChange({ dryRun: event.target.checked })}
            />
            Require dry run
          </label>
        </div>
      </div>

      {problems.length > 0 && (
        <ul className="portability-problems" aria-label="Plan validation">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
      <footer className="portability-card__footer">
        <button
          type="button"
          className="portability-button"
          onClick={onNext}
          disabled={busy || problems.length > 0}
        >
          Continue to preview
        </button>
      </footer>
    </section>
  );
}
