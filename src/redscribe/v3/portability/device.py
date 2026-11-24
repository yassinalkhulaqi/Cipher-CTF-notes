"""Device identity and trust for portable bundle provenance."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

from redscribe.v3.portability.errors import DeviceError


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    """A local device that may author or receive portable bundles."""

    device_id: str
    label: str
    platform: str = "desktop"
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.device_id.strip():
            raise DeviceError("Device id cannot be blank")
        if not self.label.strip():
            raise DeviceError("Device label cannot be blank")
        if any(char.isspace() for char in self.device_id):
            raise DeviceError("Device id cannot contain whitespace")

    @property
    def fingerprint(self) -> str:
        """Stable public fingerprint used in manifests and receipts."""
        raw = f"{self.device_id}|{self.label}|{self.platform}".encode()
        return hashlib.sha256(raw).hexdigest()[:20]

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation."""
        return {
            "device_id": self.device_id,
            "label": self.label,
            "platform": self.platform,
            "created_at": self.created_at,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    """A device entry in the local trust registry."""

    identity: DeviceIdentity
    trusted: bool = False
    last_seen: float = 0.0

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation."""
        return {
            **self.identity.as_dict(),
            "trusted": self.trusted,
            "last_seen": self.last_seen,
        }


class DeviceRegistry:
    """In-memory registry of known devices and their trust decisions."""

    def __init__(self) -> None:
        self._devices: dict[str, DeviceRecord] = {}

    def add(self, identity: DeviceIdentity, *, trusted: bool = False) -> DeviceRecord:
        """Register a device, preserving an existing trust decision."""
        existing = self._devices.get(identity.device_id)
        record = DeviceRecord(
            identity=identity,
            trusted=trusted if existing is None else existing.trusted,
            last_seen=existing.last_seen if existing else 0.0,
        )
        self._devices[identity.device_id] = record
        return record

    def get(self, device_id: str) -> DeviceRecord:
        """Return a device or raise :class:`DeviceError`."""
        record = self._devices.get(device_id)
        if record is None:
            raise DeviceError(f"Unknown device: {device_id}")
        return record

    def find(self, device_id: str) -> DeviceRecord | None:
        """Look up a device without raising."""
        return self._devices.get(device_id)

    def trust(self, device_id: str, *, seen_at: float = 0.0) -> DeviceRecord:
        """Mark a known device as trusted."""
        record = self.get(device_id)
        updated = DeviceRecord(record.identity, True, seen_at or record.last_seen)
        self._devices[device_id] = updated
        return updated

    def revoke(self, device_id: str) -> DeviceRecord:
        """Revoke trust for a known device."""
        record = self.get(device_id)
        updated = DeviceRecord(record.identity, False, record.last_seen)
        self._devices[device_id] = updated
        return updated

    def see(self, device_id: str, *, at: float) -> None:
        """Update the last-seen timestamp for a device."""
        record = self.get(device_id)
        updated = DeviceRecord(record.identity, record.trusted, at)
        self._devices[device_id] = updated

    def is_trusted(self, device_id: str) -> bool:
        """Return whether a device is known and trusted."""
        record = self.find(device_id)
        return record is not None and record.trusted

    def require_trusted(self, device_id: str) -> DeviceRecord:
        """Raise when a device is unknown or untrusted."""
        if not self.is_trusted(device_id):
            raise DeviceError(f"Device is not trusted: {device_id}")
        return self.get(device_id)

    def all(self) -> tuple[DeviceRecord, ...]:
        """Return devices in stable order."""
        return tuple(self._devices[key] for key in sorted(self._devices))

    def fingerprints(self) -> dict[str, str]:
        """Return device id to fingerprint mapping."""
        return {key: record.identity.fingerprint for key, record in sorted(self._devices.items())}

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation."""
        return {
            "devices": [record.as_dict() for record in self.all()],
            "trusted": [record.identity.device_id for record in self.all() if record.trusted],
            "count": len(self._devices),
        }


@dataclass(frozen=True, slots=True)
class OriginSeal:
    """Short proof that a bundle header came from a known device."""

    device_id: str
    digest: str
    signature: str = field(repr=False)

    def verify(self, registry: DeviceRegistry, digest: str) -> bool:
        """Verify a seal against a trusted device fingerprint."""
        if digest != self.digest or not registry.is_trusted(self.device_id):
            return False
        fingerprint = registry.get(self.device_id).identity.fingerprint
        expected = hmac.new(fingerprint.encode("utf-8"), digest.encode("utf-8"), "sha256")
        return hmac.compare_digest(expected.hexdigest(), self.signature)

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-safe representation."""
        return {"device_id": self.device_id, "digest": self.digest, "signature": self.signature}


def seal_origin(device: DeviceIdentity, digest: str) -> OriginSeal:
    """Create an origin seal for a bundle digest."""
    signature = hmac.new(
        device.fingerprint.encode("utf-8"), digest.encode("utf-8"), "sha256"
    ).hexdigest()
    return OriginSeal(device_id=device.device_id, digest=digest, signature=signature)
