import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import type { FormEvent, ReactElement } from "react";

import {
  FIELD_LABELS,
  OPERATOR_LABELS,
  QUERY_FIELDS,
  QueryLanguageClient,
  V4ApiError,
} from "./client";
import type {
  FacetView,
  QueryField,
  QueryOperator,
  SavedQueryView,
  SearchResponse,
} from "./client";
import {
  appendClause,
  buildFacetSelections,
  highlightExpression,
  initialQueryState,
  queryReducer,
  resultLabel,
  selectedFacetCount,
  toggleFacetValues,
} from "./state";

import "./query-language.css";

export interface QueryBarProps {
  client: QueryLanguageClient;
  initialSaved?: SavedQueryView[];
  onSearch?: (response: SearchResponse) => void;
}

function describeError(error: unknown): string {
  if (error instanceof V4ApiError) return `${error.code}: ${error.message}`;
  if (error instanceof Error) return error.message;
  return "Unexpected query error";
}

const SUGGESTIONS: Array<{
  field: QueryField;
  operator: QueryOperator;
  value: string;
}> = [
  { field: "title", operator: "contains", value: "sql" },
  { field: "tag", operator: "in", value: "web,ctf" },
  { field: "status", operator: "=", value: "open" },
  { field: "author", operator: "starts_with", value: "ada" },
];

export function QueryBar({
  client,
  initialSaved = [],
  onSearch,
}: QueryBarProps): ReactElement {
  const [state, dispatch] = useReducer(
    queryReducer,
    initialSaved,
    initialQueryState,
  );
  const [clusterField, setClusterField] = useState<QueryField>("status");

  useEffect(() => {
    let active = true;
    client
      .listSaved()
      .then((envelope) => {
        if (active) dispatch({ type: "saved", queries: envelope.data });
      })
      .catch((error: unknown) => {
        if (active) dispatch({ type: "error", message: describeError(error) });
      });
    return () => {
      active = false;
    };
  }, [client]);

  const runSearch = useCallback(
    async (
      expression: string,
      page: number,
      selections: Record<string, string[]>,
    ) => {
      dispatch({ type: "loading", value: true });
      try {
        const envelope = await client.search({
          expression,
          page,
          pageSize: 10,
          facets: QUERY_FIELDS,
          clusterField,
          selectedFacets: selections,
        });
        dispatch({ type: "results", response: envelope.data });
        onSearch?.(envelope.data);
      } catch (error: unknown) {
        dispatch({ type: "error", message: describeError(error) });
      }
    },
    [client, clusterField, onSearch],
  );

  const highlightSegments = useMemo(
    () => highlightExpression(state.expression),
    [state.expression],
  );

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    dispatch({ type: "submit" });
    void runSearch(state.expression.trim(), 1, buildFacetSelections(state));
  };

  const handleFacetToggle = (field: QueryField, value: string) => {
    const next = toggleFacetValues(state.selectedFacets, field, value);
    dispatch({ type: "toggle-facet", field, value });
    void runSearch(state.submittedExpression, 1, next);
  };

  const handleSave = async () => {
    const name = state.saveName.trim();
    if (!name) {
      dispatch({ type: "error", message: "Enter a name before saving" });
      return;
    }
    try {
      const saved = await client.save(
        name,
        state.submittedExpression || state.expression,
      );
      const updated = [
        saved,
        ...state.savedQueries.filter((item) => item.id !== saved.id),
      ];
      dispatch({ type: "saved", queries: updated });
      dispatch({ type: "save-name", value: "" });
    } catch (error: unknown) {
      dispatch({ type: "error", message: describeError(error) });
    }
  };

  const handleChip = (saved: SavedQueryView) => {
    dispatch({ type: "apply-saved", query: saved });
    void runSearch(saved.expression, 1, {});
  };

  const handleSuggestion = (suggestion: {
    field: QueryField;
    operator: QueryOperator;
    value: string;
  }) => {
    dispatch({
      type: "expression",
      value: appendClause(
        state.expression,
        suggestion.field,
        suggestion.operator,
        suggestion.value,
      ),
    });
  };

  const pageCount =
    state.pageSize > 0 ? Math.ceil(state.total / state.pageSize) : 0;

  return (
    <section className="ql" aria-label="Structured query">
      <header className="ql__header">
        <div>
          <h2 className="ql__title">Structured search</h2>
          <p className="ql__subtitle">
            Field clauses, facets, and saved queries
          </p>
        </div>
        <span className="ql__version v4-chip v4-chip--accent">v4</span>
      </header>

      <form className="ql__form v4-panel" onSubmit={handleSubmit}>
        <label className="ql__label" htmlFor="ql-expression">
          Query expression
        </label>
        <input
          id="ql-expression"
          className="ql__input v4-focus-ring"
          value={state.expression}
          onChange={(event) =>
            dispatch({ type: "expression", value: event.target.value })
          }
          placeholder="title:contains(sql) AND tag:in(web,ctf)"
          aria-describedby="ql-hints"
          spellCheck={false}
        />
        <div className="ql__preview" aria-live="polite">
          {highlightSegments.length === 0 ? (
            <span className="ql__preview-empty">Try field:operator(value)</span>
          ) : (
            highlightSegments.map((segment, index) => (
              <span
                className={`ql__tok ql__tok--${segment.kind}`}
                key={`${segment.kind}-${index}`}
              >
                {segment.text}
              </span>
            ))
          )}
        </div>
        <div className="ql__hints" id="ql-hints">
          {SUGGESTIONS.map((suggestion) => (
            <button
              className="ql__hint v4-chip"
              key={`${suggestion.field}-${suggestion.value}`}
              onClick={() => handleSuggestion(suggestion)}
              type="button"
            >
              + {FIELD_LABELS[suggestion.field]}{" "}
              {OPERATOR_LABELS[suggestion.operator]}
            </button>
          ))}
        </div>
        <div className="ql__actions">
          <button
            className="v4-btn v4-btn--primary"
            disabled={state.loading}
            type="submit"
          >
            {state.loading ? "Searching…" : "Run query"}
          </button>
          <select
            aria-label="Cluster results by"
            className="ql__select"
            onChange={(event) =>
              setClusterField(event.target.value as QueryField)
            }
            value={clusterField}
          >
            {QUERY_FIELDS.map((field) => (
              <option key={field} value={field}>
                Cluster by {FIELD_LABELS[field]}
              </option>
            ))}
          </select>
        </div>
      </form>

      {state.error && (
        <div className="ql__error" role="alert">
          {state.error}
        </div>
      )}

      <div className="ql__layout">
        <aside className="ql__facets v4-panel" aria-label="Facet filters">
          <div className="ql__section-head">
            <h3>Facets</h3>
            <button
              className="ql__link"
              onClick={() => dispatch({ type: "clear-facets" })}
              type="button"
            >
              Clear ({selectedFacetCount(state)})
            </button>
          </div>
          {state.facets.length === 0 ? (
            <p className="ql__muted">Run a query to see facet counts.</p>
          ) : (
            state.facets.map((facet: FacetView) => (
              <div className="ql__facet" key={facet.field}>
                <h4>{facet.label}</h4>
                {facet.values.length === 0 ? (
                  <p className="ql__muted">No values</p>
                ) : (
                  facet.values.map((value) => (
                    <label className="ql__facet-row" key={value.value}>
                      <input
                        checked={value.selected}
                        onChange={() =>
                          handleFacetToggle(facet.field, value.value)
                        }
                        type="checkbox"
                      />
                      <span>{value.value}</span>
                      <span className="ql__count">{value.count}</span>
                    </label>
                  ))
                )}
              </div>
            ))
          )}
        </aside>

        <div className="ql__results">
          <div className="ql__status">
            <strong>{state.total}</strong> results
            {state.nextCursor && <span> · page {state.page}</span>}
          </div>
          {state.warnings.map((warning) => (
            <p className="ql__warning" key={warning}>
              {warning}
            </p>
          ))}
          {state.results.length === 0 ? (
            <div className="v4-empty">No results match this query.</div>
          ) : (
            state.results.map((result, index) => (
              <article
                className="ql__result v4-panel"
                key={String(result.id ?? index)}
              >
                <h4 className="ql__result-title">{resultLabel(result)}</h4>
                <div className="ql__fields">
                  {Object.entries(result)
                    .filter(([key]) => key !== "title")
                    .slice(0, 5)
                    .map(([key, value]) => (
                      <span className="ql__field" key={key}>
                        <b>{key}</b> {String(value)}
                      </span>
                    ))}
                </div>
              </article>
            ))
          )}
          <nav className="ql__pager" aria-label="Result pages">
            <button
              className="v4-btn"
              disabled={state.page <= 1 || state.loading}
              onClick={() => {
                dispatch({ type: "page", value: state.page - 1 });
                void runSearch(
                  state.submittedExpression,
                  state.page - 1,
                  buildFacetSelections(state),
                );
              }}
              type="button"
            >
              Previous
            </button>
            <span className="ql__muted">
              {state.page} / {Math.max(1, pageCount)}
            </span>
            <button
              className="v4-btn"
              disabled={!state.nextCursor || state.loading}
              onClick={() => {
                dispatch({ type: "page", value: state.page + 1 });
                void runSearch(
                  state.submittedExpression,
                  state.page + 1,
                  buildFacetSelections(state),
                );
              }}
              type="button"
            >
              Next
            </button>
          </nav>
        </div>

        <aside className="ql__clusters" aria-label="Result clusters">
          <div className="ql__section-head">
            <h3>Clusters</h3>
          </div>
          {state.clusters.length === 0 ? (
            <p className="ql__muted">No clusters for this query.</p>
          ) : (
            state.clusters.map((cluster) => (
              <button
                className="ql__cluster v4-panel"
                key={cluster.key}
                onClick={() => {
                  dispatch({
                    type: "expression",
                    value: appendClause(
                      state.expression,
                      clusterField,
                      "=",
                      cluster.key,
                    ),
                  });
                }}
                type="button"
              >
                <span className="ql__cluster-key">{cluster.key}</span>
                <span className="ql__cluster-count">{cluster.count}</span>
                <span className="ql__cluster-samples">
                  {cluster.sample_ids.slice(0, 3).join(", ") || "no samples"}
                </span>
              </button>
            ))
          )}
        </aside>
      </div>

      <footer className="ql__saved v4-panel">
        <div className="ql__section-head">
          <h3>Saved queries</h3>
          <span className="ql__muted">{state.savedQueries.length} saved</span>
        </div>
        <div className="ql__chips">
          {state.savedQueries.length === 0 ? (
            <span className="ql__muted">Nothing saved yet.</span>
          ) : (
            state.savedQueries.map((saved) => (
              <button
                className={`ql__chip v4-chip ${state.activeChip === saved.id ? "v4-chip--accent" : ""}`}
                key={saved.id}
                onClick={() => handleChip(saved)}
                title={saved.expression}
                type="button"
              >
                {saved.name}
              </button>
            ))
          )}
        </div>
        <div className="ql__save-row">
          <input
            aria-label="Saved query name"
            className="ql__save-input v4-focus-ring"
            onChange={(event) =>
              dispatch({ type: "save-name", value: event.target.value })
            }
            placeholder="Name this query"
            value={state.saveName}
          />
          <button
            className="v4-btn"
            onClick={() => void handleSave()}
            type="button"
          >
            Save current query
          </button>
        </div>
      </footer>
    </section>
  );
}

export default QueryBar;
