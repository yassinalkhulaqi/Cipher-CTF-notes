"""Shared fixtures for V3 portability tests."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityId, EntityRecord, EntityStatus
from redscribe.v3.portability.crypto import encrypt_bytes
from redscribe.v3.portability.device import DeviceIdentity
from redscribe.v3.portability.records import PortableEntity
from redscribe.v3.portability.vectors import VersionVector

TEST_PASSPHRASE = "S3cure-Passphrase!42"


@pytest.fixture
def clock() -> FixedClock:
    """Deterministic clock starting at a fixed timestamp."""
    return FixedClock(1_700_000_000.0)


@pytest.fixture
def device() -> DeviceIdentity:
    """Trusted test device identity."""
    return DeviceIdentity("alpha", "Alpha laptop", "desktop", 1_700_000_000.0)


@pytest.fixture
def other_device() -> DeviceIdentity:
    """Second test device identity."""
    return DeviceIdentity("beta", "Beta desktop", "desktop", 1_700_000_010.0)


def make_entity(
    ref: str,
    *,
    title: str = "Sample finding",
    summary: str = "summary",
    tags: tuple[str, ...] = ("ctf",),
    body: str = "body text",
    version: int = 1,
    updated_at: float = 10.0,
    vector: dict[str, int] | None = None,
    deleted: bool = False,
    status: EntityStatus = EntityStatus.ACTIVE,
) -> PortableEntity:
    """Build a portable entity from a canonical reference."""
    record = EntityRecord(
        entity_id=EntityId.parse(ref),
        title=title,
        summary=summary,
        status=status,
        tags=tags,
        created_at=1.0,
        updated_at=updated_at,
        version=version,
    )
    return PortableEntity(
        record=record,
        vector=VersionVector(vector or {"alpha": 1}),
        body=body,
        deleted=deleted,
    )


@pytest.fixture
def entity_factory() -> Callable[..., PortableEntity]:
    """Expose the entity builder as a fixture."""
    return make_entity


@pytest.fixture
def blob_factory() -> Callable[..., object]:
    """Encrypt short payloads with cheap KDF settings for tests."""

    def build(text: str, *, passphrase: str = TEST_PASSPHRASE, aad: str = "") -> object:
        return encrypt_bytes(text.encode("utf-8"), passphrase, aad=aad, iterations=1_000)

    return build
