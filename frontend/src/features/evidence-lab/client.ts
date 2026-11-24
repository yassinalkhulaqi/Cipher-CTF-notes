/** Typed API client for the evidence-lab namespace. */

import { V3Client } from "../../v3/apiClient";
import type { V3ClientOptions } from "../../v3/apiClient";
import { bytesToBase64 } from "./format";
import type {
  BundleDiffData,
  BundleEntryData,
  CustodyGraphData,
  EntropyReportData,
  EvidenceReportData,
  FileClassData,
  HexWindowData,
  IngestRecordData,
  LabManifest,
  RangeChunkData,
  StringScanData,
} from "./types";

export interface EvidenceLabClientOptions extends V3ClientOptions {
  namespace?: string;
}

export interface InspectOptions {
  filename?: string;
  expectedSha256?: string;
  expectedBlake2b?: string;
  expectedSize?: number;
  hexStart?: number;
  hexLength?: number;
  bytesPerRow?: number;
  minStringLength?: number;
  encoding?: string;
}

export interface HashResult {
  panel: EvidenceReportData["panel"];
  badge: EvidenceReportData["badge"];
}

export class EvidenceLabClient {
  private readonly client: V3Client;
  private readonly namespace: string;

  constructor(options: EvidenceLabClientOptions = {}) {
    const { namespace = "evidence", ...rest } = options;
    this.client = new V3Client(rest);
    this.namespace = namespace;
  }

  async manifest(): Promise<LabManifest> {
    return this.client.data<LabManifest>(this.namespace, "manifest");
  }

  async inspect(
    ref: string,
    data: Uint8Array,
    options: InspectOptions = {},
  ): Promise<EvidenceReportData> {
    return this.client.data<EvidenceReportData>(this.namespace, "inspect", {
      ref,
      data: bytesToBase64(data),
      filename: options.filename ?? "",
      expected_sha256: options.expectedSha256 ?? "",
      expected_blake2b: options.expectedBlake2b ?? "",
      expected_size: options.expectedSize ?? null,
      hex_start: options.hexStart ?? 0,
      hex_length: options.hexLength ?? 512,
      bytes_per_row: options.bytesPerRow ?? 16,
      min_string_length: options.minStringLength ?? 4,
      encoding: options.encoding ?? "ascii",
    });
  }

  async hex(
    ref: string,
    data: Uint8Array,
    start: number,
    length: number,
    bytesPerRow = 16,
  ): Promise<HexWindowData> {
    return this.client.data<HexWindowData>(this.namespace, "hex", {
      ref,
      data: bytesToBase64(data),
      start,
      length,
      bytes_per_row: bytesPerRow,
    });
  }

  async strings(
    ref: string,
    data: Uint8Array,
    minLength = 4,
    encoding = "ascii",
  ): Promise<StringScanData> {
    return this.client.data<StringScanData>(this.namespace, "strings", {
      ref,
      data: bytesToBase64(data),
      min_length: minLength,
      encoding,
    });
  }

  async entropy(ref: string, data: Uint8Array): Promise<EntropyReportData> {
    return this.client.data<EntropyReportData>(this.namespace, "entropy", {
      ref,
      data: bytesToBase64(data),
    });
  }

  async classify(ref: string, data: Uint8Array): Promise<FileClassData> {
    return this.client.data<FileClassData>(this.namespace, "classify", {
      ref,
      data: bytesToBase64(data),
    });
  }

  async hashes(ref: string, data: Uint8Array): Promise<HashResult> {
    return this.client.data<HashResult>(this.namespace, "hashes", {
      ref,
      data: bytesToBase64(data),
    });
  }

  async ranges(
    ref: string,
    data: Uint8Array,
    range: string,
  ): Promise<{ chunks: RangeChunkData[]; total_size: number }> {
    return this.client.data(this.namespace, "ranges", {
      ref,
      data: bytesToBase64(data),
      range,
    });
  }

  async register(
    ref: string,
    filename: string,
    data: Uint8Array,
  ): Promise<IngestRecordData> {
    return this.client.data<IngestRecordData>(this.namespace, "register", {
      ref,
      filename,
      data: bytesToBase64(data),
    });
  }

  async custody(
    root: string,
    steps: Array<Record<string, unknown>>,
  ): Promise<CustodyGraphData> {
    return this.client.data<CustodyGraphData>(this.namespace, "custody", {
      root,
      steps,
    });
  }

  async custodyGraph(root: string): Promise<CustodyGraphData> {
    return this.client.data<CustodyGraphData>(this.namespace, "custody_graph", {
      root,
    });
  }

  async compare(
    left: BundleEntryData[],
    right: BundleEntryData[],
  ): Promise<BundleDiffData> {
    return this.client.data<BundleDiffData>(this.namespace, "compare", {
      left,
      right,
    });
  }
}
