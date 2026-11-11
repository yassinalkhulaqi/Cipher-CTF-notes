import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type {
  FlagHit,
  FlagInsights,
  NodeSummary,
  Template,
  TimelineEvent,
} from "../lib/types";

export interface DashboardData {
  templates: Template[];
  events: TimelineEvent[];
  activityLoading: boolean;
  flags: FlagHit[];
  flagsLoading: boolean;
  insights: FlagInsights | null;
}

/**
 * Loads dashboard backing data (templates, recent activity, captured flags,
 * flag insights). Effects key off a stable signature derived from the note
 * list (count + most recent update) â€” not the `nodes` Map identity â€” so
 * unrelated tree refreshes (rename, pin, move) no longer re-fetch everything.
 */
export function useDashboardData(notes: NodeSummary[]): DashboardData {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [activityLoading, setActivityLoading] = useState(true);
  const [flags, setFlags] = useState<FlagHit[]>([]);
  const [flagsLoading, setFlagsLoading] = useState(true);
  const [insights, setInsights] = useState<FlagInsights | null>(null);

  const signature = useMemo(() => {
    const count = notes.length;
    const latest = notes.reduce(
      (max, note) =>
        note.updated_at > max ? note.updated_at : max,
      "",
    );
    return `${count}:${latest}`;
  }, [notes]);

  useEffect(() => {
    let cancelled = false;
    api
      .templates()
      .then((items) => {
        if (!cancelled) setTemplates(items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setActivityLoading(true);
    api
      .timeline(null, 7)
      .then((items) => {
        if (cancelled) return;
        setEvents(items);
        setActivityLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setEvents([]);
        setActivityLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [signature]);

  useEffect(() => {
    if (notes.length === 0) {
      setFlags([]);
      setFlagsLoading(false);
      return;
    }
    let cancelled = false;
    setFlagsLoading(true);
    api
      .collectedFlags()
      .then((items) => {
        if (cancelled) return;
        setFlags(items);
        setFlagsLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setFlags([]);
        setFlagsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [signature]);

  useEffect(() => {
    if (notes.length === 0) {
      setInsights(null);
      return;
    }
    let cancelled = false;
    api
      .flagInsights()
      .then((items) => {
        if (!cancelled) setInsights(items);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [signature]);

  return { templates, events, activityLoading, flags, flagsLoading, insights };
}
