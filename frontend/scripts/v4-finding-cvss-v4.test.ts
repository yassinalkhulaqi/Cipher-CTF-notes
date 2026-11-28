import assert from "node:assert/strict";
import test from "node:test";

import {
  FindingClient,
  V4ApiError,
} from "../src/features/finding-cvss-v4/client";
import type { FindingV4 } from "../src/features/finding-cvss-v4/client";
import { V4Client } from "../src/features/v4-kernel/client";
import {
  DEFAULT_METRICS,
  LIFECYCLE_STATES,
  LEGAL_TRANSITIONS_V4,
  METRIC_CODES,
  METRIC_DEFINITIONS,
  estimateScore,
  formatVector,
  initialFindingStudioState,
  legalTransitions,
  parseVectorText,
  reduceFindingStudio,
  scorePercent,
  selectedFinding,
  severityFromScore,
  severityTone,
} from "../src/features/finding-cvss-v4/state";
import type { MetricValues } from "../src/features/finding-cvss-v4/state";

const STRONG: MetricValues = {
  ...DEFAULT_METRICS,
  VC: "H",
  VI: "H",
  VA: "H",
};

function finding(overrides: Partial<FindingV4> = {}): FindingV4 {
  return {
    id: "finding-a",
    title: "Stored XSS",
    description: "comments",
    vector: formatVector(STRONG),
    severity: "critical",
    lifecycle_state: "draft",
    remediation_due: null,
    remediation_notes: "",
    retest_count: 0,
    created_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

function fakeFetch(
  handler: (
    url: string,
    init: RequestInit,
  ) => { status: number; body: unknown },
): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const result = handler(String(input), init ?? {});
    return {
      status: result.status,
      ok: result.status >= 200 && result.status < 300,
      json: async () => result.body,
    } as Response;
  }) as typeof fetch;
}

test("metric definitions cover every canonical metric", () => {
  assert.equal(METRIC_CODES.length, 15);
  assert.deepEqual(
    METRIC_DEFINITIONS.map((definition) => definition.code),
    METRIC_CODES,
  );
  for (const definition of METRIC_DEFINITIONS) {
    assert.ok(definition.options.length >= 2);
    for (const option of definition.options) {
      assert.ok(option.weight >= 0 && option.weight <= 1.5);
      assert.ok(option.label.length > 0);
    }
  }
});

test("default vector formats and parses back", () => {
  const text = formatVector(DEFAULT_METRICS);
  assert.ok(text.startsWith("CVSS:4.0/AV:N/AC:L"));
  assert.deepEqual(parseVectorText(text), DEFAULT_METRICS);
  assert.deepEqual(parseVectorText(formatVector(STRONG)), STRONG);
});

test("parse vector text is order independent", () => {
  const shuffled =
    "CVSS:4.0/SA:N/AV:N/CR:X/VI:H/AC:L/AT:N/PR:N/UI:N/VC:H/VA:H/SC:N/SI:N";
  assert.deepEqual(parseVectorText(shuffled), STRONG);
});

test("parse vector text rejects malformed input", () => {
  assert.throws(
    () => parseVectorText("CVSS:3.1/AV:N"),
    /must start with CVSS:4.0/,
  );
  assert.throws(
    () => parseVectorText(formatVector(STRONG) + "/AV:L"),
    /duplicate metric: AV/,
  );
  assert.throws(
    () => parseVectorText("CVSS:4.0/AV:N/AC:L"),
    /missing base metrics/,
  );
  assert.throws(
    () => parseVectorText("CVSS:4.0/ZZ:N"),
    /invalid metric component/,
  );
});

test("estimate score matches known vectors", () => {
  assert.equal(estimateScore(DEFAULT_METRICS), 0);
  assert.equal(estimateScore(STRONG), 9.8);
  assert.equal(estimateScore({ ...STRONG, AV: "P" }), 6.8);
  assert.equal(estimateScore({ ...STRONG, SC: "H", SI: "H", SA: "H" }), 10);
  assert.equal(estimateScore({ ...STRONG, E: "U" }), 8.3);
  assert.equal(estimateScore({ ...STRONG, CR: "L" }), 9.5);
});

test("severity bands and tones", () => {
  assert.equal(severityFromScore(0), "none");
  assert.equal(severityFromScore(3.9), "low");
  assert.equal(severityFromScore(4), "medium");
  assert.equal(severityFromScore(7), "high");
  assert.equal(severityFromScore(9), "critical");
  assert.equal(severityTone("none"), "var(--v4-text-faint)");
  assert.equal(severityTone("low"), "var(--v4-info)");
  assert.equal(severityTone("medium"), "var(--v4-warning)");
  assert.equal(severityTone("high"), "var(--v4-accent)");
  assert.equal(severityTone("critical"), "var(--v4-danger)");
});

test("score percent clamps to the gauge range", () => {
  assert.equal(scorePercent(0), 0);
  assert.equal(scorePercent(7.5), 75);
  assert.equal(scorePercent(10), 100);
  assert.equal(scorePercent(99), 100);
  assert.equal(scorePercent(-2), 0);
});

test("lifecycle transition table covers every state", () => {
  assert.equal(LIFECYCLE_STATES.length, 7);
  assert.deepEqual(
    Object.keys(LEGAL_TRANSITIONS_V4).sort(),
    [...LIFECYCLE_STATES].sort(),
  );
  for (const state of LIFECYCLE_STATES) {
    const targets = legalTransitions(state);
    assert.ok(targets.length > 0);
    assert.ok(!targets.includes(state));
  }
  assert.deepEqual(legalTransitions("draft"), ["open"]);
  assert.deepEqual(legalTransitions("remediating"), ["retest", "open"]);
  assert.deepEqual(legalTransitions("retest"), ["closed", "remediating"]);
});

test("reducer edits metrics and clears the stored score", () => {
  const initial = initialFindingStudioState();
  assert.equal(initial.metrics.AV, "N");
  assert.equal(initial.score, null);
  const updated = reduceFindingStudio(initial, {
    type: "set-metric",
    code: "AV",
    value: "P",
  });
  assert.equal(updated.metrics.AV, "P");
  assert.equal(updated.metrics.VC, "N");
  assert.notEqual(updated.metrics, initial.metrics);
});

test("reducer loads, selects and applies findings", () => {
  let state = initialFindingStudioState();
  state = reduceFindingStudio(state, {
    type: "load-findings",
    findings: [finding(), finding({ id: "finding-b", title: "Second" })],
  });
  assert.equal(state.selectedId, "finding-a");
  assert.equal(selectedFinding(state)?.title, "Stored XSS");

  state = reduceFindingStudio(state, { type: "select", id: "finding-b" });
  assert.equal(state.title, "Second");
  assert.equal(state.selectedId, "finding-b");

  const changed = finding({ id: "finding-b", lifecycle_state: "closed" });
  state = reduceFindingStudio(state, {
    type: "apply-finding",
    finding: changed,
  });
  assert.equal(selectedFinding(state)?.lifecycle_state, "closed");
  assert.equal(state.findings.length, 2);

  state = reduceFindingStudio(state, {
    type: "apply-finding",
    finding: finding({ id: "finding-c" }),
  });
  assert.equal(state.findings.length, 3);
});

test("reducer updates remediation and retest fields", () => {
  let state = initialFindingStudioState();
  state = reduceFindingStudio(state, { type: "set-due", value: "2026-12-31" });
  state = reduceFindingStudio(state, { type: "set-notes", value: "patch" });
  state = reduceFindingStudio(state, {
    type: "set-retest-note",
    value: "verified",
  });
  state = reduceFindingStudio(state, { type: "set-verdict", value: "pass" });
  state = reduceFindingStudio(state, { type: "set-busy", value: true });
  state = reduceFindingStudio(state, { type: "set-error", value: "oops" });
  assert.equal(state.remediationDue, "2026-12-31");
  assert.equal(state.remediationNotes, "patch");
  assert.equal(state.retestNote, "verified");
  assert.equal(state.verdict, "pass");
  assert.equal(state.busy, true);
  assert.equal(state.error, "oops");
});

test("reducer caps the activity log and resets", () => {
  let state = initialFindingStudioState();
  for (let index = 0; index < 30; index += 1) {
    state = reduceFindingStudio(state, {
      type: "log",
      message: `entry ${index}`,
    });
  }
  assert.equal(state.log.length, 20);
  assert.equal(state.log[0], "entry 10");
  state = reduceFindingStudio(state, { type: "reset" });
  assert.deepEqual(state, initialFindingStudioState());
});

test("client lists findings with filters and decodes the envelope", async () => {
  const client = new FindingClient(
    new V4Client(
      "/api/v4",
      fakeFetch((url) => ({
        status: 200,
        body: {
          data: {
            items: [finding()],
            total: 1,
            page: 2,
            page_size: 50,
            next_cursor: "",
            etag: "etag-1",
          },
          meta: {
            request_id: "r1",
            version: "v4",
            page: 2,
            page_size: 50,
            etag: "etag-1",
          },
        },
      })),
    ),
  );
  const page = await client.list({ severity: "critical", page: 2 });
  assert.equal(page.data.items[0].title, "Stored XSS");
  assert.equal(page.meta.version, "v4");
});

test("client sends the expected verbs and bodies", async () => {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const client = new FindingClient(
    new V4Client(
      "/api/v4",
      fakeFetch((url, init) => {
        calls.push({ url, init });
        return {
          status: 200,
          body: {
            data: {
              finding: finding(),
              score: {
                vector: finding().vector,
                base: 9.8,
                threat: 9.8,
                environmental: 9.8,
                final: 9.8,
                severity: "critical",
                nomenclature: "CVSS:B",
              },
            },
            meta: {
              request_id: "r",
              version: "v4",
              page: 1,
              page_size: 50,
            },
          },
        };
      }),
    ),
  );
  await client.create({ title: "New", vector: formatVector(STRONG) });
  await client.transition("finding-a", "open");
  await client.assignRemediation("finding-a", "2026-12-01", "notes");
  await client.retest("finding-a", "pass", "done");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[1].init.method, "PUT");
  assert.ok(String(calls[1].init.body).includes("transition"));
  assert.ok(String(calls[2].init.body).includes("remediation"));
  assert.ok(String(calls[3].init.body).includes("retest"));
});

test("client throws a structured API error", async () => {
  const client = new FindingClient(
    new V4Client(
      "/api/v4",
      fakeFetch(() => ({
        status: 403,
        body: {
          error: {
            code: "forbidden",
            message: "no write",
            details: ["cvss_v4"],
          },
        },
      })),
    ),
  );
  await assert.rejects(
    () => client.create({ title: "Nope", vector: formatVector(STRONG) }),
    (error: unknown) =>
      error instanceof V4ApiError &&
      error.code === "forbidden" &&
      error.details[0] === "cvss_v4",
  );
});
