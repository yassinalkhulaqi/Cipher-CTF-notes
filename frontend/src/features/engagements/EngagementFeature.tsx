import { useCallback, useEffect, useMemo, useState } from "react";
import { Banner } from "../../ui/Banner";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { Field } from "../../ui/Field";
import { Tabs, type TabItem } from "../../ui/Tabs";
import { ApiClientError } from "../../lib/apiClient";
import { EngagementApi } from "./api";
import { DashboardWidgets } from "./DashboardWidgets";
import { EngagementList } from "./EngagementList";
import { FindingEditor } from "./FindingEditor";
import { CredentialTable, AssetTable, ServiceTable } from "./InventoryTables";
import { ScopeEditor } from "./ScopeEditor";
import { TargetTable } from "./TargetTable";
import { engagementTitle, transitionLabel } from "./logic";
import type {
  Activity,
  Asset,
  Credential,
  DashboardPayload,
  EngagementKind,
  EngagementSummary,
  Finding,
  ScopeRule,
  Service,
  Target,
} from "./types";

export interface EngagementFeatureProps {
  api?: EngagementApi;
  initialEngagementId?: number;
}

interface EngagementDraft {
  name: string;
  client: string;
  kind: EngagementKind;
  description: string;
  owner: string;
  start_date: string;
  end_date: string;
}

const EMPTY_ENGAGEMENT: EngagementDraft = {
  name: "",
  client: "",
  kind: "pentest",
  description: "",
  owner: "",
  start_date: "",
  end_date: "",
};

function errorMessage(error: unknown): string {
  if (error instanceof ApiClientError) {
    return `${error.code}: ${error.message}`;
  }
  if (error instanceof Error) return error.message;
  return "Unexpected engagement error";
}

export function EngagementFeature({
  api,
  initialEngagementId,
}: EngagementFeatureProps) {
  const client = useMemo(() => api ?? new EngagementApi(), [api]);
  const [engagements, setEngagements] = useState<EngagementSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(
    initialEngagementId ?? null,
  );
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [targets, setTargets] = useState<Target[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [rules, setRules] = useState<ScopeRule[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("dashboard");
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<EngagementDraft>(EMPTY_ENGAGEMENT);

  const refreshEngagements = useCallback(async () => {
    const page = await client.listEngagements({ limit: 100 });
    setEngagements(page.items);
  }, [client]);

  const refreshSelected = useCallback(
    async (id: number) => {
      setLoading(true);
      setError("");
      try {
        const [
          nextDashboard,
          targetPage,
          assetPage,
          servicePage,
          credentialPage,
          findingPage,
          rulePage,
          activityPage,
        ] = await Promise.all([
          client.dashboard(id),
          client.listTargets(id, { limit: 200 }),
          client.listAssets(id, { limit: 200 }),
          client.listServices(id, { limit: 200 }),
          client.listCredentials(id, { limit: 200 }),
          client.listFindings(id, { limit: 200 }),
          client.listScopeRules(id),
          client.activity(id, 50),
        ]);
        setDashboard(nextDashboard);
        setTargets(targetPage.items);
        setAssets(assetPage.items);
        setServices(servicePage.items);
        setCredentials(credentialPage.items);
        setFindings(findingPage.items);
        setRules(rulePage.items);
        setActivity(activityPage.items);
        await refreshEngagements();
      } catch (cause) {
        setError(errorMessage(cause));
      } finally {
        setLoading(false);
      }
    },
    [client, refreshEngagements],
  );

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        await refreshEngagements();
        if (mounted && selectedId !== null) await refreshSelected(selectedId);
      } catch (cause) {
        if (mounted) {
          setError(errorMessage(cause));
          setLoading(false);
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, [refreshEngagements, refreshSelected, selectedId]);

  const select = (id: number) => {
    setSelectedId(id);
    setTab("dashboard");
  };

  const mutate = async (work: () => Promise<unknown>) => {
    if (selectedId === null) return;
    setError("");
    try {
      await work();
      await refreshSelected(selectedId);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };

  const createEngagement = async () => {
    setError("");
    try {
      const created = await client.createEngagement({ ...draft });
      setCreating(false);
      setDraft(EMPTY_ENGAGEMENT);
      await refreshEngagements();
      select(created.id);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };

  const seedDemo = () => {
    void mutate(async () => {
      const result = await client.seedDemo();
      if (result.engagement) select(result.engagement.id);
    });
  };

  const tabs: TabItem[] = [
    {
      id: "dashboard",
      label: "Dashboard",
      content: dashboard ? <DashboardWidgets dashboard={dashboard} /> : null,
    },
    {
      id: "scope",
      label: `Scope (${rules.length})`,
      content: (
        <ScopeEditor
          rules={rules}
          onAdd={(data) =>
            mutate(() => client.addScopeRule(selectedId ?? 0, data))
          }
          onRemove={(id) =>
            mutate(() => client.removeScopeRule(selectedId ?? 0, id))
          }
        />
      ),
    },
    {
      id: "targets",
      label: `Targets (${targets.length})`,
      content: (
        <TargetTable
          targets={targets}
          onCreate={(data) =>
            mutate(() => client.createTarget(selectedId ?? 0, data))
          }
          onUpdate={(id, data) => mutate(() => client.updateTarget(id, data))}
          onRemove={(id) => mutate(() => client.removeTarget(id))}
          onScopeTransition={(id, action) =>
            mutate(() => client.transitionTargetScope(id, action))
          }
        />
      ),
    },
    {
      id: "inventory",
      label: `Inventory (${assets.length + services.length + credentials.length})`,
      content: (
        <div className="eng-stack">
          <AssetTable
            items={assets}
            targets={targets}
            onCreate={(data) =>
              mutate(() => client.createAsset(selectedId ?? 0, data))
            }
            onUpdate={(id, data) => mutate(() => client.updateAsset(id, data))}
            onRemove={(id) => mutate(() => client.removeAsset(id))}
          />
          <ServiceTable
            items={services}
            targets={targets}
            onCreate={(data) =>
              mutate(() => client.createService(selectedId ?? 0, data))
            }
            onUpdate={(id, data) =>
              mutate(() => client.updateService(id, data))
            }
            onRemove={(id) => mutate(() => client.removeService(id))}
          />
          <CredentialTable
            items={credentials}
            targets={targets}
            onCreate={(data) =>
              mutate(() => client.createCredential(selectedId ?? 0, data))
            }
            onUpdate={(id, data) =>
              mutate(() => client.updateCredential(id, data))
            }
            onRemove={(id) => mutate(() => client.removeCredential(id))}
          />
        </div>
      ),
    },
    {
      id: "findings",
      label: `Findings (${findings.length})`,
      content: (
        <FindingEditor
          findings={findings}
          onCreate={(data) =>
            mutate(() => client.createFinding(selectedId ?? 0, data))
          }
          onUpdate={(id, data) => mutate(() => client.updateFinding(id, data))}
          onTransition={(id, action, data) =>
            mutate(() => client.transitionFinding(id, action, data))
          }
          onDuplicate={(id, canonicalId) =>
            mutate(() => client.markDuplicate(id, canonicalId))
          }
          onRemove={(id) => mutate(() => client.removeFinding(id))}
        />
      ),
    },
    {
      id: "activity",
      label: `Activity (${activity.length})`,
      content: (
        <section className="eng-panel" aria-label="Engagement activity">
          <h3 className="eng-panel__title">Activity</h3>
          {activity.length === 0 ? (
            <p className="eng-panel__subtitle">No recorded activity.</p>
          ) : (
            <ul className="eng-activity-list">
              {activity.map((item) => (
                <li key={item.id}>
                  <span className="eng-activity-list__meta">
                    {item.created_at.slice(0, 16)}
                  </span>
                  <strong>{item.summary || item.action}</strong>
                  <span>{item.actor || "system"}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      ),
    },
  ];

  const selected = engagements.find((item) => item.id === selectedId) ?? null;

  return (
    <div className="eng-feature">
      {error ? (
        <Banner
          tone="danger"
          title="Engagement error"
          onDismiss={() => setError("")}
        >
          {error}
        </Banner>
      ) : null}
      <div className="eng-feature__layout">
        <aside className="eng-feature__sidebar">
          <EngagementList
            engagements={engagements}
            selectedId={selectedId}
            loading={loading && engagements.length === 0}
            onSelect={select}
            onCreate={() => setCreating(true)}
            onSeedDemo={seedDemo}
          />
        </aside>
        <main className="eng-feature__main">
          {selected ? (
            <>
              <header className="eng-feature__head">
                <div>
                  <h1 className="eng-feature__title">
                    {engagementTitle(selected)}
                  </h1>
                  <p className="eng-panel__subtitle">
                    {selected.client || "No client"} · owned by{" "}
                    {selected.owner || "unassigned"}
                  </p>
                </div>
                <div className="eng-feature__actions">
                  {(selected.allowed_actions ?? []).map((action) => (
                    <Button
                      key={action}
                      size="sm"
                      variant="secondary"
                      onClick={() =>
                        mutate(() =>
                          client.transitionEngagement(selected.id, action),
                        )
                      }
                    >
                      {transitionLabel(action)}
                    </Button>
                  ))}
                </div>
              </header>
              {loading ? (
                <p className="eng-panel__subtitle">Refreshing engagement…</p>
              ) : null}
              <Tabs
                items={tabs}
                label="Engagement sections"
                value={tab}
                onChange={setTab}
              />
            </>
          ) : (
            <div className="eng-feature__empty">
              <h1 className="eng-feature__title">Engagement workspace</h1>
              <p className="eng-panel__subtitle">
                Select an engagement to review scope, assets, and findings.
              </p>
            </div>
          )}
        </main>
      </div>
      <Dialog
        open={creating}
        onClose={() => setCreating(false)}
        title="New engagement"
        description="Create a container for scope, inventory, and findings."
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void createEngagement()}>
              Create engagement
            </Button>
          </>
        }
      >
        <div className="eng-form-grid">
          <Field
            label="Name"
            value={draft.name}
            onChange={(event) =>
              setDraft({ ...draft, name: event.target.value })
            }
          />
          <Field
            label="Client"
            value={draft.client}
            onChange={(event) =>
              setDraft({ ...draft, client: event.target.value })
            }
          />
          <label className="eng-select">
            <span>Kind</span>
            <select
              value={draft.kind}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  kind: event.target.value as EngagementKind,
                })
              }
            >
              <option value="pentest">Pentest</option>
              <option value="red_team">Red team</option>
              <option value="ctf">CTF</option>
              <option value="lab">Lab</option>
              <option value="audit">Audit</option>
              <option value="research">Research</option>
            </select>
          </label>
          <Field
            label="Owner"
            value={draft.owner}
            onChange={(event) =>
              setDraft({ ...draft, owner: event.target.value })
            }
          />
          <Field
            label="Start date"
            type="date"
            value={draft.start_date}
            onChange={(event) =>
              setDraft({ ...draft, start_date: event.target.value })
            }
          />
          <Field
            label="End date"
            type="date"
            value={draft.end_date}
            onChange={(event) =>
              setDraft({ ...draft, end_date: event.target.value })
            }
          />
          <label className="eng-textarea">
            <span>Description</span>
            <textarea
              rows={4}
              value={draft.description}
              onChange={(event) =>
                setDraft({ ...draft, description: event.target.value })
              }
            />
          </label>
        </div>
      </Dialog>
    </div>
  );
}
