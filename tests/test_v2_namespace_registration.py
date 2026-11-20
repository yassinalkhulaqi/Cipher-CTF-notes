"""Regression tests for explicit, additive API v2 namespace registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.web.v2 import ApiV2, V2Router
from redscribe.ui.web.v2.namespaces import sync


@pytest.fixture
def vault(tmp_path: Path):
    db = Vault(tmp_path / "vault.db")
    try:
        yield db
    finally:
        db.close()


def test_bare_api_has_only_kernel_routes(vault: Vault) -> None:
    api = ApiV2(vault)
    namespaces = {name.split(".", 1)[0] for name in api.routes}
    assert namespaces == {"system", "api", "notes"}


def test_explicit_registration_is_additive(vault: Vault) -> None:
    api = ApiV2(vault)
    before = set(api.routes)
    namespace = sync.register(api)
    added = set(api.routes) - before
    assert added == set(namespace.routes())
    assert added == set(sync.route_names())


def test_router_builds_a_fully_registered_registry(vault: Vault) -> None:
    router = V2Router(vault)
    names = set(router.api.routes)
    assert "sync.health" in names
    assert "blocks.capabilities" in names


def test_supplied_registry_is_not_mutated_by_router(vault: Vault) -> None:
    api = ApiV2(vault)
    before = set(api.routes)
    V2Router(vault, api)
    assert set(api.routes) == before
