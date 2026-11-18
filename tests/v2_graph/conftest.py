from __future__ import annotations

from pathlib import Path

import pytest

from redscribe.storage.db import Vault


def seed_vault(vault: Vault) -> tuple[int, int, int]:
    folder = vault.create_node("CTF", kind="folder")
    alpha = vault.create_node(
        "Alpha", folder.id, content="See [[Beta]] and #web.", tags="web, recon"
    )
    beta = vault.create_node(
        "Beta", folder.id, content="See [[Gamma]] and [[Missing Note]].", tags="web"
    )
    vault.create_node("Gamma", folder.id, content="[[Alpha]] closes the loop.", tags="recon")
    vault.create_node("Island", content="No links here.")
    return folder.id, alpha.id, beta.id


@pytest.fixture
def graph_vault(tmp_path: Path) -> Vault:
    instance = Vault(tmp_path / "graph.db")
    try:
        yield instance
    finally:
        instance.close()
