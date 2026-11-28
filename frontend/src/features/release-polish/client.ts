/** Typed V3 client wrapper for release routes. */

import { V3Client } from "../../v3/apiClient";
import type { V3ClientOptions } from "../../v3/apiClient";
import { RELEASE_ROUTES } from "./config";
import type {
  AnimationAudit,
  EmptyStateSpec,
  IconLabel,
  OnboardingStep,
  PolishCheck,
  ReleaseManifestData,
  ShowcaseEntry,
} from "./types";

export interface GoldenEnvelope {
  ok: boolean;
  scenarios: Array<{ name: string; ok: boolean; phases: string[] }>;
}

export interface SmokeEnvelope {
  ok: boolean;
  total: number;
  passed: number;
  failed: number;
  checks: Array<{ id: string; title: string; passed: boolean }>;
}

export interface GateEnvelope {
  ok: boolean;
  gates: Array<{ id: string; status: string; title: string }>;
}

export interface DocsEnvelope {
  sections: Array<{ id: string; title: string; body: string }>;
  rendered?: string;
}

export interface ReleaseEnvelope {
  version: string;
  released_on: string;
  entries: Array<{
    version: string;
    category: string;
    title: string;
    detail: string;
  }>;
  rendered: string;
}

export interface MigrationEnvelope {
  notes: Array<{ from: string; to: string; title: string; automated: boolean }>;
  rendered: string;
}

export interface OnboardingEnvelope {
  steps: OnboardingStep[];
  required: number;
  empty_states: EmptyStateSpec[];
}

export interface ShowcaseEnvelope {
  entries: ShowcaseEntry[];
  icons: IconLabel[];
  kind_colors: Record<string, string>;
  kind_labels: Record<string, string>;
}

export interface PolishEnvelope {
  checks: PolishCheck[];
  animations: AnimationAudit[];
  icons: IconLabel[];
  breakpoints: Array<{ name: string; width: number }>;
}

export interface ReleasePolishClientOptions extends V3ClientOptions {}

export class ReleasePolishClient {
  private readonly client: V3Client;

  constructor(options: ReleasePolishClientOptions = {}) {
    this.client = new V3Client(options);
  }

  async manifest(): Promise<ReleaseManifestData> {
    return this.client.data<ReleaseManifestData>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.manifest,
    );
  }

  async golden(name?: string): Promise<GoldenEnvelope> {
    return this.client.data<GoldenEnvelope>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.golden,
      {
        name: name ?? "",
      },
    );
  }

  async smoke(): Promise<SmokeEnvelope> {
    return this.client.data<SmokeEnvelope>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.smoke,
    );
  }

  async gates(): Promise<GateEnvelope> {
    return this.client.data<GateEnvelope>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.gates,
    );
  }

  async docs(rendered = false): Promise<DocsEnvelope> {
    return this.client.data<DocsEnvelope>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.docs,
      { rendered },
    );
  }

  async changelog(): Promise<ReleaseEnvelope> {
    return this.client.data<ReleaseEnvelope>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.changelog,
    );
  }

  async migrationNotes(): Promise<MigrationEnvelope> {
    return this.client.data<MigrationEnvelope>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.migrationNotes,
    );
  }

  async readiness(
    gatesEvaluated = false,
  ): Promise<{ ready: boolean; verdict: string }> {
    return this.client.data<{ ready: boolean; verdict: string }>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.readiness,
      { gates_evaluated: gatesEvaluated },
    );
  }

  async onboarding(): Promise<OnboardingEnvelope> {
    return this.client.data<OnboardingEnvelope>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.onboarding,
    );
  }

  async showcase(): Promise<ShowcaseEnvelope> {
    return this.client.data<ShowcaseEnvelope>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.showcase,
    );
  }

  async polish(): Promise<PolishEnvelope> {
    return this.client.data<PolishEnvelope>(
      RELEASE_NAMESPACE_NAME,
      RELEASE_ROUTES.polish,
    );
  }
}

const RELEASE_NAMESPACE_NAME = "release";
