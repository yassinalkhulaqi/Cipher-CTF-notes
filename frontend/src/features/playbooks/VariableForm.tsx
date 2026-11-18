import { useState } from "react";
import { Banner } from "../../ui/Banner";
import { Button } from "../../ui/Button";
import { Field } from "../../ui/Field";
import {
  coerceVariableInput,
  formatValue,
  validateVariableDraft,
  variableKindLabel,
} from "./helpers";
import type { VariableDefinition, VariableKind, PlaybookValues } from "./types";

export interface VariableFormProps {
  definitions: VariableDefinition[];
  values: PlaybookValues;
  inputs: Record<string, string>;
  onChange: (definitions: VariableDefinition[]) => void;
  onInputChange: (key: string, value: string) => void;
  onValuesChange: (values: PlaybookValues) => void;
  readOnly?: boolean;
}

const KINDS: VariableKind[] = [
  "text",
  "number",
  "boolean",
  "choice",
  "secret",
  "list",
];

function blankVariable(index: number): VariableDefinition {
  return {
    key: `variable_${index + 1}`,
    label: `Variable ${index + 1}`,
    description: "",
    kind: "text",
    default: "",
    choices: [],
    required: false,
    secret: false,
    pattern: "",
    minimum: null,
    maximum: null,
  };
}

export function VariableForm({
  definitions,
  values,
  inputs,
  onChange,
  onInputChange,
  onValuesChange,
  readOnly = false,
}: VariableFormProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [choiceDraft, setChoiceDraft] = useState<Record<string, string>>({});

  const patch = (key: string, changes: Partial<VariableDefinition>) => {
    onChange(
      definitions.map((definition) =>
        definition.key === key ? { ...definition, ...changes } : definition,
      ),
    );
  };

  const addVariable = () => {
    onChange([...definitions, blankVariable(definitions.length)]);
  };

  const removeVariable = (key: string) => {
    onChange(definitions.filter((definition) => definition.key !== key));
    const next = { ...values };
    delete next[key];
    onValuesChange(next);
  };

  const move = (index: number, offset: number) => {
    const target = index + offset;
    if (target < 0 || target >= definitions.length) return;
    const next = [...definitions];
    const [item] = next.splice(index, 1);
    if (!item) return;
    next.splice(target, 0, item);
    onChange(next);
  };

  const applyInput = (definition: VariableDefinition, text: string) => {
    onInputChange(definition.key, text);
    const value = coerceVariableInput(definition, text);
    const next = { ...values };
    if (value === null) delete next[definition.key];
    else next[definition.key] = value;
    onValuesChange(next);
  };

  const addChoice = (definition: VariableDefinition) => {
    const value = (choiceDraft[definition.key] ?? "").trim();
    if (!value || definition.choices.includes(value)) return;
    patch(definition.key, { choices: [...definition.choices, value] });
    setChoiceDraft({ ...choiceDraft, [definition.key]: "" });
  };

  if (definitions.length === 0) {
    return (
      <div className="pb-variables__empty">
        <p>This playbook declares no variables.</p>
        {readOnly ? null : (
          <Button size="sm" variant="secondary" onClick={addVariable}>
            Add variable
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="pb-variables">
      {definitions.map((definition, index) => {
        const issues = validateVariableDraft(definition);
        const isOpen = expanded === definition.key;
        const text =
          inputs[definition.key] ??
          formatValue(values[definition.key] ?? definition.default);
        return (
          <article className="pb-variable" key={definition.key}>
            <header className="pb-variable__header">
              <button
                type="button"
                className="pb-variable__toggle"
                aria-expanded={isOpen}
                onClick={() => setExpanded(isOpen ? null : definition.key)}
              >
                <code>{definition.key}</code>
                <span className="pb-variable__meta">
                  {variableKindLabel(definition.kind)}
                  {definition.required ? " · required" : ""}
                  {definition.secret ? " · secret" : ""}
                </span>
              </button>
              <div className="pb-variable__actions">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => move(index, -1)}
                  disabled={readOnly}
                >
                  Up
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => move(index, 1)}
                  disabled={readOnly}
                >
                  Down
                </Button>
                {readOnly ? null : (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => removeVariable(definition.key)}
                  >
                    Remove
                  </Button>
                )}
              </div>
            </header>

            {isOpen ? (
              <div className="pb-variable__body">
                {issues.length > 0 ? (
                  <Banner tone="warning" title="Variable issues">
                    {issues.map((issue) => issue.message).join(" · ")}
                  </Banner>
                ) : null}

                <div className="pb-grid pb-grid--two">
                  <Field
                    label="Key"
                    value={definition.key}
                    disabled={readOnly}
                    onChange={(event) =>
                      patch(definition.key, { key: event.target.value.trim() })
                    }
                  />
                  <Field
                    label="Label"
                    value={definition.label}
                    disabled={readOnly}
                    onChange={(event) =>
                      patch(definition.key, { label: event.target.value })
                    }
                  />
                </div>

                <label className="pb-field">
                  <span>Description</span>
                  <textarea
                    rows={2}
                    value={definition.description ?? ""}
                    disabled={readOnly}
                    onChange={(event) =>
                      patch(definition.key, { description: event.target.value })
                    }
                  />
                </label>

                <div className="pb-grid pb-grid--three">
                  <label className="pb-field">
                    <span>Kind</span>
                    <select
                      value={definition.kind}
                      disabled={readOnly}
                      onChange={(event) =>
                        patch(definition.key, {
                          kind: event.target.value as VariableKind,
                        })
                      }
                    >
                      {KINDS.map((kind) => (
                        <option key={kind} value={kind}>
                          {variableKindLabel(kind)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Field
                    label="Pattern"
                    value={definition.pattern}
                    disabled={readOnly}
                    onChange={(event) =>
                      patch(definition.key, { pattern: event.target.value })
                    }
                  />
                  <Field
                    label="Minimum"
                    type="number"
                    value={
                      definition.minimum === null
                        ? ""
                        : String(definition.minimum)
                    }
                    disabled={readOnly}
                    onChange={(event) =>
                      patch(definition.key, {
                        minimum:
                          event.target.value === ""
                            ? null
                            : Number(event.target.value),
                      })
                    }
                  />
                  <Field
                    label="Maximum"
                    type="number"
                    value={
                      definition.maximum === null
                        ? ""
                        : String(definition.maximum)
                    }
                    disabled={readOnly}
                    onChange={(event) =>
                      patch(definition.key, {
                        maximum:
                          event.target.value === ""
                            ? null
                            : Number(event.target.value),
                      })
                    }
                  />
                </div>

                {definition.kind === "choice" ? (
                  <div className="pb-fieldset">
                    <legend>Choices</legend>
                    <div className="pb-chip-row">
                      {definition.choices.map((choice) => (
                        <span className="pb-chip pb-chip--muted" key={choice}>
                          {choice}
                        </span>
                      ))}
                    </div>
                    {readOnly ? null : (
                      <div className="pb-inline-form">
                        <Field
                          label="New choice"
                          value={choiceDraft[definition.key] ?? ""}
                          onChange={(event) =>
                            setChoiceDraft({
                              ...choiceDraft,
                              [definition.key]: event.target.value,
                            })
                          }
                        />
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => addChoice(definition)}
                        >
                          Add
                        </Button>
                      </div>
                    )}
                  </div>
                ) : null}

                <Field
                  label="Value"
                  value={text}
                  type={
                    definition.secret || definition.kind === "secret"
                      ? "password"
                      : "text"
                  }
                  placeholder={formatValue(definition.default)}
                  onChange={(event) =>
                    applyInput(definition, event.target.value)
                  }
                />

                {definition.pattern ? (
                  <p className="pb-variable__pattern">
                    Pattern: <code>{definition.pattern}</code>
                  </p>
                ) : null}
              </div>
            ) : null}
          </article>
        );
      })}

      {readOnly ? null : (
        <Button size="sm" variant="secondary" onClick={addVariable}>
          Add variable
        </Button>
      )}
    </div>
  );
}
