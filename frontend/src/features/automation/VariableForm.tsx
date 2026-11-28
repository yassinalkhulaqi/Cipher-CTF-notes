/** Typed variable form with inline validation messages. */

import { useMemo } from "react";
import type { VariableDef } from "./types";
import { validateVariableValues, variableIssuesByKey } from "./variables";

export interface VariableFormProps {
  definitions: VariableDef[];
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
}

function parseInput(kind: VariableDef["kind"], raw: string): unknown {
  if (kind === "number") return raw === "" ? "" : Number(raw);
  if (kind === "list")
    return raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  return raw;
}

export function VariableForm({
  definitions,
  values,
  onChange,
}: VariableFormProps) {
  const resolution = useMemo(
    () => validateVariableValues(definitions, values),
    [definitions, values],
  );
  const problems = useMemo(
    () => variableIssuesByKey(resolution.issues),
    [resolution.issues],
  );

  return (
    <form
      className="automation-variables"
      data-automation="variable-form"
      onSubmit={(event) => event.preventDefault()}
    >
      {definitions.length === 0 && (
        <p className="automation-variables__empty">
          This playbook declares no variables.
        </p>
      )}
      {definitions.map((definition) => {
        const problem = problems[definition.key];
        const value = values[definition.key] ?? "";
        const inputId = `automation-var-${definition.key}`;
        return (
          <div
            className="automation-variables__field"
            key={definition.key}
            data-automation="variable-field"
          >
            <label htmlFor={inputId}>
              {definition.label || definition.key}
              {definition.required ? " *" : ""}
            </label>
            {definition.kind === "boolean" ? (
              <input
                id={inputId}
                type="checkbox"
                data-automation="variable-input"
                data-key={definition.key}
                aria-invalid={Boolean(problem)}
                checked={Boolean(value)}
                onChange={(event) =>
                  onChange(definition.key, event.target.checked)
                }
              />
            ) : definition.kind === "choice" ? (
              <select
                id={inputId}
                data-automation="variable-input"
                data-key={definition.key}
                aria-invalid={Boolean(problem)}
                value={String(value)}
                onChange={(event) =>
                  onChange(definition.key, event.target.value)
                }
              >
                {(definition.choices ?? []).map((choice) => (
                  <option key={choice} value={choice}>
                    {choice}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={inputId}
                type={definition.secret ? "password" : "text"}
                data-automation="variable-input"
                data-key={definition.key}
                aria-invalid={Boolean(problem)}
                aria-describedby={problem ? `${inputId}-error` : undefined}
                value={Array.isArray(value) ? value.join(", ") : String(value)}
                placeholder={definition.description || definition.kind}
                onChange={(event) =>
                  onChange(
                    definition.key,
                    parseInput(definition.kind, event.target.value),
                  )
                }
              />
            )}
            {problem && (
              <span
                className="automation-variables__error"
                id={`${inputId}-error`}
                role="alert"
                data-code={problem.code}
              >
                {problem.message}
              </span>
            )}
          </div>
        );
      })}
      <p
        className="automation-variables__status"
        data-automation="variable-status"
        data-ok={resolution.ok}
      >
        {resolution.ok
          ? "All variables valid"
          : `${resolution.issues.length} issue(s)`}
      </p>
    </form>
  );
}
