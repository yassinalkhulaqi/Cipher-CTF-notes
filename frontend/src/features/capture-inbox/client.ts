import { V4ApiError, V4Client } from "../v4-kernel/client";
import type { PageMetaV4 } from "../v4-kernel/types-v4";

export type CaptureSourceV4 =
  | "manual"
  | "link"
  | "snippet"
  | "flag"
  | "clipboard";

export type TriageStateV4 = "untriaged" | "accepted" | "rejected" | "archived";

export interface CaptureItemV4 {
  id: string;
  raw: string;
  source: CaptureSourceV4;
  state: TriageStateV4;
  tags: string[];
  confidence: number;
  created_at: string;
  content_hash: string;
}

export interface InboxFilters {
  state: string;
  source: string;
  tag: string;
  query: string;
}

export interface InboxListData {
  items: CaptureItemV4[];
  total: number;
  page: number;
  page_size: number;
  next_cursor: string;
  etag: string;
  not_modified?: boolean;
  filters: InboxFilters;
}

export interface CaptureMutationData {
  capture: CaptureItemV4;
  created?: boolean;
  duplicate?: boolean;
  from_state?: string;
  to_state?: string;
}

export interface InboxPage {
  data: InboxListData;
  meta: PageMetaV4;
}

export interface InboxListOptions {
  page?: number;
  pageSize?: number;
  state?: TriageStateV4;
  source?: CaptureSourceV4;
  tag?: string;
  query?: string;
  cursor?: string;
  etag?: string;
  signal?: AbortSignal;
}

export const CAPTURE_SOURCES: readonly CaptureSourceV4[] = [
  "manual",
  "link",
  "snippet",
  "flag",
  "clipboard",
];

export const TRIAGE_STATES: readonly TriageStateV4[] = [
  "untriaged",
  "accepted",
  "rejected",
  "archived",
];

export const QUICK_TAGS: readonly string[] = ["ctf", "todo", "web", "flag"];

export class InboxClient {
  constructor(private readonly client: V4Client = new V4Client()) {}

  async list(options: InboxListOptions = {}): Promise<InboxPage> {
    const params = new URLSearchParams();
    if (options.state) params.set("state", options.state);
    if (options.source) params.set("source", options.source);
    if (options.tag) params.set("tag", options.tag);
    if (options.query) params.set("query", options.query);
    if (options.cursor) params.set("cursor", options.cursor);
    const query = params.toString();
    const result = await this.client.get<InboxListData>(
      query ? `/inbox?${query}` : "/inbox",
      {
        page: options.page,
        pageSize: options.pageSize,
        etag: options.etag,
        signal: options.signal,
      },
    );
    const data = result.data;
    if (!data || !Array.isArray(data.items)) {
      throw new V4ApiError(
        "invalid_response",
        "inbox list payload is malformed",
      );
    }
    return { data, meta: result.meta };
  }

  async capture(
    raw: string,
    source?: CaptureSourceV4,
    tags: readonly string[] = [],
  ): Promise<CaptureMutationData> {
    if (!raw.trim()) {
      throw new V4ApiError("invalid_input", "raw must not be empty", ["raw"]);
    }
    if (source !== undefined && !CAPTURE_SOURCES.includes(source)) {
      throw new V4ApiError("invalid_input", "unknown capture source", [
        "source",
      ]);
    }
    const result = await this.client.post<CaptureMutationData>(
      "/inbox/capture",
      {
        raw,
        source,
        tags: [...tags],
      },
    );
    if (!result?.capture) {
      throw new V4ApiError("invalid_response", "capture payload is malformed");
    }
    return result;
  }

  async triage(
    itemId: string,
    target: TriageStateV4,
  ): Promise<CaptureMutationData> {
    if (!itemId.trim()) {
      throw new V4ApiError("invalid_input", "id must not be empty", ["id"]);
    }
    if (!TRIAGE_STATES.includes(target)) {
      throw new V4ApiError("invalid_input", "unknown triage state", ["state"]);
    }
    const result = await this.client.patch<CaptureMutationData>(
      "/inbox/triage",
      {
        id: itemId,
        state: target,
      },
    );
    if (!result?.capture) {
      throw new V4ApiError("invalid_response", "triage payload is malformed");
    }
    return result;
  }

  async triageByAction(
    itemId: string,
    action: "accept" | "reject" | "archive" | "reset",
  ): Promise<CaptureMutationData> {
    const result = await this.client.patch<CaptureMutationData>(
      "/inbox/triage",
      {
        id: itemId,
        action,
      },
    );
    if (!result?.capture) {
      throw new V4ApiError("invalid_response", "triage payload is malformed");
    }
    return result;
  }
}

export const inboxClient = new InboxClient();
