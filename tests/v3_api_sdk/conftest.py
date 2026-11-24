"""Shared fixtures for the B13 SDK tests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from redscribe.v3.api.router import V3Router, register_system_routes
from redscribe.v3.api_sdk.capabilities import CapabilityNegotiator
from redscribe.v3.api_sdk.client import SdkClient
from redscribe.v3.api_sdk.manifest import example_manifest
from redscribe.v3.api_sdk.service import ExtensionService, get_service, set_service
from redscribe.v3.api_sdk.transport import InProcessTransport
from redscribe.v3.capabilities import CAP_EXTENSIONS
from redscribe.v3.clock import FixedClock
from redscribe.v3.config import V3Config
from redscribe.v3.namespaces.extensions import register as register_extensions
from redscribe.v3.namespaces.system import register as register_system


@pytest.fixture
def router() -> V3Router:
    router = V3Router()
    register_system_routes(router)
    register_system(router)
    register_extensions(router)
    return router


@pytest.fixture
def writable_service() -> Iterator[ExtensionService]:
    previous = get_service()
    config = V3Config(
        allow_extensions=True,
        enabled_capabilities=(CAP_EXTENSIONS,),
        offline_only=True,
    )
    service = ExtensionService(config)
    set_service(service)
    yield service
    set_service(previous)


@pytest.fixture
def client(router: V3Router) -> SdkClient:
    return SdkClient(
        transport=InProcessTransport(router=router),
        clock=FixedClock(start=1000.0, step=0.5),
    )


@pytest.fixture
def writable_client(router: V3Router, writable_service: ExtensionService) -> SdkClient:
    transport = InProcessTransport(
        router=router,
        negotiator=CapabilityNegotiator(config=writable_service.config),
        allow_write=True,
    )
    return SdkClient(transport=transport, clock=FixedClock(start=1000.0, step=0.5))


@pytest.fixture
def sample_manifest() -> dict[str, Any]:
    return example_manifest()
