import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClientError } from "../../lib/apiClient";
import { PlaybooksClient } from "./client";
import {
  filterPlaybooks,
  groupRecommendations,
  playbookStats,
  sortPlaybooks,
} from "./helpers";
import type {
  Playbook,
  PlaybookSummary,
  Recommendation,
  RunPlan,
  RunState,
  SnippetRecord,
  TemplateRecord,
} from "./types";

export interface PlaybooksFilters {
  query: string;
  tags: string[];
  status: string;
  category: string;
  sort: "title" | "status" | "steps" | "updated" | "version";
  direction: "asc" | "desc";
}

export const initialFilters: PlaybooksFilters = {
  query: "",
  tags: [],
  status: "",
  category: "",
  sort: "title",
  direction: "asc",
};

export interface PlaybooksController {
  client: PlaybooksClient;
  loading: boolean;
  saving: boolean;
  error: string;
  notice: string;
  filters: PlaybooksFilters;
  playbooks: PlaybookSummary[];
  visible: PlaybookSummary[];
  selected: Playbook | null;
  snippets: SnippetRecord[];
  templates: TemplateRecord[];
  recommendations: Recommendation[];
  recommendationGroups: ReturnType<typeof groupRecommendations>;
  stats: Record<string, number>;
  plan: RunPlan | null;
  run: RunState | null;
  setFilters: (changes: Partial<PlaybooksFilters>) => void;
  refresh: () => Promise<void>;
  select: (key: string) => Promise<void>;
  setNotice: (message: string) => void;
  savePlaybook: (playbook: Playbook) => Promise<void>;
  duplicate: (key: string) => Promise<void>;
  remove: (key: string) => Promise<void>;
  makePlan: (key: string, values: Record<string, unknown>) => Promise<void>;
  start: (key: string, values: Record<string, unknown>) => Promise<void>;
  advance: (stepId: string, status?: string) => Promise<void>;
  clearRun: () => void;
}

function messageOf(error: unknown): string {
  if (error instanceof ApiClientError) return error.message;
  if (error instanceof Error) return error.message;
  return String(error);
}

function toSummaries(playbooks: readonly Playbook[]): PlaybookSummary[] {
  return playbooks.map((playbook) => {
    const { steps: _steps, variables: _variables, ...summary } = playbook;
    return {
      ...summary,
      step_count: playbook.steps.length,
      checklist_count: playbook.steps.reduce(
        (total, step) => total + step.checklist.length,
        0,
      ),
    };
  });
}

export function usePlaybooks(client: PlaybooksClient): PlaybooksController {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filters, setFiltersState] = useState<PlaybooksFilters>(initialFilters);
  const [allPlaybooks, setAllPlaybooks] = useState<Playbook[]>([]);
  const [selected, setSelected] = useState<Playbook | null>(null);
  const [snippets, setSnippets] = useState<SnippetRecord[]>([]);
  const [templates, setTemplates] = useState<TemplateRecord[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [plan, setPlan] = useState<RunPlan | null>(null);
  const [run, setRun] = useState<RunState | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [
        playbookPage,
        snippetPage,
        templatePage,
        recommendationRows,
        statsResult,
      ] = await Promise.all([
        client.listPlaybooks({ limit: 200 }),
        client.listSnippets({ limit: 200 }),
        client.listTemplates({ limit: 200 }),
        client.recommend({ query: filters.query, tags: filters.tags }),
        client.stats(),
      ]);
      const playbooks = await Promise.all(
        playbookPage.items.map((item) => client.getPlaybook(item.key)),
      );
      setAllPlaybooks(playbooks);
      setSnippets(snippetPage.items);
      setTemplates(templatePage.items);
      setRecommendations(recommendationsFrom(recommendationRows));
      setStats(numericStats(statsResult));
      setSelected((current) => {
        if (!current) return playbooks[0] ?? null;
        return (
          playbooks.find((item) => item.key === current.key) ??
          playbooks[0] ??
          null
        );
      });
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setLoading(false);
    }
  }, [client, filters.query, filters.tags]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const playbooks = useMemo(() => toSummaries(allPlaybooks), [allPlaybooks]);
  const visible = useMemo(
    () =>
      sortPlaybooks(
        filterPlaybooks(allPlaybooks, {
          query: filters.query,
          tags: filters.tags,
          status: filters.status,
          category: filters.category,
        }),
        filters.sort,
        filters.direction,
      ).map((playbook) => {
        const { steps: _steps, variables: _variables, ...summary } = playbook;
        return {
          ...summary,
          step_count: playbook.steps.length,
          checklist_count: playbook.steps.reduce(
            (total, step) => total + step.checklist.length,
            0,
          ),
        };
      }),
    [allPlaybooks, filters],
  );

  const recommendationGroups = useMemo(
    () => groupRecommendations(recommendations),
    [recommendations],
  );
  const computedStats = useMemo(() => {
    if (Object.keys(stats).length > 0) return stats;
    return playbookStats(allPlaybooks);
  }, [allPlaybooks, stats]);

  const setFilters = useCallback((changes: Partial<PlaybooksFilters>) => {
    setFiltersState((current) => ({ ...current, ...changes }));
  }, []);

  const select = useCallback(
    async (key: string) => {
      setError("");
      try {
        const playbook = await client.getPlaybook(key);
        setSelected(playbook);
        setPlan(null);
        setRun(null);
      } catch (caught) {
        setError(messageOf(caught));
      }
    },
    [client],
  );

  const savePlaybook = useCallback(
    async (playbook: Playbook) => {
      setSaving(true);
      setError("");
      try {
        const saved = await client.updatePlaybook(playbook.key, {
          title: playbook.title,
          description: playbook.description,
          status: playbook.status,
          category: playbook.category,
          tags: playbook.tags,
          steps: playbook.steps,
          variables: playbook.variables,
        });
        setSelected(saved);
        setNotice(`Saved ${saved.key} v${saved.version}`);
        await refresh();
      } catch (caught) {
        setError(messageOf(caught));
      } finally {
        setSaving(false);
      }
    },
    [client, refresh],
  );

  const duplicate = useCallback(
    async (key: string) => {
      setSaving(true);
      setError("");
      try {
        const clone = await client.clonePlaybook(key);
        setNotice(`Created ${clone.key}`);
        await refresh();
        await select(clone.key);
      } catch (caught) {
        setError(messageOf(caught));
      } finally {
        setSaving(false);
      }
    },
    [client, refresh, select],
  );

  const remove = useCallback(
    async (key: string) => {
      setSaving(true);
      setError("");
      try {
        await client.deletePlaybook(key);
        setNotice(`Deleted ${key}`);
        setSelected(null);
        await refresh();
      } catch (caught) {
        setError(messageOf(caught));
      } finally {
        setSaving(false);
      }
    },
    [client, refresh],
  );

  const makePlan = useCallback(
    async (key: string, values: Record<string, unknown>) => {
      setSaving(true);
      setError("");
      try {
        const result = await client.planRun(key, values);
        setPlan(result);
        setNotice(`Planned ${result.steps.length} steps`);
      } catch (caught) {
        setError(messageOf(caught));
      } finally {
        setSaving(false);
      }
    },
    [client],
  );

  const start = useCallback(
    async (key: string, values: Record<string, unknown>) => {
      setSaving(true);
      setError("");
      try {
        const started = await client.startRun(key, values);
        setRun(started);
        setNotice(`Started run #${started.id}`);
      } catch (caught) {
        setError(messageOf(caught));
      } finally {
        setSaving(false);
      }
    },
    [client],
  );

  const advance = useCallback(
    async (stepId: string, status = "done") => {
      if (!run) return;
      setSaving(true);
      setError("");
      try {
        const updated = await client.advanceRun(run.id, stepId, status);
        setRun(updated);
        setNotice(`Step ${stepId} marked ${status}`);
      } catch (caught) {
        setError(messageOf(caught));
      } finally {
        setSaving(false);
      }
    },
    [client, run],
  );

  const clearRun = useCallback(() => {
    setRun(null);
    setPlan(null);
  }, []);

  return {
    client,
    loading,
    saving,
    error,
    notice,
    filters,
    playbooks,
    visible,
    selected,
    snippets,
    templates,
    recommendations,
    recommendationGroups,
    stats: computedStats,
    plan,
    run,
    setFilters,
    refresh,
    select,
    setNotice,
    savePlaybook,
    duplicate,
    remove,
    makePlan,
    start,
    advance,
    clearRun,
  };
}

function recommendationsFrom(rows: unknown): Recommendation[] {
  if (!Array.isArray(rows)) return [];
  return rows.filter((row): row is Recommendation => {
    if (typeof row !== "object" || row === null) return false;
    const item = row as Record<string, unknown>;
    return typeof item.key === "string" && typeof item.kind === "string";
  });
}

function numericStats(
  result: Record<string, number | string | string[]>,
): Record<string, number> {
  const output: Record<string, number> = {};
  for (const [key, value] of Object.entries(result)) {
    if (typeof value === "number") output[key] = value;
    if (typeof value === "string" && /^\d+$/.test(value))
      output[key] = Number(value);
    if (Array.isArray(value)) output[key] = value.length;
  }
  return output;
}
