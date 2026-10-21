from __future__ import annotations

from redscribe.demo import seed_demo
from redscribe.storage.db import Vault


def test_seed_demo_populates_an_empty_vault(vault: Vault) -> None:
    assert seed_demo(vault) == 6
    stats = vault.stats()
    assert stats.notes == 6
    assert stats.folders == 3
    assert stats.flags == 2
    assert stats.targets == 3
    assert stats.tags == 15
    assert stats.pinned == 3
    assert len(vault.list_custom_snippets()) == 1
    assert {hit.flag for hit in vault.collected_flags()} == {
        "HTB{th1s_1s_4_d3m0_fl4g}",
        "picoCTF{demo_buffer_overflow}",
    }
    assert vault.search("smb") != []
    assert vault.search("nmap") != []


def test_seed_demo_is_idempotent(vault: Vault) -> None:
    assert seed_demo(vault) == 6
    assert seed_demo(vault) == 0
    assert vault.stats().notes == 6
    assert vault.stats().folders == 3
