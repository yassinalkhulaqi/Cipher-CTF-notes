/** Inline argument form for the currently selected command. */

import { useState } from "react";

import { validateArgument } from "./parse";
import type { CommandSpec } from "./types";

export interface ArgumentFormProps {
  command: CommandSpec;
  values: Record<string, string>;
  onChange: (name: string, value: string) => void;
  onSubmit: (values: Record<string, string>) => void;
  onCancel: () => void;
}

export function ArgumentForm({
  command,
  values,
  onChange,
  onSubmit,
  onCancel,
}: ArgumentFormProps) {
  const [error, setError] = useState("");

  const submit = () => {
    try {
      const validated: Record<string, string> = {};
      for (const argument of command.arguments) {
        const value = values[argument.name] ?? argument.default;
        validated[argument.name] = validateArgument(value, argument);
      }
      setError("");
      onSubmit(validated);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Invalid argument");
    }
  };

  return (
    <form
      className="v3c-arguments"
      data-testid="command-arguments"
      data-command={command.id}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="v3c-arguments__title">{command.title}</div>
      {command.description && (
        <p className="v3c-arguments__description">{command.description}</p>
      )}
      {command.arguments.map((argument) => (
        <label className="v3c-arguments__field" key={argument.name}>
          <span>
            {argument.name}
            {argument.required && <span aria-hidden="true"> *</span>}
          </span>
          {argument.choices.length ? (
            <select
              data-testid={`arg-${argument.name}`}
              value={values[argument.name] ?? argument.default}
              onChange={(event) => onChange(argument.name, event.target.value)}
            >
              {argument.choices.map((choice) => (
                <option value={choice} key={choice}>
                  {choice}
                </option>
              ))}
            </select>
          ) : (
            <input
              data-testid={`arg-${argument.name}`}
              type="text"
              maxLength={argument.max_length}
              placeholder={argument.help || argument.name}
              value={values[argument.name] ?? argument.default}
              onChange={(event) => onChange(argument.name, event.target.value)}
            />
          )}
        </label>
      ))}
      {error && (
        <p className="v3c-arguments__error" role="alert">
          {error}
        </p>
      )}
      <div className="v3c-arguments__actions">
        <button type="submit" className="v3c-button v3c-button--primary">
          Run command
        </button>
        <button type="button" className="v3c-button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
