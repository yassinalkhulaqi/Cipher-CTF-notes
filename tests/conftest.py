from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from redscribe.db import Vault


@pytest.fixture
def vault(tmp_path: Path) -> Iterator[Vault]:
    instance = Vault(tmp_path / "vault.db")
    try:
        yield instance
    finally:
        instance.close()
