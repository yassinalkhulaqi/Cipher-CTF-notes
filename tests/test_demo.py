from __future__ import annotations

from pathlib import Path

import pytest

from redscribe.services.demo import (
    DEMO_NOTES,
    DEMO_SNIPPETS,
    demo_fingerprint,
    demo_manifest,
    seed_demo,
    seeded_notes,
)
from redscribe.storage.db import Vault


def test_seed_demo_populates_an_empty_vault(vault: Vault) -> None:
    assert seed_demo(vault) == 6
    stats = vault.stats()
    assert stats.notes == 6
    assert stats.folders == 3
    assert stats.flags == 2
    assert stats.targets == 3
    assert stats.tags == 15
    assert stats.pinned == 2
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


def test_manifest_is_stable_and_describes_fixtures() -> None:
    manifest = demo_manifest()
    assert manifest == demo_manifest()
    assert manifest.fingerprint == demo_fingerprint()
    assert len(manifest.fingerprint) == 16
    assert manifest.slugs == tuple(note.slug for note in DEMO_NOTES)
    assert manifest.titles == tuple(note.title for note in DEMO_NOTES)
    assert manifest.snippet_count == len(DEMO_SNIPPETS) == 1
    assert manifest.profiles["full"] == ("ctf", "engagements", "cheatsheets")
    assert len(set(manifest.slugs)) == len(DEMO_NOTES)


@pytest.mark.parametrize(
    ("profile", "notes", "folders"),
    [
        ("full", 6, 3),
        ("ctf", 2, 1),
        ("engagement", 2, 1),
        ("cheatsheets", 2, 1),
    ],
)
def test_seed_demo_profiles(profile: str, notes: int, folders: int, tmp_path: Path) -> None:
    with Vault(tmp_path / f"{profile}.db") as vault:
        assert seed_demo(vault, profile=profile) == notes
        stats = vault.stats()
        assert stats.notes == notes
        assert stats.folders == folders
        assert len(vault.list_custom_snippets()) == 1
        assert seed_demo(vault, profile=profile) == 0


def test_seed_demo_rejects_unknown_profile(vault: Vault) -> None:
    with pytest.raises(ValueError, match="Unknown demo profile: missing"):
        seed_demo(vault, profile="missing")


def test_seeded_notes_are_deterministic() -> None:
    first = seeded_notes(42)
    second = seeded_notes(42)
    assert first == second
    assert seeded_notes(43) != first
    assert len(first) == 3
    assert len({note.slug for note in first}) == 3
    assert all(note.folder == "ctf" for note in first)
    assert all(note.status in ("todo", "active", "done") for note in first)
    assert all(note.difficulty in ("easy", "medium", "hard") for note in first)
    assert all("fixture" in note.tags for note in first)
    assert all(note.target.startswith("10.10.") for note in first)
    assert seeded_notes(0, count=0) == ()
    with pytest.raises(ValueError, match="Fixture count cannot be negative"):
        seeded_notes(1, count=-1)
    with pytest.raises(ValueError, match="Unknown demo folder: missing"):
        seeded_notes(1, folder="missing")


def test_seed_demo_with_seed_adds_reproducible_notes(tmp_path: Path) -> None:
    titles: list[list[str]] = []
    for name in ("first", "second"):
        with Vault(tmp_path / f"{name}.db") as vault:
            assert seed_demo(vault, profile="ctf", seed=17) == 5
            assert vault.stats().notes == 5
            assert vault.stats().folders == 1
            titles.append([node.title for node in vault.iter_notes()])
    assert titles[0] == titles[1]
    assert sum(1 for title in titles[0] if title.startswith("Seeded ")) == 3
