"""Bundle manifests and integrity verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from redscribe.v3.entities.types import EntityLink as V3EntityLink
from redscribe.v3.migrations.v5 import SCHEMA_VERSION
from redscribe.v3.portability.canonical import (
    canonical_bytes,
    digest_collection,
    digest_entity,
    digest_value,
    ensure_json_safe,
    sha256_hex,
)
from redscribe.v3.portability.errors import ManifestError, VerificationError
from redscribe.v3.portability.records import PortableEntity
from redscribe.v3.portability.vectors import VersionVector

MANIFEST_VERSION = "v3.1"


@dataclass(frozen=True, slots=True)
class VerificationIssue:
    """One failed integrity check with a stable reason code."""

    code: str
    ref: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        """Return a JSON-safe representation."""
        return {"code": self.code, "ref": self.ref, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Result of verifying a bundle payload against its manifest."""

    issues: tuple[VerificationIssue, ...] = ()
    checked_entities: int = 0
    checked_links: int = 0

    @property
    def ok(self) -> bool:
        """Whether every check passed."""
        return not self.issues

    @property
    def codes(self) -> tuple[str, ...]:
        """Stable reason codes in encounter order."""
        return tuple(dict.fromkeys(issue.code for issue in self.issues))

    def require_ok(self) -> None:
        """Raise when verification failed."""
        if not self.ok:
            raise VerificationError(
                "Bundle verification failed",
                context={"codes": list(self.codes)},
            )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "ok": self.ok,
            "codes": list(self.codes),
            "issues": [issue.as_dict() for issue in self.issues],
            "checked_entities": self.checked_entities,
            "checked_links": self.checked_links,
        }


@dataclass(frozen=True, slots=True)
class BundleManifest:
    """Signed-by-hash inventory of a portable bundle."""

    bundle_id: str
    created_at: float
    source_device: str
    entity_count: int
    link_count: int
    checksums: dict[str, str]
    payload_digest: str
    families: tuple[str, ...] = ()
    vector: VersionVector = field(default_factory=VersionVector.empty)
    manifest_version: str = MANIFEST_VERSION
    schema_version: int = SCHEMA_VERSION
    app_version: str = "3.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.bundle_id.strip():
            raise ManifestError("Bundle id cannot be blank")
        if self.schema_version > SCHEMA_VERSION:
            raise ManifestError(
                f"Bundle schema {self.schema_version} is newer than supported {SCHEMA_VERSION}"
            )
        if self.entity_count < 0 or self.link_count < 0:
            raise ManifestError("Manifest counts cannot be negative")
        ensure_json_safe(self.metadata, path="$.metadata")

    @classmethod
    def build(
        cls,
        bundle_id: str,
        entities: tuple[PortableEntity, ...],
        links: tuple[V3EntityLink, ...],
        *,
        created_at: float,
        source_device: str,
        vector: VersionVector | None = None,
        metadata: dict[str, Any] | None = None,
        app_version: str = "3.0.0",
    ) -> BundleManifest:
        """Build a manifest from a concrete entity and link collection."""
        entity_payloads = tuple(entity.as_dict() for entity in entities)
        link_payloads = tuple(link.as_dict() for link in links)
        return cls(
            bundle_id=bundle_id,
            created_at=created_at,
            source_device=source_device,
            entity_count=len(entities),
            link_count=len(links),
            checksums={entity.ref: digest_entity(entity.as_dict()) for entity in entities},
            payload_digest=digest_collection(entity_payloads, link_payloads),
            families=tuple(sorted({entity.family for entity in entities})),
            vector=vector or VersionVector.empty(),
            metadata=dict(metadata or {}),
            app_version=app_version,
        )

    def verify(
        self,
        entities: tuple[PortableEntity, ...],
        links: tuple[V3EntityLink, ...],
    ) -> VerificationReport:
        """Compare a payload with every recorded checksum."""
        issues: list[VerificationIssue] = []
        if self.schema_version > SCHEMA_VERSION:
            issues.append(
                VerificationIssue("SCHEMA_MISMATCH", "manifest", "Bundle schema is too new")
            )
        actual = {entity.ref: digest_entity(entity.as_dict()) for entity in entities}
        for ref in sorted(set(self.checksums) - set(actual)):
            issues.append(VerificationIssue("MISSING_RECORD", ref, "Record listed in manifest"))
        for ref in sorted(set(actual) - set(self.checksums)):
            issues.append(VerificationIssue("EXTRA_RECORD", ref, "Record not in manifest"))
        for ref in sorted(set(actual) & set(self.checksums)):
            if actual[ref] != self.checksums[ref]:
                issues.append(
                    VerificationIssue("CHECKSUM_MISMATCH", ref, "Record checksum changed")
                )
        if self.entity_count != len(entities):
            issues.append(VerificationIssue("COUNT_MISMATCH", "entities", "Entity count changed"))
        if self.link_count != len(links):
            issues.append(VerificationIssue("COUNT_MISMATCH", "links", "Link count changed"))
        expected_digest = digest_collection(
            tuple(entity.as_dict() for entity in entities),
            tuple(link.as_dict() for link in links),
        )
        if expected_digest != self.payload_digest:
            issues.append(
                VerificationIssue("PAYLOAD_DIGEST_MISMATCH", "payload", "Payload digest changed")
            )
        return VerificationReport(tuple(issues), len(entities), len(links))

    def digest(self) -> str:
        """Return the canonical digest of the manifest itself."""
        return digest_value(self.as_dict())

    def origin_bytes(self) -> bytes:
        """Return the bytes covered by the device origin seal."""
        return canonical_bytes(
            {
                "bundle_id": self.bundle_id,
                "payload_digest": self.payload_digest,
                "created_at": self.created_at,
                "source_device": self.source_device,
            }
        )

    def origin_digest(self) -> str:
        """Return the short digest used as the device seal subject."""
        return sha256_hex(self.origin_bytes())[:24]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "manifest_version": self.manifest_version,
            "bundle_id": self.bundle_id,
            "created_at": self.created_at,
            "source_device": self.source_device,
            "schema_version": self.schema_version,
            "app_version": self.app_version,
            "entity_count": self.entity_count,
            "link_count": self.link_count,
            "families": list(self.families),
            "vector": self.vector.as_dict(),
            "checksums": dict(sorted(self.checksums.items())),
            "payload_digest": self.payload_digest,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BundleManifest:
        """Parse and validate a manifest from a JSON mapping."""
        try:
            version = str(payload["manifest_version"])
            if version != MANIFEST_VERSION:
                raise ManifestError(f"Unsupported manifest version: {version}")
            checksums = payload["checksums"]
            if not isinstance(checksums, dict):
                raise ManifestError("Manifest checksums must be a mapping")
            return cls(
                bundle_id=str(payload["bundle_id"]),
                created_at=float(payload["created_at"]),
                source_device=str(payload["source_device"]),
                schema_version=int(payload["schema_version"]),
                app_version=str(payload.get("app_version", "3.0.0")),
                entity_count=int(payload["entity_count"]),
                link_count=int(payload["link_count"]),
                families=tuple(str(item) for item in payload.get("families", ())),
                vector=VersionVector.from_dict(payload.get("vector")),
                checksums={str(key): str(value) for key, value in checksums.items()},
                payload_digest=str(payload["payload_digest"]),
                metadata=dict(payload.get("metadata", {})),
            )
        except ManifestError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise ManifestError("Malformed bundle manifest") from error
