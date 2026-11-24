"""Tests for resumable, checksummed chunk transfers."""

from __future__ import annotations

import base64

import pytest

from redscribe.v3.portability.bundle import PortableBundle, create_bundle
from redscribe.v3.portability.device import DeviceIdentity
from redscribe.v3.portability.errors import TransferError
from redscribe.v3.portability.transfer import TransferManager, TransferState
from tests.v3_portability.conftest import TEST_PASSPHRASE, make_entity


def bundle_bytes() -> bytes:
    """Create a small encrypted bundle as transfer payload."""
    bundle: PortableBundle = create_bundle(
        (make_entity("note:1"),),
        (),
        device=DeviceIdentity("alpha", "Alpha"),
        passphrase=TEST_PASSPHRASE,
        iterations=1_000,
    )
    return bundle.to_bytes()


def push_all(
    manager: TransferManager, transfer_id: str, data: bytes, *, chunk_size: int = 32
) -> None:
    """Push every chunk of a data blob into a transfer session."""
    for index, start in enumerate(range(0, len(data), chunk_size)):
        manager.push(transfer_id, index, data[start : start + chunk_size])


def test_start_splits_data_into_chunks() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    assert session.transfer_id.startswith("xfer_")
    assert session.total_bytes == len(data)
    assert session.total_chunks == (len(data) + 31) // 32
    assert session.state is TransferState.ACTIVE
    assert session.percent == 0
    assert session.missing() == tuple(range(session.total_chunks))


def test_push_all_chunks_and_finish() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    push_all(manager, session.transfer_id, data)
    assert session.is_complete()
    assert session.percent == 100
    assert manager.finish(session.transfer_id) == data
    assert session.state is TransferState.COMPLETE


def test_partial_progress_and_missing_chunks() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    manager.push(session.transfer_id, 0, data[0:32])
    assert session.received_chunks == 1
    assert session.received_bytes == 32
    assert 0 < session.percent < 100
    assert 0 not in session.missing()
    with pytest.raises(TransferError, match="missing"):
        manager.finish(session.transfer_id)


def test_push_rejects_bad_index() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    with pytest.raises(TransferError, match="out of range"):
        manager.push(session.transfer_id, 999, b"x")
    with pytest.raises(TransferError, match="out of range"):
        manager.push(session.transfer_id, -1, b"x")


def test_corrupt_chunk_is_refused() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    with pytest.raises(TransferError, match="checksum"):
        manager.push(session.transfer_id, 0, b"corrupted-chunk-data")


def test_pause_resume_preserves_received_chunks() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    manager.push(session.transfer_id, 0, data[0:32])
    manager.pause(session.transfer_id)
    assert session.state is TransferState.PAUSED
    assert session.received_chunks == 1
    manager.resume(session.transfer_id)
    assert session.state is TransferState.ACTIVE
    assert session.received_chunks == 1
    push_all(manager, session.transfer_id, data)
    assert manager.finish(session.transfer_id) == data


def test_cancelled_transfer_cannot_resume_or_push() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    manager.cancel(session.transfer_id)
    assert session.state is TransferState.CANCELLED
    with pytest.raises(TransferError):
        manager.resume(session.transfer_id)
    with pytest.raises(TransferError):
        manager.push(session.transfer_id, 0, data[0:32])


def test_checkpoint_is_resumable() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    manager.push(session.transfer_id, 0, data[0:32])
    checkpoint = manager.checkpoint(session.transfer_id)
    assert checkpoint["resumable"]
    assert checkpoint["received_chunks"] == 1
    assert checkpoint["missing_chunks"][0] == 1
    assert checkpoint["receipts"][0]["index"] == 0


def test_metadata_only_begin_and_resume() -> None:
    data = bundle_bytes()
    source = TransferManager().start("bundle_1", data, chunk_size=64)
    manager = TransferManager()
    session = manager.begin(
        "bundle_1",
        total_chunks=source.total_chunks,
        chunk_size=64,
        total_bytes=len(data),
        checksum=source.checksum,
    )
    assert session.state is TransferState.PREPARING
    assert (
        manager.begin(
            "bundle_1",
            total_chunks=source.total_chunks,
            chunk_size=64,
            total_bytes=len(data),
            checksum=source.checksum,
        )
        is session
    )
    manager.resume(session.transfer_id)
    push_all(manager, session.transfer_id, data, chunk_size=64)
    assert manager.finish(session.transfer_id) == data


def test_finish_detects_assembled_digest_mismatch() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    push_all(manager, session.transfer_id, data)
    session.checksum = "0" * 64
    with pytest.raises(TransferError, match="bundle checksum"):
        manager.finish(session.transfer_id)
    assert session.state is TransferState.FAILED


def test_chunk_receipts_and_base64_round_trip() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    chunk = data[0:32]
    receipt = manager.push(session.transfer_id, 0, base64.b64decode(base64.b64encode(chunk)))
    assert receipt.index == 0
    assert receipt.size == 32
    assert len(receipt.digest) == 64
    assert receipt.as_dict()["digest"] == receipt.digest


def test_original_chunk_is_kept_on_duplicate_push() -> None:
    data = bundle_bytes()
    manager = TransferManager()
    session = manager.start("bundle_1", data, chunk_size=32)
    manager.push(session.transfer_id, 0, data[0:32])
    receipt = manager.push(session.transfer_id, 0, data[0:32])
    assert receipt.index == 0
    assert session.received_chunks == 1


def test_unknown_transfer_refused() -> None:
    manager = TransferManager()
    with pytest.raises(TransferError, match="Unknown transfer"):
        manager.get("xfer_missing")
