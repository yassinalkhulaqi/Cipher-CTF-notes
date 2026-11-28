"""HTTP-facing v4 vault routes.

The API is a thin, typed adapter over the vault services. Every response is a
v4 envelope, every mutation is gated on the ENCRYPT capability, and every
emitted domain event passes through a strict allowlist before it reaches the
event bus or its outbox. No key material or plaintext recovery code is ever
placed in a response, event, or log record.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from typing import Any

from redscribe.v4.api_v4 import RouteRegistry, register_routes
from redscribe.v4.contracts import (
    ApiError,
    Capability,
    CapabilitySet,
    EntityKind,
    ErrorCode,
    PageMeta,
    fail,
    new_entity_id,
    ok,
)
from redscribe.v4.events import DomainEvent, EventBus, EventKind, default_redactor
from redscribe.v4.vault_security.service import (
    IntegrityError,
    KeyManager,
    PassphraseError,
    RecoveryError,
    RecoveryManager,
    RedactionError,
    Redactor,
    StreamSeal,
    VaultError,
    VaultKeyError,
    score_posture,
)
from redscribe.v4.vault_security.storage import KeyMetadataStore, StorageError
from redscribe.v4.vault_security.types import (
    PrivacyMode,
    RedactionRule,
    SealedEnvelope,
    require_text,
)

ROUTE_PREFIX = "/vault"
ROUTE_NAME = "security-vault"

SAFE_EVENT_KEYS = frozenset(
    {
        "forgotten",
        "fingerprint",
        "key_id",
        "key_version",
        "privacy_mode",
        "previous_version",
        "state",
        "version",
    }
)


class VaultEndpoint:
    """Stateful handler for the ``/vault`` GET and POST surface."""

    def __init__(
        self,
        store: KeyMetadataStore | None = None,
        manager: KeyManager | None = None,
        seal: StreamSeal | None = None,
        recovery: RecoveryManager | None = None,
        redactor: Redactor | None = None,
        capabilities: CapabilitySet | None = None,
        bus: EventBus | None = None,
        id_factory: Callable[[], str] | None = None,
        privacy: PrivacyMode = PrivacyMode.REDACTED,
    ) -> None:
        self.store = store or KeyMetadataStore()
        self.manager = manager or KeyManager(store=self.store)
        self.seal = seal or StreamSeal()
        self.redactor = redactor or Redactor()
        self.capabilities = capabilities or CapabilitySet.full()
        self.bus = bus or EventBus()
        self.id_factory = id_factory or new_entity_id
        self.privacy = privacy
        self._seals = 0
        self._opens = 0
        self.recovery = recovery or RecoveryManager(store=self.store)

    @property
    def actions(self) -> tuple[str, ...]:
        return (
            "initialize",
            "lock",
            "open",
            "privacy",
            "recovery_consume",
            "recovery_generate",
            "redact",
            "rotate",
            "seal",
            "status",
            "unlock",
        )

    def _meta(self) -> PageMeta:
        return PageMeta(request_id=self.id_factory(), version="v4")

    def describe(self) -> dict[str, Any]:
        """Return a secret-free posture summary."""
        active = self.manager.active()
        posture = score_posture(
            active,
            len(self.recovery.remaining()),
            self.privacy,
            self.manager.resident_count(),
        )
        return {
            "algorithm": "sha256-stream+hmac-sha256",
            "envelope_version": 1,
            "key_id": active.id if active else "",
            "key_state": active.state.value if active else "none",
            "key_version": active.version if active else 0,
            "fingerprint": self.manager.fingerprint(active.id) if active else "unavailable",
            "open_count": self._opens,
            "posture": posture.to_dict(),
            "privacy_mode": self.privacy.value,
            "recovery_remaining": len(self.recovery.remaining()),
            "seal_count": self._seals,
            "seal_status": "ready" if active is not None else "uninitialized",
        }

    def handle_get(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Handle ``GET /vault``."""
        del payload
        try:
            self.capabilities.require(Capability.ENCRYPT)
        except ApiError as exc:
            return fail(exc)
        return ok(self.describe(), self._meta())

    def handle_post(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Handle ``POST /vault`` with an ``action`` discriminator."""
        meta = self._meta()
        try:
            self.capabilities.require(Capability.ENCRYPT)
            if not isinstance(payload, Mapping):
                raise ApiError(ErrorCode.INVALID_INPUT, "body must be an object")
            action = str(payload.get("action", ""))
            handler = self._handlers().get(action)
            if handler is None:
                raise ApiError(ErrorCode.INVALID_INPUT, f"unknown action: {action}")
            return ok(handler(payload), meta)
        except (ApiError, VaultError, StorageError, ValueError) as exc:
            return fail(_as_api_error(exc))

    def dispatch(
        self,
        method: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Dispatch by HTTP verb for registration with generic route tables."""
        normalized = method.upper()
        if normalized == "GET":
            try:
                return self.handle_get(payload)
            except ApiError as exc:
                return fail(exc)
        if normalized == "POST":
            return self.handle_post(payload or {})
        return fail(ApiError(ErrorCode.INVALID_INPUT, f"unsupported method: {method}"))

    def _handlers(self) -> dict[str, Callable[[Mapping[str, Any]], dict[str, Any]]]:
        return {
            "initialize": self._action_initialize,
            "lock": self._action_lock,
            "open": self._action_open,
            "privacy": self._action_privacy,
            "recovery_consume": self._action_recovery_consume,
            "recovery_generate": self._action_recovery_generate,
            "redact": self._action_redact,
            "rotate": self._action_rotate,
            "seal": self._action_seal,
            "status": self._action_status,
            "unlock": self._action_unlock,
        }

    # -- action handlers -------------------------------------------------

    def _action_status(self, body: Mapping[str, Any]) -> dict[str, Any]:
        del body
        return self.describe()

    def _action_initialize(self, body: Mapping[str, Any]) -> dict[str, Any]:
        record = self.manager.initialize(self._passphrase(body), self._optional_salt(body))
        self._emit(
            EventKind.VAULT_UNLOCKED,
            {"key_id": record.id, "key_version": record.version, "state": "unlocked"},
        )
        return {"key": record.to_dict()}

    def _action_seal(self, body: Mapping[str, Any]) -> dict[str, Any]:
        key_id = self._resolve_key_id(body)
        plaintext = require_text(body.get("plaintext", ""), "plaintext", allow_empty=True)
        aad = self._aad(body)
        envelope = self.seal.seal_for(
            plaintext.encode("utf-8"), key_id, self.manager.key_for(key_id), aad
        )
        self._seals += 1
        return {"envelope": envelope.to_dict(), "size": envelope.plaintext_size}

    def _action_open(self, body: Mapping[str, Any]) -> dict[str, Any]:
        raw = body.get("envelope")
        if not isinstance(raw, Mapping):
            raise ApiError(ErrorCode.INVALID_INPUT, "envelope must be an object")
        envelope = SealedEnvelope.from_dict(dict(raw))
        aad = self._aad(body)
        key = self.manager.key_for(envelope.key_id)
        plaintext = self.seal.open(envelope, key, aad).decode("utf-8")
        self._opens += 1
        return {
            "aad": envelope.aad,
            "key_id": envelope.key_id,
            "plaintext": plaintext,
        }

    def _action_rotate(self, body: Mapping[str, Any]) -> dict[str, Any]:
        result = self.manager.rotate(self._passphrase(body), self._optional_salt(body))
        self._emit(
            EventKind.KEY_ROTATED,
            {
                "fingerprint": self.manager.fingerprint(result.current.id),
                "key_id": result.current.id,
                "previous_version": result.previous.version,
                "version": result.current.version,
            },
        )
        return result.to_dict()

    def _action_lock(self, body: Mapping[str, Any]) -> dict[str, Any]:
        del body
        forgotten = sum(1 for record in self.manager.list_keys() if self.manager.forget(record.id))
        self._emit(
            EventKind.VAULT_LOCKED,
            {"forgotten": forgotten, "state": "locked"},
        )
        return {"forgotten": forgotten, "state": "locked"}

    def _action_unlock(self, body: Mapping[str, Any]) -> dict[str, Any]:
        key_id = self._resolve_key_id(body)
        passphrase = self._passphrase(body)
        if not self.manager.verify_passphrase(key_id, passphrase):
            raise ApiError(ErrorCode.FORBIDDEN, "passphrase rejected")
        record = self.manager.restore(key_id, passphrase)
        self._emit(
            EventKind.VAULT_UNLOCKED,
            {"key_id": key_id, "key_version": record.version, "state": "unlocked"},
        )
        return {"key_id": key_id, "state": "unlocked", "version": record.version}

    def _action_privacy(self, body: Mapping[str, Any]) -> dict[str, Any]:
        self.privacy = PrivacyMode.parse(str(body.get("mode", self.privacy.value)))
        kind: EventKind | None = None
        if self.privacy is PrivacyMode.LOCKED:
            kind = EventKind.VAULT_LOCKED
        elif self.privacy is PrivacyMode.NORMAL:
            kind = EventKind.VAULT_UNLOCKED
        if kind is not None:
            self._emit(kind, {"privacy_mode": self.privacy.value, "state": kind.value})
        return {"privacy_mode": self.privacy.value}

    def _action_redact(self, body: Mapping[str, Any]) -> dict[str, Any]:
        data = body.get("data")
        if not isinstance(data, Mapping):
            raise ApiError(ErrorCode.INVALID_INPUT, "data must be an object")
        raw_rules = body.get("rules", [])
        if not isinstance(raw_rules, list):
            raise ApiError(ErrorCode.INVALID_INPUT, "rules must be a list")
        rules = [RedactionRule.from_dict(dict(item)) for item in raw_rules]
        mode = PrivacyMode.parse(str(body.get("mode", self.privacy.value)))
        return self.redactor.redact_with_report(data, rules, mode).to_dict()

    def _action_recovery_generate(self, body: Mapping[str, Any]) -> dict[str, Any]:
        raw_count = body.get("count", 6)
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            raise ApiError(ErrorCode.INVALID_INPUT, "count must be an integer")
        return self.recovery.generate(raw_count).to_dict()

    def _action_recovery_consume(self, body: Mapping[str, Any]) -> dict[str, Any]:
        record = self.recovery.consume(str(body.get("code", "")))
        return {
            "id": record.id,
            "remaining": len(self.recovery.remaining()),
            "used": record.used,
        }

    # -- helpers ---------------------------------------------------------

    def _passphrase(self, body: Mapping[str, Any]) -> str:
        return require_text(body.get("passphrase", ""), "passphrase")

    def _aad(self, body: Mapping[str, Any]) -> str:
        return str(body.get("aad", ""))

    def _optional_salt(self, body: Mapping[str, Any]) -> bytes | None:
        raw = body.get("salt_hex")
        if raw is None:
            return None
        try:
            salt = bytes.fromhex(str(raw))
        except ValueError as exc:
            raise ApiError(ErrorCode.INVALID_INPUT, "salt_hex must be hexadecimal") from exc
        return salt

    def _resolve_key_id(self, body: Mapping[str, Any]) -> str:
        raw = body.get("key_id")
        if raw is not None:
            return str(raw)
        active = self.manager.active()
        if active is None:
            raise ApiError(ErrorCode.CONFLICT, "vault has no active key")
        return active.id

    def _emit(self, kind: EventKind, payload: Mapping[str, Any]) -> DomainEvent:
        safe = {name: value for name, value in payload.items() if name in SAFE_EVENT_KEYS}
        sanitized = default_redactor(safe)
        if any(name.casefold() not in SAFE_EVENT_KEYS for name in sanitized):
            raise ApiError(ErrorCode.INTERNAL, "event payload rejected")
        event = DomainEvent(
            kind=kind,
            aggregate_id=str(safe.get("key_id", "vault")),
            aggregate_kind=EntityKind.KEY,
            payload=sanitized,
        )
        self.bus.publish(event)
        return event


def _as_api_error(exc: Exception) -> ApiError:
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, IntegrityError):
        return ApiError(ErrorCode.INVALID_INPUT, "envelope authentication failed")
    if isinstance(exc, (RecoveryError, VaultKeyError)):
        return ApiError(ErrorCode.CONFLICT, str(exc))
    if isinstance(exc, (PassphraseError, RedactionError, StorageError, VaultError, ValueError)):
        return ApiError(ErrorCode.INVALID_INPUT, str(exc))
    return ApiError(ErrorCode.INTERNAL, "vault request failed")


_DEFAULT: VaultEndpoint | None = None


def default_endpoint() -> VaultEndpoint:
    """Return the lazily created process-wide endpoint."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = VaultEndpoint()
    return _DEFAULT


def register_vault_route(
    registry: RouteRegistry, endpoint: VaultEndpoint | None = None
) -> VaultEndpoint:
    """Register the vault GET/POST dispatcher on a v4 route registry."""
    handler = endpoint or default_endpoint()
    registry.register(ROUTE_PREFIX, ROUTE_NAME, handler.dispatch)
    return handler


def register(api: Any) -> None:
    """Register with a route registry, mapping, or opaque API object.

    The hook is intentionally conservative: objects that expose neither a
    ``register`` method nor a mutable mapping are left untouched, which keeps
    namespace discovery safe for lightweight test doubles.
    """
    handler = default_endpoint().dispatch
    registrar = getattr(api, "register", None)
    if callable(registrar):
        registrar(ROUTE_PREFIX, ROUTE_NAME, handler)
        return
    if isinstance(api, MutableMapping):
        api[f"/api/v4{ROUTE_PREFIX}"] = handler


def register_global(endpoint: VaultEndpoint | None = None) -> VaultEndpoint:
    """Register the vault on the process-wide v4 registry."""
    handler = endpoint or default_endpoint()
    register_routes(ROUTE_PREFIX, ROUTE_NAME, handler.dispatch)
    return handler


__all__ = [
    "ROUTE_NAME",
    "ROUTE_PREFIX",
    "SAFE_EVENT_KEYS",
    "VaultEndpoint",
    "default_endpoint",
    "register",
    "register_global",
    "register_vault_route",
]
