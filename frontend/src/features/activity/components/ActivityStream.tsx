/** Activity stream presentation with density modes and date groups. */

import type { Dispatch } from "react";

import { densityLabel, formatCount, severitySummary, summarizeFacets } from "../format";
import { DENSITY_OPTIONS } from "../format";
import type { FilterValidation, JumpTarget } from "../types";
import type { ActivityAction, ActivityState } from "../state";
import { DateGroupView } from "./DateGroupView";
import { FilterChips } from "./FilterChips";

export interface ActivityStreamProps {
  state: ActivityState;
  dispatch: Dispatch<ActivityAction>;
  validation: FilterValidation | null;
  onJump: (target: JumpTarget) => void;
}

export function ActivityStream({ state, dispatch, validation, onJump }: ActivityStreamProps) {
  const since = state.since;
  return (
    <div className="activity-stream">
      <div className="activity-stream__toolbar">
        <label className="activity-stream__search">
          <span>Search</span>
          <input
            type="search"
            value={state.query}
            placeholder="kind:finding.created actor:alice"
            onChange={(event) => dispatch({ type: "query", value: event.target.value })}
          />
        </label>
        <div className="activity-stream__densities" role="group" aria-label="Density">
          {DENSITY_OPTIONS.map((density) => (
            <button
              key={density}
              type="button"
              data-active={state.density === density ? "true" : "false"}
              onClick={() => dispatch({ type: "density", value: density })}
            >
              {densityLabel(density)}
            </button>
          ))}
        </div>
      </div>

      {since && since.count > 0 && (
        <div className="activity-stream__since" role="status">
          {formatCount(since.count)} new event{since.count === 1 ? "" : "s"} since your last visit
        </div>
      )}

      <FilterChips
        chips={state.chips}
        facets={state.stream.facets}
        validation={validation}
        onChange={(chips) => dispatch({ type: "chips", value: chips })}
        onClear={() => dispatch({ type: "clear-chips" })}
      />

      <p className="activity-stream__summary">
        {formatCount(state.stream.total)} events · {summarizeFacets(state.stream.facets)} ·{" "}
        {severitySummary(state.stream.facets)}
      </p>

      {state.stream.warnings.map((warning) => (
        <p key={warning} className="activity-stream__warning">
          {warning}
        </p>
      ))}

      {state.error && <p className="activity-stream__error">{state.error}</p>}

      {state.stream.entries.length === 0 ? (
        <div className="activity-stream__empty">No activity matches this view.</div>
      ) : (
        state.stream.groups.map((group) => (
          <DateGroupView
            key={`${group.period}-${group.key}`}
            group={group}
            density={state.density}
            now={state.now}
            selectedSequence={state.selectedSequence}
            onSelect={(sequence) => dispatch({ type: "select", value: sequence })}
            onJump={onJump}
          />
        ))
      )}
    </div>
  );
}
