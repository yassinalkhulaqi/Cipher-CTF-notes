import { ApiClientError, type V2Client } from "../../lib/apiClient";
import { filtersToQueryFragment } from "./filters";
import {
  asArray,
  asBoolean,
  asNumber,
  asRecord,
  asString,
  normalizeCommandSuggestions,
  normalizeFacets,
  normalizeParsedCommand,
  normalizeSaved,
  normalizeSearchResponse,
} from "./normalizers";
import type {
  CommandArgumentSuggestion,
  CommandCompletion,
  FacetCount,
  ParsedCommand,
  SavedQuery,
  SavedQueryDraft,
  SearchErrorShape,
  SearchRequestOptions,
  SearchResponse,
  SearchSnippet,
} from "./types";

export type SearchApiClient = Pick<V2Client, "call">;

export interface SearchCallOptions {
  signal?: AbortSignal;
  requestId?: string;
}

export interface SearchStatus {
  documents: number;
  terms: number;
  postings: number;
  generation: number;
  updated_at: string;
  rebuilds: number;
  synced: boolean;
  saved_queries: number;
  commands: number;
  synonyms: number;
  last_update: Record<string, unknown>;
}

export interface SearchSuggestions {
  query: string;
  suggestions: string[];
  commands: CommandArgumentSuggestion[];
  saved: SavedQuery[];
}

export class SearchServiceError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly requestId: string | null;

  constructor(error: SearchErrorShape & { requestId?: string | null }) {
    super(error.message);
    this.name = "SearchServiceError";
    this.code = error.code;
    this.retryable = error.retryable ?? false;
    this.requestId = error.requestId ?? null;
  }
}

export function normalizeSearchError(error: unknown): SearchServiceError {
  if (error instanceof SearchServiceError) return error;
  if (error instanceof ApiClientError) {
    return new SearchServiceError({
      code: error.code ?? "api_error",
      message: error.message,
      retryable: error.retryable,
      requestId: error.requestId,
    });
  }
  return new SearchServiceError({
    code: "network_error",
    message:
      error instanceof Error
        ? error.message
        : typeof error === "string"
          ? error
          : "Search request failed",
    retryable: true,
  });
}

export function searchRequestBody(
  options: SearchRequestOptions,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    query: options.query,
  };
  if (options.limit !== undefined) body.limit = options.limit;
  if (options.cursor) body.cursor = options.cursor;
  if (options.sort) body.sort = options.sort;
  if (options.groupBy) body.group_by = options.groupBy;
  if (options.facetField) body.facet_field = options.facetField;
  if (options.width !== undefined) body.width = options.width;
  const fragment = filtersToQueryFragment(options.filters ?? []);
  if (fragment) body.query = `${options.query} ${fragment}`.trim();
  return body;
}

export function draftRequestBody(
  draft: SavedQueryDraft,
): Record<string, unknown> {
  return {
    name: draft.name,
    query: draft.query,
    description: draft.description,
    tags: draft.tags,
    pinned: draft.pinned,
  };
}

export class SearchService {
  private readonly client: SearchApiClient;

  constructor(client: SearchApiClient) {
    this.client = client;
  }

  private async call<T>(
    route: string,
    body: Record<string, unknown>,
    options: SearchCallOptions = {},
  ): Promise<T> {
    try {
      return await this.client.call<T>(route, body, {
        signal: options.signal,
        requestId: options.requestId,
      });
    } catch (error) {
      throw normalizeSearchError(error);
    }
  }

  async search(
    options: SearchRequestOptions,
    callOptions: SearchCallOptions = {},
  ): Promise<SearchResponse> {
    const data = await this.call<unknown>(
      "search.query",
      searchRequestBody(options),
      callOptions,
    );
    return normalizeSearchResponse(data);
  }

  async suggest(
    text: string,
    signal?: AbortSignal,
  ): Promise<SearchSuggestions> {
    const data = asRecord(
      await this.call<unknown>("search.suggest", { query: text }, { signal }),
    );
    return {
      query: asString(data.query, text),
      suggestions: asArray(data.suggestions).map((item) => asString(item)),
      commands: normalizeCommandSuggestions(data.commands),
      saved: asArray(data.saved).map(normalizeSaved),
    };
  }

  async facets(
    field: string,
    _text = "",
    signal?: AbortSignal,
  ): Promise<FacetCount[]> {
    const data = asRecord(
      await this.call<unknown>("search.facets", { field }, { signal }),
    );
    return normalizeFacets(data.facets);
  }

  async snippet(
    nodeId: number,
    text: string,
    width = 300,
  ): Promise<SearchSnippet> {
    const data = asRecord(
      await this.call<unknown>("search.snippet", {
        id: nodeId,
        query: text,
        width,
      }),
    );
    return {
      text: asString(data.text),
      highlights: asArray(data.highlights).map((item) => {
        const highlight = asRecord(item);
        return {
          start: asNumber(highlight.start),
          end: asNumber(highlight.end),
          term: asString(highlight.term),
          kind: asString(highlight.kind, "term"),
        };
      }),
      chunks: asArray(data.chunks).map((item) => {
        const chunk = asRecord(item);
        return { text: asString(chunk.text), match: asBoolean(chunk.match) };
      }),
      fragments: asNumber(data.fragments, 1),
      matched: asBoolean(data.matched),
    };
  }

  async terms(signal?: AbortSignal): Promise<string[]> {
    const data = asRecord(
      await this.call<unknown>("search.terms", {}, { signal }),
    );
    return asArray(data.terms).map((item) => asString(item));
  }

  async status(signal?: AbortSignal): Promise<SearchStatus> {
    const data = asRecord(
      await this.call<unknown>("search.status", {}, { signal }),
    );
    return {
      documents: asNumber(data.documents),
      terms: asNumber(data.terms),
      postings: asNumber(data.postings),
      generation: asNumber(data.generation),
      updated_at: asString(data.updated_at),
      rebuilds: asNumber(data.rebuilds),
      synced: asBoolean(data.synced),
      saved_queries: asNumber(data.saved_queries),
      commands: asNumber(data.commands),
      synonyms: asNumber(data.synonyms),
      last_update: asRecord(data.last_update),
    };
  }

  async reindex(): Promise<Record<string, unknown>> {
    return asRecord(await this.call<unknown>("search.reindex", {}));
  }

  async describe(): Promise<Record<string, unknown>> {
    return asRecord(await this.call<unknown>("search.describe", {}));
  }

  async listSaved(): Promise<SavedQuery[]> {
    const data = asRecord(await this.call<unknown>("saved.list", {}));
    return asArray(data.items).map(normalizeSaved);
  }

  async getSaved(id: string): Promise<SavedQuery> {
    return normalizeSaved(await this.call<unknown>("saved.get", { id }));
  }

  async createSaved(draft: SavedQueryDraft): Promise<SavedQuery> {
    return normalizeSaved(
      await this.call<unknown>("saved.create", draftRequestBody(draft)),
    );
  }

  async updateSaved(draft: SavedQueryDraft): Promise<SavedQuery> {
    return normalizeSaved(
      await this.call<unknown>("saved.update", draftRequestBody(draft)),
    );
  }

  async deleteSaved(id: string): Promise<boolean> {
    const data = asRecord(await this.call<unknown>("saved.delete", { id }));
    return asBoolean(data.removed, true);
  }

  async useSaved(id: string): Promise<SavedQuery> {
    const data = asRecord(await this.call<unknown>("saved.use", { id }));
    return normalizeSaved(data.saved);
  }

  async parseCommand(text: string): Promise<ParsedCommand> {
    return normalizeParsedCommand(
      await this.call<unknown>("commands.parse", { text }),
    );
  }

  async suggestCommand(
    text: string,
    limit = 8,
  ): Promise<CommandArgumentSuggestion[]> {
    const data = asRecord(
      await this.call<unknown>("commands.suggest", { text, limit }),
    );
    return normalizeCommandSuggestions(data.suggestions);
  }

  async completeCommand(text: string): Promise<CommandCompletion> {
    const data = asRecord(
      await this.call<unknown>("commands.complete", { text }),
    );
    return {
      text: asString(data.text, text),
      cursor: asNumber(data.cursor, text.length),
      prefix: asString(data.prefix),
      context: asString(
        data.context,
        "command",
      ) as CommandCompletion["context"],
      suggestions: normalizeCommandSuggestions(data.suggestions),
    };
  }

  async listCommands(): Promise<Array<Record<string, unknown>>> {
    const data = asRecord(await this.call<unknown>("commands.list", {}));
    return asArray(data.commands).map(asRecord);
  }

  async commandHelp(name: string): Promise<Record<string, unknown>> {
    return asRecord(await this.call<unknown>("commands.help", { text: name }));
  }

  async runCommand(text: string): Promise<Record<string, unknown>> {
    return asRecord(await this.call<unknown>("commands.run", { text }));
  }
}

export function createSearchService(client: SearchApiClient): SearchService {
  return new SearchService(client);
}
