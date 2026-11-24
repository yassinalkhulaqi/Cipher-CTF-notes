/** Main activity feature: stream, digests, retrospectives, and resolver jumps. */

import { useCallback, useEffect, useMemo, useReducer, useState } from "react";

import { makeActivityClient, type ActivityClient } from "./client";
import { validateFilterQuery } from "./filters";
import { PERIOD_OPTIONS } from "./format";
import {
  activityReducer,
  digestRequest,
  effectiveQuery,
  initialActivityState,
  retrospectiveRequest,
  stateSignature,
  streamRequest,
  type ActivityTab,
} from "./state";
import type { FilterValidation, JumpTarget } from "./types";
import { ActivityStream } from "./components/ActivityStream";
import { DigestCard } from "./components/DigestCard";
import { RetrospectiveView } from "./components/RetrospectiveView";
import { V3Panel } from "../../v3/components/V3Panel";
import "./activity.css";

export interface ActivityFeatureProps {
  client?: ActivityClient;
  identity?: string;
  onNavigate?: (route: string) => void;
}

const TABS: ActivityTab[] = ["stream", "digest", "retrospective"];

export function ActivityFeature({
  client,
  identity = "local",
  onNavigate,
}: ActivityFeatureProps) {
  const [state, dispatch] = useReducer(activityReducer, undefined, () =>
    initialActivityState({ now: Math.floor(Date.now() / 1000) }),
  );
  const [validation, setValidation] = useState<FilterValidation | null>(null);
  const activeClient = useMemo(() => client ?? makeActivityClient(), [client]);
  const signature = stateSignature(state);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      dispatch({ type: "loading" });
      try {
        const [stream, digests, retrospective, since] = await Promise.all([
          activeClient.stream(streamRequest(state)),
          activeClient.digest(digestRequest(state)),
          activeClient.retrospective(
            retrospectiveRequest(state).start ?? 0,
            retrospectiveRequest(state).end ?? 1,
          ),
          activeClient.since(identity),
        ]);
        if (cancelled) return;
        dispatch({ type: "stream", value: stream });
        dispatch({ type: "digests", value: digests });
        dispatch({ type: "retrospective", value: retrospective });
        dispatch({ type: "since", value: since });
      } catch (error) {
        if (!cancelled) {
          dispatch({
            type: "error",
            value: error instanceof Error ? error.message : String(error),
          });
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
    // The signature covers the request-affecting state fields.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeClient, identity, signature]);

  useEffect(() => {
    const query = effectiveQuery(state);
    if (!query) {
      setValidation(null);
      return;
    }
    let cancelled = false;
    void activeClient
      .validate(query)
      .then((result) => {
        if (!cancelled) setValidation(result);
      })
      .catch(() => {
        if (!cancelled) setValidation(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeClient, state.query, state.chips]);

  const jump = useCallback(
    (target: JumpTarget) => {
      onNavigate?.(target.route);
    },
    [onNavigate],
  );

  const markVisited = useCallback(async () => {
    try {
      await activeClient.mark(
        identity,
        "marked from activity",
        state.stream.total,
      );
      const since = await activeClient.since(identity);
      dispatch({ type: "since", value: since });
    } catch (error) {
      dispatch({
        type: "error",
        value: error instanceof Error ? error.message : String(error),
      });
    }
  }, [activeClient, identity, state.stream.total]);

  return (
    <V3Panel
      title="Activity"
      subtitle={`Timeline for ${identity}`}
      kind="activity"
      density={state.density === "compact" ? "compact" : "comfortable"}
      actions={
        <button
          type="button"
          className="activity-mark"
          onClick={() => void markVisited()}
        >
          Mark visited
        </button>
      }
    >
      <div className="activity-tabs" role="tablist" aria-label="Activity views">
        {TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={state.tab === tab}
            data-active={state.tab === tab ? "true" : "false"}
            onClick={() => dispatch({ type: "tab", value: tab })}
          >
            {tab === "retrospective"
              ? "Retrospective"
              : tab === "digest"
                ? "Digests"
                : "Stream"}
          </button>
        ))}
      </div>

      {state.tab === "stream" && (
        <ActivityStream
          state={state}
          dispatch={dispatch}
          validation={validation}
          onJump={jump}
        />
      )}

      {state.tab === "digest" && (
        <div className="activity-digests">
          <div
            className="activity-periods"
            role="group"
            aria-label="Digest period"
          >
            {PERIOD_OPTIONS.map((period) => (
              <button
                key={period}
                type="button"
                data-active={state.period === period ? "true" : "false"}
                onClick={() => dispatch({ type: "period", value: period })}
              >
                {period}
              </button>
            ))}
          </div>
          {state.digests?.digests.length ? (
            state.digests.digests.map((digest) => (
              <DigestCard
                key={`${digest.period}-${digest.key}`}
                digest={digest}
                onJump={jump}
                onSelect={(sequence) =>
                  dispatch({ type: "select", value: sequence })
                }
              />
            ))
          ) : (
            <p className="activity-empty">No digests available yet.</p>
          )}
        </div>
      )}

      {state.tab === "retrospective" &&
        (state.retrospective ? (
          <RetrospectiveView summary={state.retrospective} onJump={jump} />
        ) : (
          <p className="activity-empty">No retrospective available yet.</p>
        ))}
    </V3Panel>
  );
}
