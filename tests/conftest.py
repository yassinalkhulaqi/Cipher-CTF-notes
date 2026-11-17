from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from redscribe.storage.db import Vault


@pytest.fixture
def vault(tmp_path: Path) -> Iterator[Vault]:
    instance = Vault(tmp_path / "vault.db")
    try:
        yield instance
    finally:
        instance.close()


@pytest.fixture
def vault_factory(tmp_path: Path) -> Iterator[Callable[..., Vault]]:
    instances: list[Vault] = []

    def factory(name: str = "vault.db", **options: bool) -> Vault:
        instance = Vault(tmp_path / name, **options)
        instances.append(instance)
        return instance

    yield factory
    for instance in instances:
        instance.close()
