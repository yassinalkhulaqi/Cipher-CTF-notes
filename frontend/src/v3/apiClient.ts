/** Typed client for the V3 envelope API. */

import type {
  CapabilityMap,
  Envelope,
  ErrorEnvelope,
  PageMeta,
  ResponseMeta,
} from "./types";

export interface V3ClientOptions {
  basePath?: string;
  fetch?: typeof globalThis.fetch;
  requestId?: () => string;
  defaultHeaders?: Record<string, string>;
}

export class ApiClientError extends Error {
  readonly code: string;
  readonly status: number;
  readonly field: string;
  readonly retryable: boolean;
  readonly meta: ResponseMeta | null;

  constructor(error: ErrorEnvelope, status: number) {
    super(error.error.message);
    this.name = "ApiClientError";
    this.code = error.error.code;
    this.status = status;
    this.field = error.error.field;
    this.retryable = error.error.retryable;
    this.meta = error.meta;
  }
}

function defaultRequestId(): string {
  const bytes = new Uint8Array(12);
  if (typeof crypto !== "undefined" && crypto.getRandomValues) {
    crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  return `req_${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

export class V3Client {
  private readonly basePath: string;
  private readonly fetchImpl: typeof globalThis.fetch;
  private readonly requestId: () => string;
  private readonly defaultHeaders: Record<string, string>;

  constructor(options: V3ClientOptions = {}) {
    this.basePath = (options.basePath ?? "/api/v3").replace(/\/+$/, "");
    this.fetchImpl = options.fetch ?? globalThis.fetch.bind(globalThis);
    this.requestId = options.requestId ?? defaultRequestId;
    this.defaultHeaders = { ...(options.defaultHeaders ?? {}) };
  }

  async call<T>(
    namespace: string,
    action: string,
    body: Record<string, unknown> = {},
    options: { signal?: AbortSignal; etag?: string } = {},
  ): Promise<Envelope<T>> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Request-ID": this.requestId(),
      ...this.defaultHeaders,
    };
    if (options.etag) headers["If-None-Match"] = options.etag;
    const response = await this.fetchImpl(
      `${this.basePath}/${namespace}/${action}`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(body),
        signal: options.signal,
      },
    );
    const payload = (await response.json()) as Envelope<T> | ErrorEnvelope;
    if (!response.ok || "error" in payload) {
      throw new ApiClientError(payload as ErrorEnvelope, response.status);
    }
    return payload as Envelope<T>;
  }

  async data<T>(
    namespace: string,
    action: string,
    body: Record<string, unknown> = {},
  ): Promise<T> {
    return (await this.call<T>(namespace, action, body)).data;
  }

  async list<T>(
    namespace: string,
    action: string,
    body: Record<string, unknown> = {},
  ): Promise<{ items: T[]; page: PageMeta | null; etag: string }> {
    const envelope = await this.call<T[]>(namespace, action, body);
    return {
      items: envelope.data,
      page: envelope.meta.page ?? null,
      etag: envelope.meta.etag ?? "",
    };
  }

  async capabilities(): Promise<CapabilityMap> {
    return this.data<CapabilityMap>("system", "capabilities");
  }
}

export function nextCursor(page: PageMeta | null): string {
  return page && page.has_next ? String(page.page + 1) : "";
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}
