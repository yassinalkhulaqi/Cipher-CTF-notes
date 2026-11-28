"""API envelope, capability, event-redaction, and registration tests."""

from __future__ import annotations

import json
from collections.abc import Iterator, MutableMapping
from typing import Any

import pytest

from redscribe.v4 import register_all, reset_registration
from redscribe.v4.api_v4 import RouteRegistry
from redscribe.v4.contracts import Capability, CapabilitySet, ErrorCode
from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox
from redscribe.v4.vault_security import api as vault_api_module
from redscribe.v4.vault_security.api import (
    ROUTE_NAME,
    ROUTE_PREFIX,
    SAFE_EVENT_KEYS,
    VaultEndpoint,
    default_endpoint,
    register,
    register_global,
    register_vault_route,
)
from redscribe.v4.vault_security.service import KeyManager, RecoveryManager, StreamSeal
from redscribe.v4.vault_security.storage import KeyMetadataStore
from redscribe.v4.vault_security.types import NONCE_BYTES, PrivacyMode

PASSPHRASE = "correct horse battery staple"
NEW_PASSPHRASE = "another valid passphrase 42"


def fixed_clock() -> str:
    return "2026-05-01T00:00:00.000Z"


def fixed_nonce(size: int) -> bytes:
    return bytes((index + 3) % 256 for index in range(size))


def request_ids() -> Iterator[str]:
    counter = 0
    while True:
        counter += 1
        yield f"req-{counter}"


class FakeApi:
    """Minimal opaque API object used by namespace discovery."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []


class RegisteringApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    def register(self, prefix: str, name: str, handler: Any) -> None:
        self.calls.append((prefix, name, handler))


class DictApi(dict[str, Any]):
    """Mutable-mapping API surface."""


@pytest.fixture
def outbox() -> InMemoryOutbox:
    return InMemoryOutbox()


@pytest.fixture
def bus(outbox: InMemoryOutbox) -> EventBus:
    return EventBus(outbox=outbox)


@pytest.fixture
def endpoint(bus: EventBus) -> VaultEndpoint:
    store = KeyMetadataStore()
    ids = request_ids()
    return VaultEndpoint(
        store=store,
        manager=KeyManager(
            store=store, clock=fixed_clock, nonce_source=fixed_nonce, iterations=1000
        ),
        seal=StreamSeal(nonce_source=fixed_nonce),
        recovery=RecoveryManager(store=store, clock=fixed_clock),
        bus=bus,
        id_factory=lambda: next(ids),
    )


def initialize(endpoint: VaultEndpoint, passphrase: str = PASSPHRASE) -> str:
    response = endpoint.handle_post({"action": "initialize", "passphrase": passphrase})
    assert "data" in response
    return str(response["data"]["key"]["id"])


def test_get_status_envelope(endpoint: VaultEndpoint) -> None:
    response = endpoint.handle_get()
    assert response["meta"]["version"] == "v4"
    assert response["meta"]["request_id"] == "req-1"
    data = response["data"]
    assert data["seal_status"] == "uninitialized"
    assert data["key_version"] == 0
    assert data["key_state"] == "none"
    assert data["posture"]["level"] == "weak"
    assert data["algorithm"] == "sha256-stream+hmac-sha256"
    assert "passphrase" not in json.dumps(response)


def test_capability_is_enforced(endpoint: VaultEndpoint) -> None:
    restricted = VaultEndpoint(capabilities=CapabilitySet(granted=frozenset({Capability.READ})))
    for response in (restricted.handle_get(), restricted.handle_post({"action": "status"})):
        assert "error" in response
        assert response["error"]["code"] == ErrorCode.FORBIDDEN.value
        assert "encrypt" in response["error"]["message"].casefold()


def test_initialize_emits_redacted_unlock(endpoint: VaultEndpoint, outbox: InMemoryOutbox) -> None:
    response = endpoint.handle_post({"action": "initialize", "passphrase": PASSPHRASE})
    assert response["meta"]["request_id"] == "req-1"
    assert response["data"]["key"]["state"] == "active"
    assert PASSPHRASE not in json.dumps(response)
    records = outbox.records(EventKind.VAULT_UNLOCKED)
    assert len(records) == 1
    assert records[0].payload["key_version"] == 1
    assert records[0].payload["state"] == "unlocked"
    assert records[0].payload["key_id"] == response["data"]["key"]["id"]
    assert set(records[0].payload) <= SAFE_EVENT_KEYS


def test_seal_and_open_round_trip_through_api(endpoint: VaultEndpoint) -> None:
    initialize(endpoint)
    sealed = endpoint.handle_post(
        {"action": "seal", "plaintext": "findings payload", "aad": "finding:7"}
    )
    envelope = sealed["data"]["envelope"]
    assert envelope["ciphertext_hex"]
    assert envelope["aad"] == "finding:7"
    assert sealed["data"]["size"] == len("findings payload")
    assert "findings payload" not in json.dumps(sealed)
    opened = endpoint.handle_post({"action": "open", "envelope": envelope, "aad": "finding:7"})
    assert opened["data"]["plaintext"] == "findings payload"
    status = endpoint.handle_get()["data"]
    assert status["seal_count"] == 1
    assert status["open_count"] == 1


def test_open_rejects_wrong_aad_and_tampering(endpoint: VaultEndpoint) -> None:
    initialize(endpoint)
    sealed = endpoint.handle_post({"action": "seal", "plaintext": "data", "aad": "right"})
    envelope = sealed["data"]["envelope"]
    wrong = endpoint.handle_post({"action": "open", "envelope": envelope, "aad": "wrong"})
    assert wrong["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert "authentication failed" in wrong["error"]["message"]
    tampered = dict(envelope)
    tampered["ciphertext_hex"] = "00" if envelope["ciphertext_hex"] != "00" else "ff"
    bad = endpoint.handle_post({"action": "open", "envelope": tampered, "aad": "right"})
    assert "error" in bad
    assert bad["error"]["code"] == ErrorCode.INVALID_INPUT.value


def test_rotate_emits_key_rotated_without_secrets(
    endpoint: VaultEndpoint, outbox: InMemoryOutbox
) -> None:
    key_id = initialize(endpoint)
    sealed = endpoint.handle_post({"action": "seal", "plaintext": "historic"})
    result = endpoint.handle_post({"action": "rotate", "passphrase": NEW_PASSPHRASE})
    assert result["data"]["current"]["version"] == 2
    assert result["data"]["previous"]["state"] == "rotated"
    assert NEW_PASSPHRASE not in json.dumps(result)
    records = outbox.records(EventKind.KEY_ROTATED)
    assert len(records) == 1
    payload = records[0].payload
    assert payload["previous_version"] == 1
    assert payload["version"] == 2
    assert len(payload["fingerprint"]) == 12
    assert set(payload) <= SAFE_EVENT_KEYS
    assert records[0].aggregate_id == result["data"]["current"]["id"]
    reopened = endpoint.handle_post({"action": "open", "envelope": sealed["data"]["envelope"]})
    assert reopened["data"]["plaintext"] == "historic"
    assert endpoint.handle_get()["data"]["key_id"] != key_id


def test_lock_and_unlock_events(endpoint: VaultEndpoint, outbox: InMemoryOutbox) -> None:
    initialize(endpoint)
    locked = endpoint.handle_post({"action": "lock"})
    assert locked["data"] == {"forgotten": 1, "state": "locked"}
    assert len(outbox.records(EventKind.VAULT_LOCKED)) == 1
    blocked = endpoint.handle_post({"action": "seal", "plaintext": "blocked"})
    assert blocked["error"]["code"] == ErrorCode.CONFLICT.value
    denied = endpoint.handle_post({"action": "unlock", "passphrase": "wrong but long enough"})
    assert denied["error"]["code"] == ErrorCode.FORBIDDEN.value
    unlocked = endpoint.handle_post({"action": "unlock", "passphrase": PASSPHRASE})
    assert unlocked["data"]["state"] == "unlocked"
    assert len(outbox.records(EventKind.VAULT_UNLOCKED)) == 2
    assert endpoint.handle_post({"action": "seal", "plaintext": "ok"})["data"]


def test_privacy_mode_switch_emits_events(endpoint: VaultEndpoint, outbox: InMemoryOutbox) -> None:
    redacted = endpoint.handle_post({"action": "privacy", "mode": "redacted"})
    assert redacted["data"]["privacy_mode"] == "redacted"
    assert endpoint.handle_get()["data"]["privacy_mode"] == "redacted"
    locked = endpoint.handle_post({"action": "privacy", "mode": "LOCKED"})
    assert locked["data"]["privacy_mode"] == "locked"
    assert len(outbox.records(EventKind.VAULT_LOCKED)) == 1
    unlocked = endpoint.handle_post({"action": "privacy", "mode": "normal"})
    assert unlocked["data"]["privacy_mode"] == "normal"
    assert len(outbox.records(EventKind.VAULT_UNLOCKED)) == 1
    invalid = endpoint.handle_post({"action": "privacy", "mode": "unknown"})
    assert invalid["error"]["code"] == ErrorCode.INVALID_INPUT.value


def test_redact_action_nested(endpoint: VaultEndpoint) -> None:
    response = endpoint.handle_post(
        {
            "action": "redact",
            "mode": "redacted",
            "data": {"user": {"token": "abc"}, "items": [{"token": "def"}]},
            "rules": [{"field": "user.token", "replacement": "[hidden]"}],
        }
    )
    assert response["data"]["data"]["user"] == {"token": "[hidden]"}
    assert response["data"]["data"]["items"] == [{"token": "def"}]
    assert response["data"]["paths"] == ["user.token"]
    locked = endpoint.handle_post(
        {"action": "redact", "mode": "locked", "data": {"nested": {"a": 1}}}
    )
    assert locked["data"]["data"] == {"nested": {"a": "[locked]"}}


def test_recovery_generate_and_consume(endpoint: VaultEndpoint) -> None:
    generated = endpoint.handle_post({"action": "recovery_generate", "count": 2})
    codes = generated["data"]["codes"]
    assert len(codes) == 2
    assert all(code not in json.dumps(endpoint.handle_get()) for code in codes)
    consumed = endpoint.handle_post({"action": "recovery_consume", "code": codes[0]})
    assert consumed["data"]["used"] is True
    assert consumed["data"]["remaining"] == 1
    assert codes[0] not in json.dumps(consumed)
    replay = endpoint.handle_post({"action": "recovery_consume", "code": codes[0]})
    assert replay["error"]["code"] == ErrorCode.CONFLICT.value
    assert "already used" in replay["error"]["message"]


def test_error_envelopes(endpoint: VaultEndpoint) -> None:
    assert (
        endpoint.handle_post({"action": "unknown"})["error"]["code"]
        == ErrorCode.INVALID_INPUT.value
    )
    assert "action" in endpoint.handle_post({"action": "unknown"})["error"]["message"]
    assert "unknown action" in endpoint.handle_post({})["error"]["message"]
    assert (
        "body must be an object"
        in endpoint.dispatch("POST", ["not", "a", "map"])["error"]["message"]
    )
    assert endpoint.dispatch("PUT")["error"]["code"] == ErrorCode.INVALID_INPUT.value
    assert "unsupported method" in endpoint.dispatch("DELETE")["error"]["message"]
    assert (
        "envelope must be an object"
        in endpoint.handle_post({"action": "open", "envelope": "bad"})["error"]["message"]
    )
    assert (
        "count must be an integer"
        in endpoint.handle_post({"action": "recovery_generate", "count": "two"})["error"]["message"]
    )
    assert (
        "at least 12 characters"
        in endpoint.handle_post({"action": "initialize", "passphrase": "short"})["error"]["message"]
    )
    assert (
        "data must be an object"
        in endpoint.handle_post({"action": "redact", "data": []})["error"]["message"]
    )


def test_outbox_never_contains_passphrases_or_key_bytes(
    endpoint: VaultEndpoint, outbox: InMemoryOutbox
) -> None:
    initialize(endpoint)
    endpoint.handle_post({"action": "rotate", "passphrase": NEW_PASSPHRASE})
    endpoint.handle_post({"action": "lock"})
    endpoint.handle_post({"action": "unlock", "passphrase": NEW_PASSPHRASE})
    endpoint.handle_post({"action": "privacy", "mode": "locked"})
    serialized = json.dumps([record.to_dict() for record in outbox.records()])
    for secret in (PASSPHRASE, NEW_PASSPHRASE):
        assert secret not in serialized
    assert "ciphertext" not in serialized
    assert "mac_hex" not in serialized


def test_dispatch_and_action_catalog(endpoint: VaultEndpoint) -> None:
    assert endpoint.actions == tuple(sorted(endpoint.actions))
    assert len(endpoint.actions) == 11
    assert endpoint.dispatch("GET")["meta"]["version"] == "v4"
    assert "data" in endpoint.dispatch("post", {"action": "status"})
    assert "data" in endpoint.dispatch("POST", {"action": "status"})
    assert endpoint.handle_get({"ignored": True})["meta"]["version"] == "v4"


def test_route_registration(endpoint: VaultEndpoint) -> None:
    registry = RouteRegistry()
    returned = register_vault_route(registry, endpoint)
    assert returned is endpoint
    route = registry.get(f"/api/v4{ROUTE_PREFIX}")
    assert route is not None
    assert route.name == ROUTE_NAME
    assert route.full_path == "/api/v4/vault"
    with pytest.raises(ValueError, match="already registered"):
        register_vault_route(registry, endpoint)


def test_register_hook_variants() -> None:
    opaque = FakeApi()
    register(opaque)
    assert opaque.calls == []
    registrar = RegisteringApi()
    register(registrar)
    assert len(registrar.calls) == 1
    assert registrar.calls[0][0] == ROUTE_PREFIX
    assert callable(registrar.calls[0][2])
    mapping: MutableMapping[str, Any] = DictApi()
    register(mapping)
    assert "/api/v4/vault" in mapping


def test_default_endpoint_and_global_registration() -> None:
    first = default_endpoint()
    assert default_endpoint() is first
    registered = register_global(first)
    assert registered is first


def test_namespace_discovery_registers_vault_security() -> None:
    reset_registration()
    registrar = RegisteringApi()
    names = register_all(registrar)
    try:
        assert "vault_security" in names
        assert any(call[0] == ROUTE_PREFIX for call in registrar.calls)
        assert vault_api_module.ROUTE_PREFIX == ROUTE_PREFIX
    finally:
        reset_registration()


def test_api_module_constants() -> None:
    assert ROUTE_PREFIX == "/vault"
    assert ROUTE_NAME == "security-vault"
    assert "fingerprint" in SAFE_EVENT_KEYS
    assert "passphrase" not in SAFE_EVENT_KEYS
    assert "key_id" in SAFE_EVENT_KEYS
    assert PrivacyMode.parse("locked") is PrivacyMode.LOCKED
    assert NONCE_BYTES == 16
