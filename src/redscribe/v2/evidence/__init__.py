"""Evidence vault domain, storage, and services.

The package is additive: it uses the existing vault connection for metadata but
owns its own tables and blob storage, so no v1 schema or API behavior changes.
"""

from __future__ import annotations

from redscribe.v2.evidence.errors import (
    ConflictError,
    EvidenceError,
    IngestError,
    IntegrityError,
    ManifestError,
    NotFoundError,
    RepositoryError,
    ValidationError,
)
from redscribe.v2.evidence.files import (
    BlobStore,
    DirectoryBlobStore,
    InMemoryBlobStore,
)
from redscribe.v2.evidence.integrity import IntegrityVerifier
from redscribe.v2.evidence.models import (
    CustodyAction,
    EvidenceKind,
    EvidenceManifest,
    EvidenceRecord,
    EvidenceStatus,
    FindingLink,
    IntegrityReport,
    IntegrityState,
    RetentionPolicy,
)
from redscribe.v2.evidence.repositories import (
    EvidenceRepository,
    InMemoryEvidenceRepository,
    SQLiteEvidenceRepository,
)
from redscribe.v2.evidence.services import EvidenceVaultService, create_service

__all__ = [
    "BlobStore",
    "ConflictError",
    "CustodyAction",
    "DirectoryBlobStore",
    "EvidenceError",
    "EvidenceKind",
    "EvidenceManifest",
    "EvidenceRecord",
    "EvidenceRepository",
    "EvidenceStatus",
    "EvidenceVaultService",
    "FindingLink",
    "InMemoryBlobStore",
    "InMemoryEvidenceRepository",
    "IngestError",
    "IntegrityError",
    "IntegrityReport",
    "IntegrityState",
    "IntegrityVerifier",
    "ManifestError",
    "NotFoundError",
    "RepositoryError",
    "RetentionPolicy",
    "SQLiteEvidenceRepository",
    "ValidationError",
    "create_service",
]
