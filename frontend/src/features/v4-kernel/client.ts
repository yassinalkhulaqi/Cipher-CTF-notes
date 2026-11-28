import type { PageMetaV4, V4Envelope, V4Error } from "./types-v4";

const API_PREFIX = "/api/v4";

export class V4ApiError extends Error {
  readonly code: string;
  readonly details: string[];

  constructor(code: string, message: string, details: string[] = []) {
    super(message);
    this.name = "V4ApiError";
    this.code = code;
    this.details = details;
  }
}

function newRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `req-${Date.now().toString(16)}-${Math.floor(Math.random() * 1e6).toString(16)}`;
}

export interface V4RequestOptions {
  page?: number;
  pageSize?: number;
  etag?: string;
  signal?: AbortSignal;
}

export class V4Client {
  constructor(
    private readonly baseUrl: string = API_PREFIX,
    private readonly fetchImpl: typeof fetch = fetch,
  ) {}

  private buildUrl(path: string, options: V4RequestOptions): string {
    const url = new URL(`${this.baseUrl}${path}`, "http://localhost");
    if (options.page !== undefined)
      url.searchParams.set("page", String(options.page));
    if (options.pageSize !== undefined)
      url.searchParams.set("page_size", String(options.pageSize));
    return `${url.pathname}${url.search}`;
  }

  private buildHeaders(options: V4RequestOptions): HeadersInit {
    const headers: Record<string, string> = {
      Accept: "application/json",
      "X-Request-ID": newRequestId(),
    };
    if (options.etag) headers["If-None-Match"] = options.etag;
    return headers;
  }

  async get<T>(
    path: string,
    options: V4RequestOptions = {},
  ): Promise<{ data: T; meta: PageMetaV4 }> {
    const response = await this.fetchImpl(this.buildUrl(path, options), {
      method: "GET",
      headers: this.buildHeaders(options),
      signal: options.signal,
    });
    if (response.status === 204) {
      return {
        data: undefined as T,
        meta: {
          request_id: "",
          version: "v4",
          page: options.page ?? 1,
          page_size: options.pageSize ?? 50,
        },
      };
    }
    const payload = (await response.json()) as V4Envelope<T> | V4Error;
    if ("error" in payload) {
      const error = payload.error;
      throw new V4ApiError(error.code, error.message, error.details);
    }
    return { data: payload.data, meta: payload.meta };
  }

  async mutate<T>(
    path: string,
    method: "POST" | "PUT" | "PATCH" | "DELETE",
    body?: unknown,
  ): Promise<T> {
    const headers: Record<string, string> = {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Request-ID": newRequestId(),
    };
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 204) return undefined as T;
    const payload = (await response.json()) as V4Envelope<T> | V4Error;
    if ("error" in payload) {
      const error = payload.error;
      throw new V4ApiError(error.code, error.message, error.details);
    }
    return payload.data;
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.mutate<T>(path, "POST", body);
  }

  async put<T>(path: string, body?: unknown): Promise<T> {
    return this.mutate<T>(path, "PUT", body);
  }

  async patch<T>(path: string, body?: unknown): Promise<T> {
    return this.mutate<T>(path, "PATCH", body);
  }

  async delete<T>(path: string): Promise<T> {
    return this.mutate<T>(path, "DELETE");
  }
}

export const v4Client = new V4Client();
