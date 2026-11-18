"""Blob storage for evidence payloads."""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from redscribe.v2.evidence.errors import IngestError
from redscribe.v2.evidence.hashing import hash_bytes
from redscribe.v2.evidence.validation import sanitize_filename, validate_evidence_id

DEFAULT_MAX_BLOB_BYTES = 64 * 1024 * 1024


class BlobStore(Protocol):
    """Storage contract used by the evidence service."""

    def put(self, evidence_id: str, filename: str, data: bytes) -> str:
        """Persist bytes and return an opaque storage path."""
        ...

    def get(self, stored_path: str) -> bytes | None:
        """Return stored bytes, or ``None`` when they are unavailable."""
        ...

    def delete(self, stored_path: str) -> bool:
        """Remove stored bytes, returning whether anything was removed."""
        ...

    def exists(self, stored_path: str) -> bool:
        """Return whether stored bytes are present."""
        ...


class InMemoryBlobStore:
    """Blob store used for tests and short-lived vaults."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}
        self._names: dict[str, str] = {}

    def put(self, evidence_id: str, filename: str, data: bytes) -> str:
        record_id = validate_evidence_id(evidence_id, field="evidence_id")
        name = sanitize_filename(filename)
        path = f"memory://{record_id}/{name}"
        self._blobs[path] = bytes(data)
        self._names[path] = name
        return path

    def get(self, stored_path: str) -> bytes | None:
        return self._blobs.get(stored_path)

    def delete(self, stored_path: str) -> bool:
        return self._blobs.pop(stored_path, None) is not None

    def exists(self, stored_path: str) -> bool:
        return stored_path in self._blobs

    def paths(self) -> tuple[str, ...]:
        """Return all stored paths in insertion order."""
        return tuple(self._blobs)

    def total_bytes(self) -> int:
        """Return the total number of stored bytes."""
        return sum(len(item) for item in self._blobs.values())


class DirectoryBlobStore:
    """Blob store writing evidence payloads beneath a dedicated directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _target(self, stored_path: str) -> Path:
        if not stored_path.startswith("evidence://"):
            raise IngestError("Unknown evidence storage path", details={"path": stored_path})
        relative = stored_path.removeprefix("evidence://").replace("/", os.sep)
        target = (self._root / relative).resolve()
        if not target.is_relative_to(self._root):
            raise IngestError("Evidence path escapes the blob directory")
        return target

    def put(self, evidence_id: str, filename: str, data: bytes) -> str:
        record_id = validate_evidence_id(evidence_id, field="evidence_id")
        name = sanitize_filename(filename)
        directory = self._root / record_id[:2] / record_id
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / name
        target.write_bytes(data)
        relative = target.resolve().relative_to(self._root).as_posix()
        return f"evidence://{relative}"

    def get(self, stored_path: str) -> bytes | None:
        target = self._target(stored_path)
        if not target.is_file():
            return None
        try:
            return target.read_bytes()
        except OSError:
            return None

    def delete(self, stored_path: str) -> bool:
        target = self._target(stored_path)
        if not target.is_file():
            return False
        target.unlink()
        parent = target.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
        return True

    def exists(self, stored_path: str) -> bool:
        return self._target(stored_path).is_file()

    def purge(self) -> int:
        """Delete all stored evidence payloads and return the removed count."""
        count = 0
        for child in self._root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
                count += 1
            elif child.is_file():
                child.unlink()
                count += 1
        return count


def validate_blob_size(data: bytes, *, max_bytes: int = DEFAULT_MAX_BLOB_BYTES) -> None:
    """Raise when an ingest payload exceeds the configured limit."""
    if not isinstance(data, bytes):
        raise IngestError("Evidence payload must be bytes")
    if not data:
        raise IngestError("Evidence payload must not be empty")
    if len(data) > max_bytes:
        raise IngestError(
            f"Evidence payload exceeds {max_bytes} bytes",
            details={"size_bytes": len(data), "max_bytes": max_bytes},
        )


def blob_profile(data: bytes) -> dict[str, object]:
    """Return a compact profile for a payload before ingestion."""
    digests = hash_bytes(data)
    return {
        "sha256": digests.sha256,
        "md5": digests.md5,
        "size_bytes": digests.size_bytes,
    }


def blob_paths(store: BlobStore, stored_paths: Mapping[str, str]) -> dict[str, bool]:
    """Check availability for a mapping of evidence ids to storage paths."""
    return {evidence_id: store.exists(path) for evidence_id, path in stored_paths.items()}
