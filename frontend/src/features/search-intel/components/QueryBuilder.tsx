/** Query builder with autocomplete and inline grammar errors. */

import { useMemo, useState, type KeyboardEvent } from "react";

import type { CompletionV2, QueryIssueV2 } from "../types";

export interface QueryBuilderProps {
  value: string;
  onChange: (value: string) => void;
  issues?: QueryIssueV2[];
  completions?: CompletionV2[];
  onRun?: () => void;
  onSave?: () => void;
  disabled?: boolean;
}

export function QueryBuilder({
  value,
  onChange,
  issues = [],
  completions = [],
  onRun,
  onSave,
  disabled = false,
}: QueryBuilderProps) {
  const [active, setActive] = useState(0);
  const errors = useMemo(
    () => issues.filter((issue) => issue.severity === "error"),
    [issues],
  );
  const open = completions.length > 0 && value.length > 0;

  const insert = (completion: CompletionV2) => {
    const before = value.slice(0, completion.start);
    const after = value.slice(completion.end);
    onChange(`${before}${completion.insert_text}${after}`.trimEnd());
    setActive(0);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (open && event.key === "ArrowDown") {
      event.preventDefault();
      setActive((current) => (current + 1) % completions.length);
      return;
    }
    if (open && event.key === "ArrowUp") {
      event.preventDefault();
      setActive(
        (current) => (current - 1 + completions.length) % completions.length,
      );
      return;
    }
    if (open && event.key === "Tab" && completions[active]) {
      event.preventDefault();
      insert(completions[active]);
      return;
    }
    if (open && event.key === "Enter" && completions[active]) {
      event.preventDefault();
      insert(completions[active]);
      return;
    }
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      onRun?.();
    }
    if (event.key === "Escape") setActive(0);
  };

  return (
    <div className="si-query" data-testid="search-query-builder">
      <div className="si-query__field">
        <textarea
          aria-label="Search query"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls="si-query-completions"
          autoComplete="off"
          className="si-query__input v3-focusable"
          data-testid="search-query-input"
          disabled={disabled}
          onChange={(event) => {
            onChange(event.target.value);
            setActive(0);
          }}
          onKeyDown={handleKeyDown}
          placeholder="kind:finding tag:web has:link(evidences)"
          rows={2}
          spellCheck={false}
          value={value}
        />
        <div className="si-query__actions">
          <button
            className="si-button v3-focusable"
            data-testid="search-query-run"
            disabled={disabled}
            onClick={onRun}
            type="button"
          >
            Search
          </button>
          <button
            className="si-button si-button--ghost v3-focusable"
            disabled={disabled || !value.trim()}
            onClick={onSave}
            type="button"
          >
            Save
          </button>
        </div>
      </div>
      {open && (
        <ul
          className="si-query__completions"
          data-testid="search-query-completions"
          id="si-query-completions"
          role="listbox"
        >
          {completions.map((completion, index) => (
            <li
              aria-selected={index === active}
              className="si-query__completion"
              data-kind={completion.kind}
              data-testid="search-query-completion"
              key={`${completion.kind}-${completion.label}`}
              onClick={() => insert(completion)}
              onMouseEnter={() => setActive(index)}
              role="option"
            >
              <span className="si-query__completion-kind">
                {completion.kind}
              </span>
              <span className="si-query__completion-label">
                {completion.label}
              </span>
            </li>
          ))}
        </ul>
      )}
      {errors.length > 0 && (
        <ul
          className="si-query__errors"
          data-testid="search-query-errors"
          role="alert"
        >
          {errors.map((error, index) => (
            <li key={`${error.code}-${error.start}-${index}`}>
              <code>{error.code}</code> {error.message}
              {error.hint && (
                <span className="si-query__hint"> — {error.hint}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function queryBuilderSummary(value: string, issueCount: number): string {
  return `${value.trim() || "No query"} · ${issueCount} issue${issueCount === 1 ? "" : "s"}`;
}
