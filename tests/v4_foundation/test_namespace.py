from __future__ import annotations

import pytest

import redscribe.v4 as v4
from redscribe.v4 import capabilities, contracts, events


@pytest.fixture(autouse=True)
def _reset() -> None:
    v4.reset_registration()
    yield
    v4.reset_registration()


def test_discover_modules_finds_foundation_modules() -> None:
    discovered = v4.discover_modules()
    assert "contracts" in discovered
    assert "events" in discovered
    assert "capabilities" in discovered
    assert "api_v4" in discovered


def test_install_namespaces_is_idempotent() -> None:
    first = v4.install_namespaces()
    second = v4.install_namespaces()
    assert first is second
    assert set(first) >= {"contracts", "events", "capabilities"}


def test_reset_registration_clears_cache() -> None:
    first = v4.install_namespaces()
    v4.reset_registration()
    second = v4.install_namespaces()
    assert first is not second
    assert first == second


def test_register_all_picks_up_register_hooks() -> None:
    class Api:
        def __init__(self) -> None:
            self.calls: list[str] = []

    api = Api()
    registered = v4.register_all(api)
    assert isinstance(registered, list)
    assert registered == sorted(registered)


def test_exports_are_sorted() -> None:
    assert v4.__all__ == sorted(v4.__all__)


def test_foundation_modules_importable() -> None:
    assert contracts.EntityKind.NOTE.value == "note"
    assert events.EventKind.RUN_STARTED.value == "run.started"
    assert capabilities.FeatureFlag.INBOX.value == "inbox"
