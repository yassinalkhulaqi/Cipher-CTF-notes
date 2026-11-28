import assert from "node:assert/strict";
import test from "node:test";

import { V4Client } from "../src/features/v4-kernel/client";
import type { V4Envelope } from "../src/features/v4-kernel/types-v4";
import {
  VaultClient,
  VaultClientError,
  describeVaultError,
} from "../src/features/security-vault/client";
import {
  VAULT_TABS,
  canSeal,
  initialVaultState,
  noticeCounts,
  postureTone,
  privacyLabel,
  summarizeVault,
  vaultReducer,
  versionLabel,
} from "../src/features/security-vault/state";
import type { VaultStatus } from "../src/features/security-vault/types";

const STATUS: VaultStatus = {
  algorithm: "sha256-stream+hmac-sha256",
  envelope_version: 1,
  key_id: "01234567-89ab-cdef-0123-456789abcdef",
  key_state: "active",
  key_version: 2,
  fingerprint: "abcdef123456",
  open_count: 0,
  posture: {
    level: "strong",
    score: 100,
    checks: ["active-key", "recovery-available"],
  },
  privacy_mode: "redacted",
  recovery_remaining: 3,
  seal_count: 0,
  seal_status: "ready",
};

function envelope<T>(data: T): V4Envelope<T> {
  return {
    data,
    meta: {
      request_id: "req-test",
      version: "v4",
      page: 1,
      page_size: 50,
    },
  };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: async () => payload,
  } as Response;
}

function recordingClient(
  payload: unknown,
  calls: Array<{ url: string; method: string; body: string | undefined }>,
  status = 200,
): V4Client {
  const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: String(input),
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? init.body : undefined,
    });
    return jsonResponse(payload, status);
  }) as typeof fetch;
  return new V4Client("/api/v4", fetchImpl);
}

test("initial vault state has no secrets and predictable defaults", () => {
  const state = initialVaultState();
  assert.deepEqual(state.status, null);
  assert.equal(state.envelope, null);
  assert.equal(state.recoveryCodes.length, 0);
  assert.equal(state.activeTab, "posture");
  assert.equal(state.busy, false);
  assert.equal(canSeal(state), false);
  assert.equal(versionLabel(state), "No key");
  assert.equal(summarizeVault(state), "Vault status unavailable");
  assert.deepEqual(VAULT_TABS, ["posture", "keys", "recovery", "privacy"]);
  assert.equal(initialVaultState(STATUS).status, STATUS);
});

test("reducer loads status and handles busy and failure transitions", () => {
  let state = initialVaultState();
  state = vaultReducer(state, { type: "loading", action: "seal" });
  assert.equal(state.busy, true);
  assert.equal(state.lastAction, "seal");
  state = vaultReducer(state, { type: "failed", message: "mac mismatch" });
  assert.equal(state.busy, false);
  assert.equal(state.error, "mac mismatch");
  assert.equal(state.notices[0].tone, "bad");
  state = vaultReducer(state, { type: "cleared-error" });
  assert.equal(state.error, "");
  state = vaultReducer(state, { type: "loaded", status: STATUS });
  assert.equal(state.status, STATUS);
  assert.equal(canSeal(state), true);
});

test("reducer counts seals and opens without storing plaintext", () => {
  const envelope = {
    version: 1,
    key_id: STATUS.key_id,
    nonce: "aa",
    ciphertext_hex: "bbcc",
    mac_hex: "dd",
    aad: "note",
  };
  let state = initialVaultState(STATUS);
  state = vaultReducer(state, { type: "sealed", envelope });
  assert.equal(state.envelope, envelope);
  assert.equal(state.status?.seal_count, 1);
  state = vaultReducer(state, { type: "opened", plaintext: "hello" });
  assert.equal(state.opened, "hello");
  assert.equal(state.status?.open_count, 1);
  state = vaultReducer(state, { type: "clear-secrets" });
  assert.equal(state.opened, "");
  assert.equal(state.envelope, null);
});

test("key change invalidates local envelopes and plaintext", () => {
  let state = initialVaultState(STATUS);
  state = vaultReducer(state, {
    type: "sealed",
    envelope: {
      version: 1,
      key_id: STATUS.key_id,
      nonce: "aa",
      ciphertext_hex: "bb",
      mac_hex: "cc",
      aad: "",
    },
  });
  const rotated: VaultStatus = { ...STATUS, key_version: 3 };
  state = vaultReducer(state, {
    type: "key-changed",
    status: rotated,
    notice: "Key rotated",
  });
  assert.equal(state.envelope, null);
  assert.equal(state.opened, "");
  assert.equal(state.status?.key_version, 3);
  assert.equal(state.notices.at(-1)?.message, "Key rotated");
});

test("reducer handles privacy, recovery, redaction and tabs", () => {
  let state = initialVaultState(STATUS);
  state = vaultReducer(state, { type: "privacy", mode: "locked" });
  assert.equal(state.status?.privacy_mode, "locked");
  assert.equal(privacyLabel("locked"), "Content locked");
  state = vaultReducer(state, {
    type: "recovery",
    codes: ["RS-AAAA-BBBB"],
    remaining: 1,
  });
  assert.deepEqual(state.recoveryCodes, ["RS-AAAA-BBBB"]);
  assert.equal(state.status?.recovery_remaining, 1);
  state = vaultReducer(state, { type: "recovery-consumed", remaining: 0 });
  assert.equal(state.status?.recovery_remaining, 0);
  state = vaultReducer(state, {
    type: "redacted",
    result: { data: { token: "[hidden]" }, paths: ["token"], mode: "redacted" },
  });
  assert.deepEqual(state.redaction?.paths, ["token"]);
  state = vaultReducer(state, { type: "tab", tab: "recovery" });
  assert.equal(state.activeTab, "recovery");
  assert.deepEqual(noticeCounts(state).good, 1);
});

test("notices are capped and dismissable", () => {
  let state = initialVaultState();
  for (let index = 0; index < 9; index += 1) {
    state = vaultReducer(state, {
      type: "notice",
      tone: "info",
      message: `notice ${index}`,
    });
  }
  assert.equal(state.notices.length, 6);
  assert.equal(state.notices[0].message, "notice 3");
  const id = state.notices[0].id;
  state = vaultReducer(state, { type: "dismiss-notice", id });
  assert.equal(state.notices.length, 5);
  assert.equal(state.noticeSequence, 9);
});

test("selectors describe posture and vault summary", () => {
  assert.equal(postureTone("strong"), "good");
  assert.equal(postureTone("fair"), "warn");
  assert.equal(postureTone("weak"), "bad");
  assert.equal(postureTone("unknown"), "bad");
  assert.equal(privacyLabel("normal"), "Normal view");
  assert.equal(privacyLabel("redacted"), "Fields redacted");
  const state = initialVaultState(STATUS);
  assert.equal(versionLabel(state), "v2 active");
  assert.equal(
    summarizeVault(state),
    "seal=ready | key=v2 active | privacy=redacted | recovery=3",
  );
  assert.deepEqual(noticeCounts(state), { info: 0, good: 0, warn: 0, bad: 0 });
});

test("client reads a v4 status envelope", async () => {
  const calls: Array<{
    url: string;
    method: string;
    body: string | undefined;
  }> = [];
  const client = new VaultClient(recordingClient(envelope(STATUS), calls));
  const status = await client.status();
  assert.equal(status.key_version, 2);
  assert.equal(calls[0].method, "GET");
  assert.ok(calls[0].url.includes("/api/v4/vault"));
});

test("client posts vault actions with the expected bodies", async () => {
  const calls: Array<{
    url: string;
    method: string;
    body: string | undefined;
  }> = [];
  const client = new VaultClient(
    recordingClient(
      envelope({
        envelope: {
          version: 1,
          key_id: STATUS.key_id,
          nonce: "aa",
          ciphertext_hex: "bb",
          mac_hex: "cc",
          aad: "ctx",
        },
        size: 4,
      }),
      calls,
    ),
  );
  const sealed = await client.seal("data", "ctx");
  assert.equal(sealed.size, 4);
  assert.equal(sealed.envelope.aad, "ctx");
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(JSON.parse(calls[0].body ?? "{}"), {
    action: "seal",
    plaintext: "data",
    aad: "ctx",
  });

  await client.rotate("new valid passphrase");
  assert.equal(JSON.parse(calls[1].body ?? "{}").action, "rotate");
  await client.setPrivacy("locked");
  assert.equal(JSON.parse(calls[2].body ?? "{}").mode, "locked");
});

test("client maps v4 errors to vault client errors", async () => {
  const calls: Array<{
    url: string;
    method: string;
    body: string | undefined;
  }> = [];
  const client = new VaultClient(
    recordingClient(
      {
        error: {
          code: "forbidden",
          message: "missing capability: encrypt",
          details: ["encrypt"],
        },
      },
      calls,
      403,
    ),
  );
  await assert.rejects(
    () => client.status(),
    (error: unknown) =>
      error instanceof VaultClientError &&
      error.code === "forbidden" &&
      error.details[0] === "encrypt",
  );
  assert.equal(
    describeVaultError(
      new VaultClientError("conflict", "already used", ["code"]),
    ),
    "already used (code)",
  );
  assert.equal(describeVaultError(new Error("boom")), "boom");
  assert.equal(describeVaultError(42), "Unexpected vault error");
});

test("client recovery and redaction helpers", async () => {
  const calls: Array<{
    url: string;
    method: string;
    body: string | undefined;
  }> = [];
  const client = new VaultClient(
    recordingClient(
      envelope({
        codes: ["RS-AAAA-BBBB"],
        records: [],
      }),
      calls,
    ),
  );
  const result = await client.generateRecovery(1);
  assert.deepEqual(result.codes, ["RS-AAAA-BBBB"]);
  assert.equal(JSON.parse(calls[0].body ?? "{}").count, 1);

  await client.consumeRecovery("RS-AAAA-BBBB");
  assert.equal(JSON.parse(calls[1].body ?? "{}").action, "recovery_consume");

  await client.redact(
    { token: "abc" },
    [{ field: "token", replacement: "[x]" }],
    "redacted",
  );
  const redactBody = JSON.parse(calls[2].body ?? "{}");
  assert.equal(redactBody.action, "redact");
  assert.deepEqual(redactBody.rules, [{ field: "token", replacement: "[x]" }]);
});
