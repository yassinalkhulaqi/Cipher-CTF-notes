/** Typed API client for the v4 evidence-lab namespace. */

import { V4Client } from "../../v4-kernel/client";
import type { V4RequestOptions } from "../../v4-kernel/client";
import type { PageMetaV4 } from "../../v4-kernel/types-v4";
import type {
  CustodyDataV4,
  EvidenceCreateDataV4,
  EvidenceCreateInputV4,
  EvidenceListDataV4,
  EvidenceRecordV4,
  InspectionResultV4,
  ManifestDataV4,
} from "./types";

const BASE_URL = "/api/v4";

export type EvidenceInspectionOptions = V4RequestOptions;

export function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

export function hexToBytes(text: string): Uint8Array {
  const normalized = text.replace(/\s+/g, "").toLowerCase();
  if (normalized.length % 2 !== 0) {
    throw new Error("hex input must have an even number of digits");
  }
  const output = new Uint8Array(normalized.length / 2);
  for (let index = 0; index < output.length; index += 1) {
    const byte = Number.parseInt(
      normalized.slice(index * 2, index * 2 + 2),
      16,
    );
    if (Number.isNaN(byte)) {
      throw new Error("hex input contains a non-hexadecimal digit");
    }
    output[index] = byte;
  }
  return output;
}

export class EvidenceLabClientV4 {
  private readonly client: V4Client;

  constructor(client: V4Client = new V4Client(BASE_URL)) {
    this.client = client;
  }

  async list(
    options: V4RequestOptions = {},
  ): Promise<{ data: EvidenceListDataV4; meta: PageMetaV4 }> {
    return this.client.get<EvidenceListDataV4>("/evidence", options);
  }

  async get(id: string): Promise<EvidenceRecordV4> {
    const { data } = await this.client.get<EvidenceRecordV4>(
      `/evidence/${encodeURIComponent(id)}`,
    );
    return data;
  }

  async create(input: EvidenceCreateInputV4): Promise<EvidenceCreateDataV4> {
    return this.client.post<EvidenceCreateDataV4>("/evidence", input);
  }

  async inspect(
    id: string,
    options: EvidenceInspectionOptions = {},
  ): Promise<InspectionResultV4> {
    const { data } = await this.client.get<InspectionResultV4>(
      `/evidence/${encodeURIComponent(id)}/inspect`,
      options,
    );
    return data;
  }

  async custody(id: string): Promise<CustodyDataV4> {
    const { data } = await this.client.get<CustodyDataV4>(
      `/evidence/${encodeURIComponent(id)}/custody`,
    );
    return data;
  }

  async manifest(): Promise<ManifestDataV4> {
    const { data } =
      await this.client.get<ManifestDataV4>("/evidence-manifest");
    return data;
  }
}

export const evidenceLabClientV4 = new EvidenceLabClientV4();
