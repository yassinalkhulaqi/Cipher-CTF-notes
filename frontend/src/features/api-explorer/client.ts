/** Typed client over the B00 V3 client for the in-app explorer. */

import { ApiClientError, V3Client } from "../../v3/apiClient";
import type { Envelope, RouteManifest } from "../../v3/types";
import { guardWrite, requestBody } from "./pure";
import type {
  ExplorerRequest,
  ExplorerResponse,
  ManifestSchemaInfo,
  NegotiationResult,
  PageSummary,
  RouteInfoLite,
  ValidationReport,
} from "./types";

export interface ApiExplorerClientOptions {
  client?: V3Client;
  fetch?: typeof globalThis.fetch;
  requestId?: () => string;
}

function responseFrom(
  envelope: Envelope<unknown>,
  status = 200,
): ExplorerResponse {
  return {
    ok: true,
    status,
    requestId: envelope.meta.request_id,
    etag: envelope.meta.etag ?? "",
    data: envelope.data,
    errorCode: "",
    errorMessage: "",
    warnings: envelope.meta.warnings ?? [],
  };
}

function errorResponse(code: string, message: string): ExplorerResponse {
  return {
    ok: false,
    status: 400,
    requestId: "",
    etag: "",
    data: null,
    errorCode: code,
    errorMessage: message,
    warnings: [],
  };
}

export class ApiExplorerClient {
  private readonly client: V3Client;
  private readonly fetchImpl?: typeof globalThis.fetch;
  private readonly requestId?: () => string;

  constructor(options: ApiExplorerClientOptions = {}) {
    this.fetchImpl = options.fetch;
    this.requestId = options.requestId;
    this.client =
      options.client ??
      new V3Client({
        fetch: options.fetch,
        requestId: options.requestId,
      });
  }

  private clientFor(request: ExplorerRequest): V3Client {
    const headers: Record<string, string> = {};
    if (request.capability.trim())
      headers["X-Capability"] = request.capability.trim();
    if (request.idempotencyKey.trim()) {
      headers["Idempotency-Key"] = request.idempotencyKey.trim();
    }
    if (request.allowWrite) headers["X-Allow-Write"] = "true";
    if (Object.keys(headers).length === 0) return this.client;
    return new V3Client({
      fetch: this.fetchImpl,
      requestId: this.requestId,
      defaultHeaders: headers,
    });
  }

  async call<T = unknown>(request: ExplorerRequest): Promise<ExplorerResponse> {
    const blocked = guardWrite(request);
    if (blocked) return errorResponse("read_only_violation", blocked);
    const body = requestBody(request);
    if (!body.ok) return errorResponse("invalid_json", body.error);
    try {
      const envelope = await this.clientFor(request).call<T>(
        request.namespace.trim(),
        request.action.trim(),
        body.value ?? {},
        { etag: request.etag || undefined },
      );
      return responseFrom(envelope as Envelope<unknown>);
    } catch (error) {
      if (error instanceof ApiClientError) {
        return {
          ok: false,
          status: error.status,
          requestId: error.meta?.request_id ?? "",
          etag: "",
          data: null,
          errorCode: error.code,
          errorMessage: error.message,
          warnings: [],
        };
      }
      return errorResponse(
        "transport_error",
        error instanceof Error ? error.message : "Request failed",
      );
    }
  }

  async routes(): Promise<RouteInfoLite[]> {
    const manifest = await this.client.data<RouteManifest>(
      "system",
      "manifest",
    );
    return manifest.routes.map((route) => ({
      path: route.path,
      methods: route.methods,
      public: route.public,
    }));
  }

  async validate(document: unknown): Promise<ValidationReport> {
    return this.client.data<ValidationReport>("extensions", "validate", {
      manifest: document,
    });
  }

  async schema(): Promise<ManifestSchemaInfo> {
    return this.client.data<ManifestSchemaInfo>("extensions", "schema");
  }

  async example(): Promise<unknown> {
    return this.client.data<unknown>("extensions", "example");
  }

  async negotiate(required: string[]): Promise<NegotiationResult> {
    return this.client.data<NegotiationResult>("extensions", "capabilities", {
      required,
    });
  }

  async page(request: ExplorerRequest, size = 50): Promise<PageSummary> {
    const body = requestBody(request);
    if (!body.ok) throw new Error(body.error);
    const envelope = await this.client.call<{
      items: unknown[];
      next_cursor: string;
    }>(
      request.namespace.trim(),
      request.action.trim(),
      { ...(body.value ?? {}), size },
      { etag: request.etag || undefined },
    );
    const items = Array.isArray(envelope.data)
      ? envelope.data
      : (envelope.data?.items ?? []);
    return {
      items,
      total: envelope.meta.page?.total ?? items.length,
      hasNext: Boolean(envelope.data?.next_cursor),
      cursor: envelope.data?.next_cursor ?? "",
    };
  }

  async safety(): Promise<Record<string, unknown>> {
    return this.client.data<Record<string, unknown>>("extensions", "safety");
  }
}

export function createApiExplorerClient(
  options: ApiExplorerClientOptions = {},
): ApiExplorerClient {
  return new ApiExplorerClient(options);
}
