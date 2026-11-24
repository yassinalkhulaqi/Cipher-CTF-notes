"""Resumable chunked transfer sessions for interrupted bundle moves."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from redscribe.v3.portability.canonical import digest_value, sha256_hex
from redscribe.v3.portability.errors import TransferError


class TransferState(str, Enum):
    """Lifecycle states of a resumable transfer."""

    PREPARING = "preparing"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ChunkReceipt:
    """Proof that one chunk was received intact."""

    index: int
    digest: str
    size: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"index": self.index, "digest": self.digest, "size": self.size}


@dataclass(slots=True)
class TransferSession:
    """Mutable state of one resumable bundle transfer."""

    transfer_id: str
    bundle_id: str
    total_chunks: int
    chunk_size: int
    total_bytes: int
    checksum: str
    state: TransferState = TransferState.PREPARING
    chunks: dict[int, bytes] = field(default_factory=dict)
    digests: dict[int, str] = field(default_factory=dict)
    received: dict[int, ChunkReceipt] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if self.total_chunks < 0 or self.chunk_size < 1 or self.total_bytes < 0:
            raise TransferError("Invalid transfer size parameters")

    @property
    def received_chunks(self) -> int:
        """Number of chunks with verified data."""
        return len(self.chunks)

    @property
    def received_bytes(self) -> int:
        """Number of received bytes."""
        return sum(receipt.size for receipt in self.received.values())

    @property
    def percent(self) -> int:
        """Integer completion percentage, clamped to 0-100."""
        if self.total_chunks == 0:
            return 100
        return min(100, round(100 * self.received_chunks / self.total_chunks))

    def missing(self) -> tuple[int, ...]:
        """Return indexes of chunks that have not been received."""
        return tuple(index for index in range(self.total_chunks) if index not in self.chunks)

    def is_complete(self) -> bool:
        """Return whether every chunk has arrived."""
        return not self.missing()

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe status snapshot."""
        return {
            "transfer_id": self.transfer_id,
            "bundle_id": self.bundle_id,
            "state": self.state.value,
            "total_chunks": self.total_chunks,
            "received_chunks": self.received_chunks,
            "missing_chunks": list(self.missing()),
            "total_bytes": self.total_bytes,
            "received_bytes": self.received_bytes,
            "percent": self.percent,
            "checksum": self.checksum,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TransferManager:
    """In-memory manager that tolerates interruption and resume."""

    def __init__(self) -> None:
        self._sessions: dict[str, TransferSession] = {}

    def start(
        self,
        bundle_id: str,
        data: bytes,
        *,
        chunk_size: int = 64 * 1024,
        created_at: float = 0.0,
    ) -> TransferSession:
        """Create a transfer session from bundle bytes."""
        if chunk_size < 1:
            raise TransferError("Chunk size must be positive")
        seed = digest_value({"bundle": bundle_id, "bytes": len(data), "at": created_at})
        transfer_id = f"xfer_{seed[:16]}"
        digests = {
            index: sha256_hex(data[start : start + chunk_size])
            for index, start in enumerate(range(0, len(data), chunk_size))
        }
        session = TransferSession(
            transfer_id=transfer_id,
            bundle_id=bundle_id,
            total_chunks=len(digests),
            chunk_size=chunk_size,
            total_bytes=len(data),
            checksum=sha256_hex(data),
            state=TransferState.ACTIVE,
            digests=digests,
            created_at=created_at,
            updated_at=created_at,
        )
        self._sessions[transfer_id] = session
        return session

    def begin(
        self,
        bundle_id: str,
        *,
        total_chunks: int,
        chunk_size: int,
        total_bytes: int,
        checksum: str,
        created_at: float = 0.0,
    ) -> TransferSession:
        """Create a metadata-only session so a peer can resume a known transfer."""
        transfer_id = f"xfer_{digest_value({'bundle': bundle_id, 'checksum': checksum})[:16]}"
        if transfer_id in self._sessions:
            return self._sessions[transfer_id]
        session = TransferSession(
            transfer_id=transfer_id,
            bundle_id=bundle_id,
            total_chunks=total_chunks,
            chunk_size=chunk_size,
            total_bytes=total_bytes,
            checksum=checksum,
            state=TransferState.PREPARING,
            created_at=created_at,
            updated_at=created_at,
        )
        self._sessions[transfer_id] = session
        return session

    def get(self, transfer_id: str) -> TransferSession:
        """Return a session or raise :class:`TransferError`."""
        session = self._sessions.get(transfer_id)
        if session is None:
            raise TransferError(f"Unknown transfer: {transfer_id}")
        return session

    def push(
        self,
        transfer_id: str,
        index: int,
        data: bytes,
        *,
        updated_at: float = 0.0,
    ) -> ChunkReceipt:
        """Store one verified chunk and return its receipt."""
        session = self.get(transfer_id)
        if session.state in (TransferState.CANCELLED, TransferState.COMPLETE):
            raise TransferError(f"Transfer is {session.state.value}: {transfer_id}")
        if index < 0 or index >= session.total_chunks:
            raise TransferError(f"Chunk index out of range: {index}")
        expected = session.digests.get(index)
        digest = sha256_hex(data)
        if expected is not None and expected != digest:
            raise TransferError(f"Chunk {index} failed its checksum")
        if index in session.chunks:
            return session.received[index]
        receipt = ChunkReceipt(index=index, digest=digest, size=len(data))
        session.chunks[index] = data
        session.received[index] = receipt
        session.state = TransferState.ACTIVE
        session.updated_at = updated_at
        return receipt

    def pause(self, transfer_id: str) -> TransferSession:
        """Mark a session paused without dropping received chunks."""
        session = self.get(transfer_id)
        if session.state is TransferState.CANCELLED:
            raise TransferError(f"Transfer is cancelled: {transfer_id}")
        session.state = TransferState.PAUSED
        return session

    def resume(self, transfer_id: str) -> TransferSession:
        """Resume a paused or failed session with its progress intact."""
        session = self.get(transfer_id)
        if session.state is TransferState.CANCELLED:
            raise TransferError(f"Cancelled transfers cannot be resumed: {transfer_id}")
        session.state = TransferState.ACTIVE
        return session

    def cancel(self, transfer_id: str) -> TransferSession:
        """Cancel a session, preserving receipts for the audit trail."""
        session = self.get(transfer_id)
        session.state = TransferState.CANCELLED
        return session

    def finish(self, transfer_id: str) -> bytes:
        """Assemble all chunks and verify the final bundle digest."""
        session = self.get(transfer_id)
        if session.state is TransferState.CANCELLED:
            raise TransferError(f"Transfer is cancelled: {transfer_id}")
        if not session.is_complete():
            raise TransferError(
                f"Transfer is missing {len(session.missing())} chunks: {transfer_id}"
            )
        data = b"".join(session.chunks[index] for index in range(session.total_chunks))
        if sha256_hex(data) != session.checksum:
            session.state = TransferState.FAILED
            raise TransferError("Assembled transfer failed its bundle checksum")
        session.state = TransferState.COMPLETE
        return data

    def checkpoint(self, transfer_id: str) -> dict[str, Any]:
        """Return a resumable checkpoint describing what still needs to arrive."""
        session = self.get(transfer_id)
        return {
            **session.as_dict(),
            "resumable": session.state
            in (
                TransferState.PAUSED,
                TransferState.FAILED,
                TransferState.ACTIVE,
                TransferState.PREPARING,
            ),
            "receipts": [receipt.as_dict() for receipt in session.received.values()],
        }

    def all(self) -> tuple[TransferSession, ...]:
        """Return sessions in stable order."""
        return tuple(self._sessions[key] for key in sorted(self._sessions))
