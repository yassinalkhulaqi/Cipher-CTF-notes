export type QueryValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | ReadonlyArray<string | number | boolean>;

export interface PageMeta {
  next_cursor?: string | null;
  nextCursor?: string | null;
  has_more?: boolean;
  hasMore?: boolean;
  total?: number;
  limit?: number;
  [key: string]: unknown;
}

export interface V2ErrorBody {
  code?: string;
  message?: string;
  details?: unknown;
  retryable?: boolean;
}

export type V2Error = string | V2ErrorBody;

export interface V2Response<T> {
  ok: boolean;
  data?: T;
  error?: V2Error | null;
  request_id?: string | null;
  requestId?: string | null;
  meta?: PageMeta | null;
  retryable?: boolean;
}

export interface ApiClientErrorOptions {
  status?: number;
  code?: string;
  requestId?: string | null;
  retryable?: boolean;
  cause?: unknown;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly retryable: boolean;

  constructor(message: string, options: ApiClientErrorOptions | number = {}) {
    super(message);
    this.name = "ApiClientError";
    if (typeof options === "number") {
      this.status = options;
      this.code = options > 0 ? `http_${options}` : "network_error";
      this.requestId = null;
      this.retryable = false;
      return;
    }
    this.status = options.status ?? 0;
    this.code = options.code ?? "unknown_error";
    this.requestId = options.requestId ?? null;
    this.retryable = options.retryable === true;
    if (options.cause !== undefined) {
      this.cause = options.cause;
    }
  }
}

export interface CallOptions {
  method?: string;
  timeout?: number;
  idempotencyKey?: string;
  /** Force a single retry even for non-GET-style calls. */
  retry?: boolean;
  /** Mark the call safe to retry without changing state. */
  idempotent?: boolean;
  retryDelay?: number;
  headers?: Record<string, string>;
  query?: Record<string, QueryValue>;
  signal?: AbortSignal;
  requestId?: string;
  /** Internal: return `{ data, meta, envelope }` instead of unwrapped data. */
  raw?: boolean;
}

export interface V2ClientOptions {
  basePath?: string;
  timeout?: number;
  fetch?: typeof globalThis.fetch;
  requestId?: () => string;
}

export interface PaginateOptions extends CallOptions {
  limit?: number;
  maxPages?: number;
  cursor?: string | null;
}

const DEFAULT_BASE_PATH = "/api/v2";
const DEFAULT_TIMEOUT = 10_000;
const DEFAULT_MAX_PAGES = 50;
const READ_ROUTE = /^(get|list|read|load|find|fetch|search)(_|$)/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function stringField(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

function randomToken(): string {
  const cryptoApi =
    typeof globalThis !== "undefined" ? globalThis.crypto : undefined;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Generate a correlation id suitable for `X-Request-ID`. */
export function requestId(prefix = "req"): string {
  return `${prefix}_${randomToken()}`;
}

/** True for browser and Node abort errors alike. */
export function isAbortError(error: unknown): boolean {
  if (!isRecord(error)) return false;
  return (
    error.name === "AbortError" ||
    error.code === "ABORT_ERR" ||
    error.code === 20
  );
}

/** Append a query object to a path, skipping null/undefined values. */
export function withQuery(
  path: string,
  query?: Record<string, QueryValue>,
): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) continue;
    if (Array.isArray(value)) {
      value.forEach((item) => params.append(key, String(item)));
    } else {
      params.append(key, String(value));
    }
  }
  const encoded = params.toString();
  if (!encoded) return path;
  return `${path}${path.includes("?") ? "&" : "?"}${encoded}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function readPayload(response: Response): Promise<unknown> {
  const text = (response as { text?: unknown }).text;
  if (typeof text === "function") {
    try {
      const raw = await (text as () => Promise<string>).call(response);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }
  const json = (response as { json?: unknown }).json;
  if (typeof json === "function") {
    try {
      return await (json as () => Promise<unknown>).call(response);
    } catch {
      return null;
    }
  }
  return null;
}

function responseHeader(response: Response, name: string): string | null {
  const headers = (
    response as { headers?: { get?: (key: string) => string | null } }
  ).headers;
  return headers && typeof headers.get === "function"
    ? headers.get(name)
    : null;
}

interface ParsedError {
  message: string;
  code: string;
  retryable: boolean;
}

function parseErrorPayload(payload: unknown, status: number): ParsedError {
  if (isRecord(payload)) {
    const error = payload.error;
    if (isRecord(error)) {
      return {
        message:
          stringField(error.message) ??
          stringField(payload.message) ??
          `Request failed (${status})`,
        code:
          stringField(error.code) ??
          stringField(payload.code) ??
          `http_${status}`,
        retryable: error.retryable === true || payload.retryable === true,
      };
    }
    if (typeof error === "string" && error) {
      return {
        message: error,
        code: stringField(payload.code) ?? `http_${status}`,
        retryable: payload.retryable === true,
      };
    }
    return {
      message: stringField(payload.message) ?? `Request failed (${status})`,
      code: stringField(payload.code) ?? `http_${status}`,
      retryable: payload.retryable === true,
    };
  }
  if (typeof payload === "string" && payload) {
    return {
      message: payload,
      code: `http_${status}`,
      retryable: false,
    };
  }
  return {
    message: `Request failed (${status})`,
    code: `http_${status}`,
    retryable: false,
  };
}

function readPageItems<T>(source: unknown): T[] {
  if (Array.isArray(source)) return source as T[];
  if (!isRecord(source)) return [];
  const candidates = [
    source.items,
    source.data,
    source.results,
    source.records,
  ];
  const rawItems = candidates.find((candidate) => Array.isArray(candidate));
  return Array.isArray(rawItems) ? (rawItems as T[]) : [];
}

function extractPage<T>(
  source: unknown,
  extraMeta: unknown[] = [],
): {
  items: T[];
  nextCursor: string | null;
  hasMore: boolean | null;
} {
  const metaSources = [
    ...extraMeta,
    isRecord(source) ? source.meta : null,
    isRecord(source) ? source.page : null,
    isRecord(source) ? source : null,
  ];

  let rawCursor: unknown = null;
  let rawHasMore: unknown;
  for (const meta of metaSources) {
    if (!isRecord(meta)) continue;
    if (rawCursor === null) {
      rawCursor = meta.next_cursor ?? meta.nextCursor ?? meta.cursor ?? null;
    }
    if (rawHasMore === undefined) {
      rawHasMore = meta.has_more ?? meta.hasMore;
    }
  }

  return {
    items: readPageItems<T>(source),
    nextCursor: typeof rawCursor === "string" && rawCursor ? rawCursor : null,
    hasMore: typeof rawHasMore === "boolean" ? rawHasMore : null,
  };
}

function readPage<T>(page: unknown): {
  items: T[];
  nextCursor: string | null;
  hasMore: boolean | null;
} {
  if (isRecord(page) && "envelope" in page && "data" in page) {
    const envelope = isRecord(page.envelope) ? page.envelope : null;
    return extractPage<T>(page.data, [page.meta, envelope]);
  }
  return extractPage<T>(page);
}

export class V2Client {
  readonly basePath: string;
  readonly timeout: number;
  private readonly fetchImpl: typeof globalThis.fetch;
  private readonly makeRequestId: () => string;

  constructor(options: V2ClientOptions = {}) {
    this.basePath = (options.basePath ?? DEFAULT_BASE_PATH).replace(/\/+$/, "");
    this.timeout = options.timeout ?? DEFAULT_TIMEOUT;
    this.fetchImpl =
      options.fetch ?? ((input, init) => globalThis.fetch(input, init));
    this.makeRequestId = options.requestId ?? (() => requestId());
  }

  private endpoint(route: string, query?: Record<string, QueryValue>): string {
    const suffix = route.replace(/^\/+/, "");
    const base = suffix ? `${this.basePath}/${suffix}` : this.basePath;
    return withQuery(base, query);
  }

  private async execute<T>(
    url: string,
    method: string,
    body: Record<string, unknown>,
    options: CallOptions,
    correlationId: string,
    retryableRequest: boolean,
  ): Promise<T> {
    const timeout = options.timeout ?? this.timeout;
    const controller = new AbortController();
    let timedOut = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let onExternalAbort: (() => void) | null = null;

    if (timeout > 0) {
      timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeout);
    }

    if (options.signal) {
      if (options.signal.aborted) {
        controller.abort();
      } else {
        onExternalAbort = () => controller.abort();
        options.signal.addEventListener("abort", onExternalAbort);
      }
    }

    try {
      const headers: Record<string, string> = {
        Accept: "application/json",
        "X-Request-ID": correlationId,
        ...options.headers,
      };
      if (options.idempotencyKey) {
        headers["Idempotency-Key"] = options.idempotencyKey;
      }

      const init: RequestInit = {
        method,
        headers,
        signal: controller.signal,
      };
      if (method !== "GET" && method !== "HEAD") {
        headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(body);
      }

      const response = await this.fetchImpl(url, init);
      const payload = await readPayload(response);
      const status = typeof response.status === "number" ? response.status : 0;
      const ok =
        typeof response.ok === "boolean"
          ? response.ok
          : status >= 200 && status < 300;

      const record = isRecord(payload) ? payload : null;
      const responseRequestId =
        stringField(record?.request_id) ??
        stringField(record?.requestId) ??
        responseHeader(response, "x-request-id") ??
        correlationId;

      if (!ok || record?.ok === false) {
        const parsed = parseErrorPayload(payload, status);
        const retryableStatus =
          status === 408 || status === 425 || status === 429 || status >= 500;
        throw new ApiClientError(parsed.message, {
          status,
          code: parsed.code,
          requestId: responseRequestId,
          retryable: parsed.retryable || retryableStatus,
        });
      }

      const data = record && "data" in record ? record.data : (payload as T);
      if (options.raw) {
        return {
          data,
          meta: record && isRecord(record.meta) ? record.meta : null,
          envelope: record,
        } as T;
      }
      return data as T;
    } catch (error) {
      if (error instanceof ApiClientError) throw error;

      if (isAbortError(error) || controller.signal.aborted) {
        if (timedOut) {
          throw new ApiClientError(`Request timed out after ${timeout}ms`, {
            status: 0,
            code: "timeout",
            requestId: correlationId,
            retryable: retryableRequest,
          });
        }
        throw new ApiClientError("Request aborted", {
          status: 0,
          code: "aborted",
          requestId: correlationId,
          retryable: false,
        });
      }

      throw new ApiClientError(
        error instanceof Error ? error.message : "Network request failed",
        {
          status: 0,
          code: "network_error",
          requestId: correlationId,
          retryable: true,
          cause: error,
        },
      );
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      if (options.signal && onExternalAbort) {
        options.signal.removeEventListener("abort", onExternalAbort);
      }
    }
  }

  async call<T>(
    route: string,
    body: Record<string, unknown> = {},
    options: CallOptions = {},
  ): Promise<T> {
    const method = (options.method ?? "POST").toUpperCase();
    const correlationId = options.requestId ?? this.makeRequestId();
    const retryableRequest =
      options.retry === true ||
      options.idempotent === true ||
      method === "GET" ||
      method === "HEAD" ||
      READ_ROUTE.test(route);
    const url = this.endpoint(route, options.query);

    let attempt = 0;
    for (;;) {
      try {
        return await this.execute<T>(
          url,
          method,
          body,
          options,
          correlationId,
          retryableRequest,
        );
      } catch (error) {
        const apiError =
          error instanceof ApiClientError
            ? error
            : new ApiClientError(
                error instanceof Error
                  ? error.message
                  : "Network request failed",
                {
                  requestId: correlationId,
                  code: "network_error",
                  retryable: true,
                  cause: error,
                },
              );

        if (attempt === 0 && retryableRequest && apiError.retryable) {
          attempt += 1;
          const delay = options.retryDelay ?? 0;
          if (delay > 0) await sleep(delay);
          continue;
        }
        throw apiError;
      }
    }
  }

  async *paginate<T>(
    route: string,
    body: Record<string, unknown> = {},
    options: PaginateOptions = {},
  ): AsyncGenerator<T, void, unknown> {
    const {
      limit,
      maxPages = DEFAULT_MAX_PAGES,
      cursor: initialCursor = null,
      ...callOptions
    } = options;
    const pageLimit = Math.max(0, Math.floor(maxPages));
    if (pageLimit === 0) return;

    let cursor: string | null = initialCursor;
    for (let pageIndex = 0; pageIndex < pageLimit; pageIndex += 1) {
      const pageBody: Record<string, unknown> = { ...body };
      if (limit !== undefined) pageBody.limit = limit;
      if (cursor) pageBody.cursor = cursor;

      const page = await this.call<unknown>(route, pageBody, {
        ...callOptions,
        raw: true,
      });
      const parsed = readPage<T>(page);
      for (const item of parsed.items) yield item;

      if (parsed.hasMore === false) return;
      if (!parsed.nextCursor) return;
      if (parsed.nextCursor === cursor) return;
      cursor = parsed.nextCursor;
    }
  }
}
