"""Encrypted portable bundles with manifests, origin seals, and verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities.types import EntityLink as V3EntityLink
from redscribe.v3.portability.canonical import canonical_bytes, digest_value
from redscribe.v3.portability.crypto import (
    DEFAULT_KDF_ITERATIONS,
    EncryptedBlob,
    decrypt_bytes,
    encrypt_bytes,
)
from redscribe.v3.portability.device import DeviceIdentity, OriginSeal, seal_origin
from redscribe.v3.portability.errors import BundleError, VerificationError
from redscribe.v3.portability.manifest import BundleManifest, VerificationReport
from redscribe.v3.portability.records import (
    PortableEntity,
    link_as_dict,
    link_from_dict,
    stable_entities,
    stable_links,
)
from redscribe.v3.portability.vectors import VersionVector

BUNDLE_VERSION = "v3.1"
MAX_BUNDLE_BYTES = 40 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class BundleHeader:
    """Unencrypted metadata required to open and attribute a bundle."""

    bundle_id: str
    manifest_digest: str
    source_device: str
    created_at: float
    kdf_iterations: int
    algorithm: str
    bundle_version: str = BUNDLE_VERSION
    aad: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "bundle_id": self.bundle_id,
            "manifest_digest": self.manifest_digest,
            "source_device": self.source_device,
            "created_at": self.created_at,
            "kdf_iterations": self.kdf_iterations,
            "algorithm": self.algorithm,
            "bundle_version": self.bundle_version,
            "aad": self.aad,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BundleHeader:
        """Parse a header from serialized data."""
        try:
            version = str(payload["bundle_version"])
            if version != BUNDLE_VERSION:
                raise BundleError(f"Unsupported bundle version: {version}")
            return cls(
                bundle_id=str(payload["bundle_id"]),
                manifest_digest=str(payload["manifest_digest"]),
                source_device=str(payload["source_device"]),
                created_at=float(payload["created_at"]),
                kdf_iterations=int(payload["kdf_iterations"]),
                algorithm=str(payload["algorithm"]),
                bundle_version=version,
                aad=str(payload.get("aad", "")),
            )
        except BundleError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise BundleError("Malformed bundle header") from error


@dataclass(frozen=True, slots=True)
class BundlePayload:
    """Verified plaintext contents of an opened bundle."""

    manifest: BundleManifest
    entities: tuple[PortableEntity, ...]
    links: tuple[V3EntityLink, ...]
    report: VerificationReport
    origin_device: str

    def counts(self) -> dict[str, int]:
        """Return payload size counters."""
        return {
            "entities": len(self.entities),
            "links": len(self.links),
            "families": len(self.manifest.families),
        }

    def as_dict(self) -> dict[str, Any]:
        """Return a safe plaintext summary."""
        return {
            **self.counts(),
            "manifest": self.manifest.as_dict(),
            "verification": self.report.as_dict(),
            "origin_device": self.origin_device,
        }


@dataclass(frozen=True, slots=True)
class PortableBundle:
    """A serialized, encrypted, verifiable vault bundle."""

    header: BundleHeader
    manifest: BundleManifest
    envelope: EncryptedBlob
    origin: OriginSeal

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "format": "redscribe-portable-bundle",
            "header": self.header.as_dict(),
            "manifest": self.manifest.as_dict(),
            "envelope": self.envelope.as_dict(),
            "origin": self.origin.as_dict(),
        }

    def to_bytes(self) -> bytes:
        """Serialize the bundle to deterministic bytes."""
        return canonical_bytes(self.as_dict())

    def size(self) -> int:
        """Return the serialized bundle size in bytes."""
        return len(self.to_bytes())

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PortableBundle:
        """Rebuild a bundle from parsed JSON data."""
        if payload.get("format") != "redscribe-portable-bundle":
            raise BundleError("Unknown portable bundle format")
        try:
            header = BundleHeader.from_dict(payload["header"])
            manifest = BundleManifest.from_dict(payload["manifest"])
            envelope = EncryptedBlob.from_dict(payload["envelope"])
            origin_payload = payload["origin"]
            origin = OriginSeal(
                device_id=str(origin_payload["device_id"]),
                digest=str(origin_payload["digest"]),
                signature=str(origin_payload["signature"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise BundleError("Malformed portable bundle") from error
        if header.bundle_id != manifest.bundle_id:
            raise VerificationError("Bundle header and manifest disagree")
        if header.manifest_digest != manifest.digest():
            raise VerificationError("Bundle manifest digest does not match its header")
        return cls(header=header, manifest=manifest, envelope=envelope, origin=origin)

    @classmethod
    def from_bytes(cls, data: bytes) -> PortableBundle:
        """Parse a bundle from serialized bytes."""
        if len(data) > MAX_BUNDLE_BYTES:
            raise BundleError("Bundle exceeds the maximum supported size")
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BundleError("Bundle is not valid JSON") from error
        if not isinstance(payload, dict):
            raise BundleError("Bundle root must be an object")
        return cls.from_dict(payload)

    def inspect(self) -> dict[str, Any]:
        """Return metadata that can be shown without a passphrase."""
        return {
            "bundle_id": self.header.bundle_id,
            "bundle_version": self.header.bundle_version,
            "algorithm": self.header.algorithm,
            "source_device": self.header.source_device,
            "created_at": self.header.created_at,
            "manifest_digest": self.header.manifest_digest,
            "entity_count": self.manifest.entity_count,
            "link_count": self.manifest.link_count,
            "families": list(self.manifest.families),
            "schema_version": self.manifest.schema_version,
            "vector": self.manifest.vector.as_dict(),
            "size_bytes": self.size(),
        }


def _bundle_aad(manifest: BundleManifest, device: DeviceIdentity) -> str:
    """Return the additional authenticated data binding header to context."""
    return f"{manifest.bundle_id}|{manifest.digest()}|{device.fingerprint}"


def create_bundle(
    entities: tuple[PortableEntity, ...],
    links: tuple[V3EntityLink, ...] = (),
    *,
    device: DeviceIdentity,
    passphrase: str,
    clock: Clock | None = None,
    metadata: dict[str, Any] | None = None,
    iterations: int = DEFAULT_KDF_ITERATIONS,
) -> PortableBundle:
    """Seal a vault snapshot into an encrypted portable bundle."""
    timer: Clock = clock or SystemClock()
    timestamp = timer.now_timestamp()
    ordered_entities = stable_entities(entities)
    ordered_links = stable_links(links)
    vector = VersionVector.empty()
    for entity in ordered_entities:
        vector = vector.merge(entity.vector)
    seed = digest_value(
        {
            "device": device.device_id,
            "timestamp": timestamp,
            "entities": [entity.fingerprint() for entity in ordered_entities],
            "links": [digest_value(link.as_dict()) for link in ordered_links],
        }
    )
    bundle_id = f"bundle_{seed[:20]}"
    manifest = BundleManifest.build(
        bundle_id,
        ordered_entities,
        ordered_links,
        created_at=timestamp,
        source_device=device.device_id,
        vector=vector,
        metadata=metadata,
    )
    aad = _bundle_aad(manifest, device)
    payload = canonical_bytes(
        {
            "entities": [entity.as_dict() for entity in ordered_entities],
            "links": [link_as_dict(link) for link in ordered_links],
        }
    )
    envelope = encrypt_bytes(payload, passphrase, aad=aad, iterations=iterations)
    header = BundleHeader(
        bundle_id=bundle_id,
        manifest_digest=manifest.digest(),
        source_device=device.device_id,
        created_at=timestamp,
        kdf_iterations=iterations,
        algorithm=envelope.algorithm,
        aad=aad,
    )
    return PortableBundle(
        header=header,
        manifest=manifest,
        envelope=envelope,
        origin=seal_origin(device, manifest.origin_digest()),
    )


def open_bundle(
    bundle: PortableBundle,
    passphrase: str,
    *,
    verify: bool = True,
) -> BundlePayload:
    """Decrypt and verify a bundle, refusing to return unverified data."""
    if bundle.header.bundle_id != bundle.manifest.bundle_id:
        raise VerificationError("Bundle header and manifest disagree")
    if bundle.header.manifest_digest != bundle.manifest.digest():
        raise VerificationError("Bundle manifest digest does not match its header")
    if not bundle.header.aad.startswith(bundle.manifest.bundle_id):
        raise VerificationError("Bundle authenticated context is inconsistent")
    if bundle.envelope.aad != bundle.header.aad:
        raise VerificationError("Bundle envelope context does not match its header")
    plaintext = decrypt_bytes(bundle.envelope, passphrase)
    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError("Decrypted bundle payload is malformed") from error
    if not isinstance(payload, dict) or "entities" not in payload or "links" not in payload:
        raise BundleError("Decrypted bundle payload is missing required collections")
    entities = tuple(PortableEntity.from_dict(item) for item in payload["entities"])
    links = tuple(link_from_dict(item) for item in payload["links"])
    report = bundle.manifest.verify(entities, links)
    if verify:
        report.require_ok()
    return BundlePayload(
        manifest=bundle.manifest,
        entities=entities,
        links=links,
        report=report,
        origin_device=bundle.header.source_device,
    )


def write_bundle(path: Path, bundle: PortableBundle) -> int:
    """Write a bundle to a local path, returning the byte count."""
    data = bundle.to_bytes()
    if len(data) > MAX_BUNDLE_BYTES:
        raise BundleError("Bundle exceeds the maximum supported size")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


def read_bundle(path: Path) -> PortableBundle:
    """Read and parse a bundle from a local path."""
    if not path.is_file():
        raise BundleError(f"Bundle file not found: {path}")
    data = path.read_bytes()
    if len(data) > MAX_BUNDLE_BYTES:
        raise BundleError("Bundle exceeds the maximum supported size")
    return PortableBundle.from_bytes(data)
