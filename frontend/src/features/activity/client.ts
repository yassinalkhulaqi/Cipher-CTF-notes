/** Typed client for the V3 activity namespace. */

import { V3Client } from "../../v3/apiClient";
import type {
  ActivityEntry,
  ActivityHealth,
  ActivityModes,
  ActivityStats,
  DigestCollection,
  FilterMetadata,
  FilterValidation,
  RedactionReportData,
  RetrospectiveSummary,
  SinceLastVisit,
  StreamResult,
  VisitMarker,
} from "./types";

export interface ActivityRequestBody {
  query?: string;
  kinds?: string[];
  exclude_kinds?: string[];
  actors?: string[];
  subjects?: string[];
  severities?: string[];
  tags?: string[];
  correlation_id?: string;
  since?: number;
  until?: number;
  offset?: number;
  size?: number;
  density?: string;
  timezone?: string;
  identity?: string;
  limit?: number;
  period?: string;
  anchor?: number;
  generated_at?: number;
  highlight_limit?: number;
  start?: number;
  end?: number;
  top_limit?: number;
  note?: string;
  sequence?: number;
  timestamp?: number;
  payload?: Record<string, unknown>;
}

const ROUTES = {
  stream: "stream",
  filters: "filters",
  validate: "validate",
  digest: "digest",
  since: "since",
  mark: "mark",
  retrospective: "retrospective",
  redact: "redact",
  entry: "entry",
  stats: "stats",
  health: "health",
  modes: "modes",
} as const;

export class ActivityClient {
  readonly routes: Record<string, string> = { ...ROUTES };

  constructor(private readonly client: V3Client) {}

  async stream(body: ActivityRequestBody = {}): Promise<StreamResult> {
    return this.client.data<StreamResult>("activity", ROUTES.stream, body);
  }

  async filters(): Promise<FilterMetadata> {
    return this.client.data<FilterMetadata>("activity", ROUTES.filters);
  }

  async validate(query: string): Promise<FilterValidation> {
    return this.client.data<FilterValidation>("activity", ROUTES.validate, {
      query,
    });
  }

  async digest(body: ActivityRequestBody = {}): Promise<DigestCollection> {
    return this.client.data<DigestCollection>("activity", ROUTES.digest, body);
  }

  async since(identity: string, limit?: number): Promise<SinceLastVisit> {
    return this.client.data<SinceLastVisit>("activity", ROUTES.since, {
      identity,
      ...(limit === undefined ? {} : { limit }),
    });
  }

  async mark(
    identity: string,
    note = "",
    sequence?: number,
  ): Promise<VisitMarker> {
    return this.client.data<VisitMarker>("activity", ROUTES.mark, {
      identity,
      note,
      ...(sequence === undefined ? {} : { sequence }),
    });
  }

  async retrospective(
    start: number,
    end: number,
    topLimit = 5,
  ): Promise<RetrospectiveSummary> {
    return this.client.data<RetrospectiveSummary>(
      "activity",
      ROUTES.retrospective,
      {
        start,
        end,
        top_limit: topLimit,
      },
    );
  }

  async redact(
    payload: Record<string, unknown>,
  ): Promise<{
    payload: Record<string, unknown>;
    report: RedactionReportData;
  }> {
    return this.client.data("activity", ROUTES.redact, { payload });
  }

  async entry(sequence: number): Promise<ActivityEntry> {
    return this.client.data<ActivityEntry>("activity", ROUTES.entry, {
      sequence,
    });
  }

  async stats(): Promise<ActivityStats> {
    return this.client.data<ActivityStats>("activity", ROUTES.stats);
  }

  async health(): Promise<ActivityHealth> {
    return this.client.data<ActivityHealth>("activity", ROUTES.health);
  }

  async modes(): Promise<ActivityModes> {
    return this.client.data<ActivityModes>("activity", ROUTES.modes);
  }
}

export function makeActivityClient(
  options: ConstructorParameters<typeof V3Client>[0] = {},
): ActivityClient {
  return new ActivityClient(new V3Client(options));
}
