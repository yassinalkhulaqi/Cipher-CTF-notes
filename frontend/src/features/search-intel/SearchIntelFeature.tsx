/** Search intelligence feature: facets, clusters, pivots and saved queries. */

import { useEffect, useMemo, useState } from "react";

import { V3Panel, V3Stat } from "../../v3/components/V3Panel";
import { groupHitsByCluster } from "./clusters";
import { createSearchIntelClient } from "./client";
import { toggleFacetValue } from "./facets";
import { formatCount } from "./format";
import { completeQuery, parseQueryV2, serializeQueryV2 } from "./query";
import type {
  ClusterGroupV2,
  PivotContextV2,
  PivotSuggestionV2,
  SavedFacetSetV2,
  SavedSearchDraftV2,
  SavedSearchV2,
  SearchResponseV2,
} from "./types";
import { ClusterGroups } from "./components/ClusterGroups";
import { FacetSidebar } from "./components/FacetSidebar";
import { PivotChips } from "./components/PivotChips";
import { QueryBuilder } from "./components/QueryBuilder";
import { ResultList } from "./components/ResultList";
import { SavedSearchManager } from "./components/SavedSearchManager";
import "../search-intel.css";
import "../../styles/tokens-v3.css";

export interface SearchIntelFeatureProps {
  client?: ReturnType<typeof createSearchIntelClient>;
  initialQuery?: string;
}

export function SearchIntelFeature({
  client,
  initialQuery = "",
}: SearchIntelFeatureProps) {
  const api = useMemo(() => client ?? createSearchIntelClient(), [client]);
  const [query, setQuery] = useState(initialQuery);
  const [response, setResponse] = useState<SearchResponseV2 | null>(null);
  const [selection, setSelection] = useState<Record<string, string[]>>({});
  const [saved, setSaved] = useState<SavedSearchV2[]>([]);
  const [facetSets, setFacetSets] = useState<SavedFacetSetV2[]>([]);
  const [activeSetId, setActiveSetId] = useState("");
  const [selectedRef, setSelectedRef] = useState("");
  const [activeCluster, setActiveCluster] = useState("");
  const [pivotContext, setPivotContext] = useState<
    PivotContextV2 | undefined
  >();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const parsed = useMemo(() => parseQueryV2(query), [query]);
  const completions = useMemo(() => {
    const tags = response?.hits.flatMap((hit) => hit.document.tags) ?? [];
    return completeQuery(query, {
      saved: saved.map((item) => ({ name: item.name, query: item.query })),
      tags: [...new Set(tags.map((tag) => tag.toLowerCase()))].sort(),
    });
  }, [query, response, saved]);

  const runSearch = async (expression = query) => {
    setBusy(true);
    setError("");
    try {
      const result = await api.search({
        query: expression,
        selected: selection,
        fields: ["kind", "status", "severity", "tag", "has_link"],
      });
      setResponse(result);
      setActiveCluster("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Search failed");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    Promise.all([api.savedList(), api.facetSets()])
      .then(([savedItems, sets]) => {
        if (!mounted) return;
        setSaved(savedItems);
        setFacetSets(sets);
      })
      .catch((cause: unknown) => {
        if (mounted)
          setError(cause instanceof Error ? cause.message : "Load failed");
      });
    return () => {
      mounted = false;
    };
  }, [api]);

  const toggleFacet = (field: string, value: string) => {
    const next = toggleFacetValue(selection, field, value);
    setSelection(next);
    setActiveSetId("");
    void runSearch(query);
  };

  const applySet = (set: SavedFacetSetV2) => {
    const next: Record<string, string[]> = {};
    for (const field of set.fields) next[field] = [];
    setSelection(next);
    setActiveSetId(set.id);
    void runSearch(query);
  };

  const loadSaved = (item: SavedSearchV2) => {
    setQuery(item.query);
    setSelection({});
    setActiveSetId("");
    void runSearch(item.query);
  };

  const saveDraft = async (draft: SavedSearchDraftV2) => {
    try {
      const item = await api.savedCreate({
        name: draft.name,
        query: draft.query,
        description: draft.description,
        tags: draft.tags,
        pinned: draft.pinned,
      });
      setSaved((current) => [item, ...current]);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Save failed");
    }
  };

  const deleteSaved = async (id: string) => {
    try {
      await api.savedDelete(id);
      setSaved((current) => current.filter((item) => item.id !== id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Delete failed");
    }
  };

  const pinSaved = async (id: string) => {
    const item = saved.find((entry) => entry.id === id);
    if (!item) return;
    try {
      const updated = await api.savedUpdate(id, { pinned: !item.pinned });
      setSaved((current) =>
        current.map((entry) => (entry.id === id ? updated : entry)),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Pin failed");
    }
  };

  const onPivot = (pivot: PivotSuggestionV2) => {
    setPivotContext(
      (current) =>
        current ?? {
          origin: pivot.ref,
          origin_kind: pivot.kind,
          origin_title: pivot.label,
          pivots: [],
          destinations: [],
        },
    );
    setQuery(pivot.query);
    void runSearch(pivot.query);
  };

  const clusters: ClusterGroupV2[] = response?.clusters ?? [];
  const visibleHits = useMemo(() => {
    const hits = response?.hits ?? [];
    if (!activeCluster) return hits;
    const cluster = clusters.find((item) => item.key === activeCluster);
    return hits.filter((hit) => cluster?.refs.includes(hit.document.ref));
  }, [response, activeCluster, clusters]);
  const grouped = groupHitsByCluster(visibleHits, clusters);
  const activeContext = pivotContext ?? response?.pivots[0];

  return (
    <div
      className="si-feature"
      data-density="comfortable"
      data-testid="search-intel-feature"
    >
      <V3Panel
        subtitle="Cross-entity query language v2 with facets, clusters and pivots"
        title="Search intelligence"
      >
        <QueryBuilder
          completions={completions}
          disabled={busy}
          issues={parsed.issues}
          onChange={setQuery}
          onRun={() => void runSearch()}
          onSave={() => {
            const draft: SavedSearchDraftV2 = {
              id: "",
              name: query.slice(0, 40) || "New search",
              query: serializeQueryV2(parsed) || query,
              description: "",
              tags: [],
              pinned: false,
            };
            void saveDraft(draft);
          }}
          value={query}
        />
        <div className="si-feature__stats">
          <V3Stat label="Matches" value={formatCount(response?.total ?? 0)} />
          <V3Stat label="Clusters" value={clusters.length} />
          <V3Stat
            label="Indexed"
            value={formatCount(response?.index.documents ?? 0)}
            hint={`generation ${response?.index.generation ?? 0}`}
          />
        </div>
        {error && (
          <p className="si-feature__error" role="alert">
            {error}
          </p>
        )}
        <div className="si-feature__layout">
          <FacetSidebar
            activeSetId={activeSetId}
            facetSets={facetSets}
            facets={response?.facets ?? []}
            onApplySet={applySet}
            onClear={() => {
              setSelection({});
              setActiveSetId("");
              void runSearch(query);
            }}
            onToggle={toggleFacet}
            selection={selection}
          />
          <main className="si-feature__results">
            <ClusterGroups
              activeKey={activeCluster}
              clusters={clusters}
              onSelect={(cluster) =>
                setActiveCluster((current) =>
                  current === cluster.key ? "" : cluster.key,
                )
              }
            />
            <PivotChips context={activeContext} onPivot={onPivot} />
            <ResultList
              hits={visibleHits}
              onSelect={(hit) => setSelectedRef(hit.document.ref)}
              selectedRef={selectedRef}
            />
            <p
              className="si-feature__groups"
              data-testid="search-result-groups"
            >
              {grouped.length} group{grouped.length === 1 ? "" : "s"} displayed
            </p>
          </main>
          <SavedSearchManager
            currentQuery={query}
            items={saved}
            onDelete={(id) => void deleteSaved(id)}
            onLoad={loadSaved}
            onPin={(id) => void pinSaved(id)}
            onSave={(draft) => void saveDraft(draft)}
          />
        </div>
      </V3Panel>
    </div>
  );
}

export default SearchIntelFeature;
