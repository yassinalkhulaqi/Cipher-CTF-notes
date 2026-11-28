"""Domain services for the v4 security vault.

This module implements a small, dependency-free authenticated stream seal, a
PBKDF2 key lifecycle, single-use recovery credentials, and nested redaction.
It deliberately keeps raw key material in process memory only: the metadata
store receives descriptors and digests, and no service method logs key bytes,
passphrases, or plaintext recovery codes.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from redscribe.v4.contracts import new_entity_id
from redscribe.v4.events import utc_now
from redscribe.v4.vault_security.storage import KeyMetadataStore, StorageError
from redscribe.v4.vault_security.types import (
    DEFAULT_ITERATIONS,
    ENVELOPE_VERSION,
    KEY_BYTES,
    MAC_BYTES,
    MIN_PASSPHRASE_LENGTH,
    NONCE_BYTES,
    SALT_BYTES,
    KeyRecord,
    KeySaltRecord,
    KeyState,
    PrivacyMode,
    RecoveryCode,
    RedactionRule,
    SealedEnvelope,
    require_text,
)

Clock = Callable[[], str]
NonceSource = Callable[[int], bytes]
CodeSource = Callable[[int], list[str]]

MAX_RECOVERY_CODES = 8
STREAM_DOMAIN = b"redscribe-v4-stream-v1"
MAC_DOMAIN = b"redscribe-v4-mac-v1"
AAD_DOMAIN = b"redscribe-v4-aad-v1"
DEFAULT_REPLACEMENT = "[redacted]"
LOCKED_REPLACEMENT = "[locked]"


class VaultError(Exception):
    """Base error for vault domain operations."""


class IntegrityError(VaultError):
    """Raised when a sealed envelope fails authentication."""


class VaultKeyError(VaultError):
    """Raised when a key is unavailable or in an invalid state."""


class PassphraseError(VaultError):
    """Raised when a passphrase is too weak or does not verify."""


class RecoveryError(VaultError):
    """Raised when a recovery code is unknown or already consumed."""


class RedactionError(VaultError):
    """Raised when a redaction specification is invalid."""


def _default_nonce_source(size: int) -> bytes:
    return secrets.token_bytes(size)


def _default_code_source(count: int) -> list[str]:
    return [
        f"RS-{secrets.token_hex(5).upper()}-{secrets.token_hex(5).upper()}" for _ in range(count)
    ]


def _system_clock() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _xor(data: bytes, keystream: bytes) -> bytes:
    return bytes(left ^ right for left, right in zip(data, keystream, strict=True))


class StreamSeal:
    """A stdlib-only authenticated stream cipher.

    A SHA-256 counter keystream provides confidentiality and an HMAC-SHA256 tag
    over the nonce, ciphertext, and length-prefixed associated data provides
    integrity. The construction is deterministic for a given key and nonce,
    which makes it straightforward to test and to reproduce across platforms.
    """

    def __init__(self, nonce_source: NonceSource | None = None) -> None:
        self.nonce_source = nonce_source or _default_nonce_source

    @staticmethod
    def validate_key(key: bytes) -> bytes:
        """Require a correctly sized key without ever echoing its value."""
        if not isinstance(key, bytes):
            raise VaultKeyError("key must be bytes")
        if len(key) != KEY_BYTES:
            raise VaultKeyError(f"key must be exactly {KEY_BYTES} bytes")
        return key

    @classmethod
    def keystream(cls, key: bytes, nonce: bytes, length: int) -> bytes:
        """Derive a domain-separated keystream of the requested length."""
        cls.validate_key(key)
        if len(nonce) != NONCE_BYTES:
            raise VaultKeyError(f"nonce must be exactly {NONCE_BYTES} bytes")
        if length < 0:
            raise VaultKeyError("keystream length must not be negative")
        blocks = (length + MAC_BYTES - 1) // MAC_BYTES
        parts: list[bytes] = []
        for counter in range(blocks):
            material = STREAM_DOMAIN + key + nonce + counter.to_bytes(8, "big")
            parts.append(hashlib.sha256(material).digest())
        return b"".join(parts)[:length]

    @classmethod
    def compute_mac(cls, key: bytes, nonce: bytes, ciphertext: bytes, aad: str) -> str:
        """Compute the authentication tag over all public envelope fields."""
        cls.validate_key(key)
        if not isinstance(aad, str):
            raise VaultKeyError("aad must be a string")
        message = (
            AAD_DOMAIN + len(aad).to_bytes(8, "big") + aad.encode("utf-8") + nonce + ciphertext
        )
        mac_key = hashlib.sha256(MAC_DOMAIN + key).digest()
        return hmac.new(mac_key, message, hashlib.sha256).hexdigest()

    def seal(self, plaintext: bytes, key: bytes, aad: str = "") -> SealedEnvelope:
        """Encrypt and authenticate bytes into a new envelope."""
        if not isinstance(plaintext, bytes):
            raise VaultKeyError("plaintext must be bytes")
        material = self.validate_key(key)
        nonce = self.nonce_source(NONCE_BYTES)
        if len(nonce) != NONCE_BYTES:
            raise VaultKeyError("nonce source returned an invalid nonce")
        ciphertext = _xor(plaintext, self.keystream(material, nonce, len(plaintext)))
        mac = self.compute_mac(material, nonce, ciphertext, aad)
        return SealedEnvelope(
            version=ENVELOPE_VERSION,
            key_id="",
            nonce=nonce.hex(),
            ciphertext_hex=ciphertext.hex(),
            mac_hex=mac,
            aad=aad,
        )

    def seal_for(self, plaintext: bytes, key_id: str, key: bytes, aad: str = "") -> SealedEnvelope:
        """Seal bytes and bind the envelope to a specific key identifier."""
        envelope = self.seal(plaintext, key, aad)
        return replace(envelope, key_id=key_id)

    def open(self, envelope: SealedEnvelope, key: bytes, aad: str = "") -> bytes:
        """Authenticate and decrypt an envelope.

        Any modification to the ciphertext, nonce, or associated data causes a
        constant-time MAC comparison to fail before decryption is attempted.
        """
        if not isinstance(envelope, SealedEnvelope):
            raise IntegrityError("envelope must be a SealedEnvelope")
        if envelope.version != ENVELOPE_VERSION:
            raise IntegrityError(f"unsupported envelope version: {envelope.version}")
        material = self.validate_key(key)
        expected = self.compute_mac(material, envelope.nonce_bytes, envelope.ciphertext, aad)
        if not hmac.compare_digest(expected, envelope.mac_hex):
            raise IntegrityError("mac mismatch")
        return _xor(
            envelope.ciphertext,
            self.keystream(material, envelope.nonce_bytes, envelope.plaintext_size),
        )

    def verify(self, envelope: SealedEnvelope, key: bytes, aad: str = "") -> bool:
        """Return whether an envelope authenticates under the given key."""
        try:
            self.open(envelope, key, aad)
        except (IntegrityError, VaultKeyError):
            return False
        return True

    def rewrap(
        self,
        envelope: SealedEnvelope,
        old_key: bytes,
        new_key: bytes,
        aad: str = "",
    ) -> SealedEnvelope:
        """Open with one key and reseal the same plaintext with another."""
        plaintext = self.open(envelope, old_key, aad)
        return self.seal(plaintext, new_key, aad)

    def seal_json(self, value: Mapping[str, Any], key: bytes, aad: str = "") -> SealedEnvelope:
        """Canonicalize and seal a JSON-serializable mapping."""
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return self.seal(payload.encode("utf-8"), key, aad)

    def open_json(self, envelope: SealedEnvelope, key: bytes, aad: str = "") -> dict[str, Any]:
        """Open a JSON envelope and require the result to be a mapping."""
        payload = self.open(envelope, key, aad).decode("utf-8")
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise IntegrityError("sealed JSON must be an object")
        return value


@dataclass(frozen=True, slots=True)
class RotationResult:
    """The before and after descriptors of a key rotation."""

    previous: KeyRecord
    current: KeyRecord

    def to_dict(self) -> dict[str, Any]:
        return {"previous": self.previous.to_dict(), "current": self.current.to_dict()}


class KeyManager:
    """Derive, rotate, and revoke vault keys while persisting metadata only."""

    def __init__(
        self,
        store: KeyMetadataStore | None = None,
        clock: Clock | None = None,
        nonce_source: NonceSource | None = None,
        iterations: int = DEFAULT_ITERATIONS,
    ) -> None:
        if iterations < 1:
            raise VaultKeyError("iterations must be positive")
        self.store = store or KeyMetadataStore()
        self.clock = clock or utc_now
        self.nonce_source = nonce_source or _default_nonce_source
        self.iterations = iterations
        self._live_keys: dict[str, bytes] = {}
        self._verifiers: dict[str, str] = {}

    @staticmethod
    def validate_passphrase(passphrase: str) -> str:
        text = require_text(passphrase, "passphrase")
        if len(text) < MIN_PASSPHRASE_LENGTH:
            raise PassphraseError(f"passphrase must be at least {MIN_PASSPHRASE_LENGTH} characters")
        return text

    def derive_key(self, passphrase: str, salt: bytes, iterations: int | None = None) -> bytes:
        """Derive a fixed-size key with PBKDF2-HMAC-SHA256."""
        phrase = self.validate_passphrase(passphrase)
        if not isinstance(salt, bytes) or len(salt) != SALT_BYTES:
            raise PassphraseError(f"salt must be exactly {SALT_BYTES} bytes")
        rounds = self.iterations if iterations is None else iterations
        if rounds < 1:
            raise PassphraseError("iterations must be positive")
        return hashlib.pbkdf2_hmac("sha256", phrase.encode("utf-8"), salt, rounds, dklen=KEY_BYTES)

    def initialize(self, passphrase: str, salt: bytes | None = None) -> KeyRecord:
        """Create the first active key from a passphrase."""
        if self.store.active_key() is not None:
            raise VaultKeyError("vault already has an active key")
        material_salt = salt if salt is not None else self.nonce_source(SALT_BYTES)
        if len(material_salt) != SALT_BYTES:
            raise PassphraseError(f"salt must be exactly {SALT_BYTES} bytes")
        key_id = new_entity_id()
        record = KeyRecord(
            id=key_id,
            version=self.store.next_version(),
            state=KeyState.ACTIVE,
            created_at=self.clock(),
        )
        derived = self.derive_key(passphrase, material_salt)
        self.store.put_key(record)
        self.store.put_salt(
            KeySaltRecord(
                key_id=key_id,
                salt_hex=material_salt.hex(),
                iterations=self.iterations,
                created_at=self.clock(),
            )
        )
        self._live_keys[key_id] = derived
        self._verifiers[key_id] = hashlib.sha256(derived).hexdigest()
        return record

    def rotate(self, passphrase: str, salt: bytes | None = None) -> RotationResult:
        """Retire the active key and install the next version."""
        previous = self.store.active_key()
        if previous is None:
            raise VaultKeyError("no active key to rotate")
        retired = KeyRecord(
            id=previous.id,
            version=previous.version,
            state=KeyState.ROTATED,
            created_at=previous.created_at,
            rotated_at=self.clock(),
        )
        self.store.replace_key(retired)
        current = self.initialize(passphrase, salt)
        return RotationResult(previous=retired, current=current)

    def revoke(self, key_id: str) -> KeyRecord:
        """Revoke a retired key and discard its in-memory material."""
        record = self.store.get_key(key_id)
        if record.state is KeyState.ACTIVE:
            raise VaultKeyError("cannot revoke the active key")
        if record.state is KeyState.REVOKED:
            raise VaultKeyError("key is already revoked")
        revoked = KeyRecord(
            id=record.id,
            version=record.version,
            state=KeyState.REVOKED,
            created_at=record.created_at,
            rotated_at=self.clock(),
        )
        self.store.replace_key(revoked)
        self._live_keys.pop(record.id, None)
        self._verifiers.pop(record.id, None)
        return revoked

    def key_for(self, key_id: str) -> bytes:
        """Return in-memory key material for an in-process crypto operation."""
        record = self.store.get_key(key_id)
        if not record.state.can_open:
            raise VaultKeyError(f"key cannot open envelopes: {record.state.value}")
        material = self._live_keys.get(record.id)
        if material is None:
            raise VaultKeyError("key material is not resident in memory")
        return material

    def active(self) -> KeyRecord | None:
        return self.store.active_key()

    def current_key(self) -> bytes:
        """Return the active key material for immediate use."""
        record = self.active()
        if record is None:
            raise VaultKeyError("vault has no active key")
        return self.key_for(record.id)

    def get(self, key_id: str) -> KeyRecord:
        return self.store.get_key(key_id)

    def list_keys(self) -> list[KeyRecord]:
        return self.store.list_keys()

    def version_index(self) -> dict[int, str]:
        return self.store.version_index()

    def fingerprint(self, key_id: str) -> str:
        """Return a short, non-reversible label safe for logs and the UI."""
        material = self._live_keys.get(self.store.get_key(key_id).id)
        if material is None:
            return "unavailable"
        return hashlib.sha256(material).hexdigest()[:12]

    def verify_passphrase(self, key_id: str, passphrase: str) -> bool:
        """Check a passphrase against a stored digest, even while locked."""
        salt_record = self.store.find_salt(key_id)
        verifier = self._verifiers.get(key_id)
        if salt_record is None or verifier is None:
            return False
        candidate = self.derive_key(passphrase, salt_record.salt, salt_record.iterations)
        expected = hashlib.sha256(candidate).hexdigest()
        return hmac.compare_digest(expected, verifier)

    def restore(self, key_id: str, passphrase: str) -> KeyRecord:
        """Rehydrate in-memory key material after a successful verification."""
        if not self.verify_passphrase(key_id, passphrase):
            raise PassphraseError("passphrase rejected")
        salt_record = self.store.find_salt(key_id)
        if salt_record is None:
            raise VaultKeyError("missing KDF parameters")
        self._live_keys[key_id] = self.derive_key(
            passphrase, salt_record.salt, salt_record.iterations
        )
        return self.store.get_key(key_id)

    def forget(self, key_id: str) -> bool:
        """Drop resident material without deleting the verifier digest."""
        return self._live_keys.pop(key_id, None) is not None

    def resident_count(self) -> int:
        return len(self._live_keys)


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    """One-time plaintext codes plus their stored digest records."""

    codes: tuple[str, ...]
    records: tuple[RecoveryCode, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "codes": list(self.codes),
            "records": [record.to_dict() for record in self.records],
        }


class RecoveryManager:
    """Issue, verify, and consume single-use recovery credentials."""

    def __init__(
        self,
        store: KeyMetadataStore | None = None,
        clock: Clock | None = None,
        code_source: CodeSource | None = None,
    ) -> None:
        self.store = store or KeyMetadataStore()
        self.clock = clock or _system_clock
        self.code_source = code_source or _default_code_source

    @staticmethod
    def normalize(code: str) -> str:
        text = require_text(code, "code").replace(" ", "").casefold()
        if len(text) < 8:
            raise RecoveryError("recovery code is too short")
        return text

    @staticmethod
    def digest(code: str) -> str:
        normalized = RecoveryManager.normalize(code)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def generate(self, count: int = 6) -> RecoveryResult:
        """Create new single-use codes; plaintext is returned only once."""
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 1 <= count <= MAX_RECOVERY_CODES
        ):
            raise RecoveryError(f"count must be between 1 and {MAX_RECOVERY_CODES}")
        issued = self.code_source(count)
        if len(issued) != count or len(set(issued)) != count:
            raise RecoveryError("code source must return unique codes")
        records: list[RecoveryCode] = []
        for code in issued:
            record = RecoveryCode(
                id=new_entity_id(),
                code_hash=self.digest(code),
                used=False,
                created_at=self.clock(),
            )
            try:
                self.store.put_recovery(record)
            except StorageError as exc:
                raise RecoveryError(str(exc)) from exc
            records.append(record)
        return RecoveryResult(codes=tuple(issued), records=tuple(records))

    def verify(self, code: str) -> RecoveryCode | None:
        """Return the matching unused record, if any."""
        record = self.store.find_recovery_by_hash(self.digest(code))
        return None if record is None or record.used else record

    def consume(self, code: str) -> RecoveryCode:
        """Mark a recovery code as used exactly once."""
        record = self.store.find_recovery_by_hash(self.digest(code))
        if record is None:
            raise RecoveryError("unknown recovery code")
        if record.used:
            raise RecoveryError("recovery code already used")
        return self.store.mark_recovery_used(record.id)

    def remaining(self) -> list[RecoveryCode]:
        return self.store.remaining_recovery()

    def invalidate_all(self) -> int:
        """Consume every outstanding code, for example after a rotation."""
        count = 0
        for record in self.remaining():
            self.store.mark_recovery_used(record.id)
            count += 1
        return count

    def is_available(self) -> bool:
        return bool(self.remaining())


class PostureLevel(str, Enum):
    """Coarse security posture bands surfaced by the dashboard."""

    STRONG = "strong"
    FAIR = "fair"
    WEAK = "weak"


@dataclass(frozen=True, slots=True)
class VaultPosture:
    """A secret-free summary of the vault's current posture."""

    level: PostureLevel
    score: int
    checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "score": self.score,
            "checks": list(self.checks),
        }


def score_posture(
    active: KeyRecord | None,
    recovery_remaining: int,
    privacy: PrivacyMode,
    resident_keys: int,
) -> VaultPosture:
    """Score posture from observable, non-secret facts."""
    checks: list[str] = []
    score = 0
    if active is not None and active.state.can_seal:
        score += 40
        checks.append("active-key")
    else:
        checks.append("no-active-key")
    if recovery_remaining > 0:
        score += 20
        checks.append("recovery-available")
    else:
        checks.append("recovery-empty")
    if privacy.hides_content:
        score += 20
        checks.append("privacy-on")
    else:
        checks.append("privacy-off")
    if resident_keys > 0:
        score += 20
        checks.append("key-resident")
    else:
        checks.append("key-not-resident")
    level = (
        PostureLevel.STRONG
        if score >= 80
        else PostureLevel.FAIR
        if score >= 50
        else PostureLevel.WEAK
    )
    return VaultPosture(level=level, score=score, checks=tuple(checks))


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """A redacted mapping plus the paths that were changed."""

    data: dict[str, Any]
    paths: tuple[str, ...]
    mode: PrivacyMode

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": dict(self.data),
            "paths": list(self.paths),
            "mode": self.mode.value,
        }


def _matches(path: str, rule: RedactionRule) -> bool:
    actual = path.split(".") if path else []
    expected = rule.segments
    if len(actual) != len(expected):
        return False
    return all(want == "*" or want == got for want, got in zip(expected, actual, strict=True))


class Redactor:
    """Apply dotted redaction rules to arbitrarily nested mappings."""

    def __init__(self, default_replacement: str = DEFAULT_REPLACEMENT) -> None:
        self.default_replacement = require_text(default_replacement, "default_replacement")

    def _transform(
        self,
        value: object,
        path: str,
        mode: PrivacyMode,
        rules: Sequence[RedactionRule],
        hits: list[str],
    ) -> object:
        if mode is PrivacyMode.LOCKED:
            if isinstance(value, dict):
                return {
                    str(key): self._transform(
                        child, f"{path}.{key}" if path else str(key), mode, rules, hits
                    )
                    for key, child in value.items()
                }
            if isinstance(value, list):
                return [
                    self._transform(
                        child, f"{path}.{index}" if path else str(index), mode, rules, hits
                    )
                    for index, child in enumerate(value)
                ]
            hits.append(path)
            return LOCKED_REPLACEMENT
        if isinstance(value, dict):
            result: dict[str, object] = {}
            for key, child in value.items():
                name = str(key)
                child_path = f"{path}.{name}" if path else name
                matched = next((rule for rule in rules if _matches(child_path, rule)), None)
                if matched is not None:
                    hits.append(child_path)
                    result[name] = matched.replacement
                else:
                    result[name] = self._transform(child, child_path, mode, rules, hits)
            return result
        if isinstance(value, list):
            return [
                self._transform(child, f"{path}.{index}" if path else str(index), mode, rules, hits)
                for index, child in enumerate(value)
            ]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def apply(
        self,
        data: Mapping[str, Any],
        rules: Sequence[RedactionRule] = (),
        mode: PrivacyMode = PrivacyMode.REDACTED,
    ) -> dict[str, Any]:
        """Return a redacted deep copy of a mapping."""
        result = self.redact_with_report(data, rules, mode)
        return result.data

    def redact_with_report(
        self,
        data: Mapping[str, Any],
        rules: Sequence[RedactionRule] = (),
        mode: PrivacyMode = PrivacyMode.REDACTED,
    ) -> RedactionResult:
        """Redact and report which field paths were changed."""
        if not isinstance(data, Mapping):
            raise RedactionError("data must be a mapping")
        if not isinstance(mode, PrivacyMode):
            raise RedactionError("mode must be a PrivacyMode")
        for rule in rules:
            if not isinstance(rule, RedactionRule):
                raise RedactionError("rules must contain RedactionRule values")
        hits: list[str] = []
        effective_rules = () if mode is PrivacyMode.NORMAL else rules
        transformed = self._transform(dict(data), "", mode, effective_rules, hits)
        if not isinstance(transformed, dict):
            raise RedactionError("redaction must produce a mapping")
        return RedactionResult(data=transformed, paths=tuple(hits), mode=mode)


__all__ = [
    "AAD_DOMAIN",
    "DEFAULT_REPLACEMENT",
    "LOCKED_REPLACEMENT",
    "MAC_DOMAIN",
    "MAX_RECOVERY_CODES",
    "STREAM_DOMAIN",
    "IntegrityError",
    "KeyManager",
    "PassphraseError",
    "PostureLevel",
    "RecoveryError",
    "RecoveryManager",
    "RecoveryResult",
    "RedactionError",
    "RedactionResult",
    "Redactor",
    "RotationResult",
    "StreamSeal",
    "VaultError",
    "VaultKeyError",
    "VaultPosture",
    "score_posture",
]
