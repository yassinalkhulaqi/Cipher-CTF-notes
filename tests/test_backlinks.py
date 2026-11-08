from __future__ import annotations

import pytest

from redscribe.services.graph import (
    backlinks_for,
    build_timeline,
    note_links,
    note_links_payload,
)
from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api, ApiError


def test_backlinks_finds_notes_linking_to_target(vault: Vault) -> None:
    target = vault.create_node("HTB Corporate", content="flag{...}")
    source = vault.create_node("Writeup", content="See [[HTB Corporate]] for scope.")

    links = note_links(vault, target.id)

    assert len(links.backlinks) == 1
    assert links.backlinks[0].node_id == source.id
    assert links.backlinks[0].snippet
    out = backlinks_for(vault, target.id)
    assert [item.node_id for item in out] == [source.id]


def test_backlinks_ignore_self_and_trashed_notes(vault: Vault) -> None:
    note = vault.create_node("Alpha", content="[[Alpha]] self link")
    trashed = vault.create_node("Gone", content="[[Alpha]] was here")
    vault.delete_node(trashed.id, permanent=False)

    links = note_links(vault, note.id)

    assert links.backlinks == ()
    assert links.outlinks == ()


def test_outlinks_resolve_and_dedupe(vault: Vault) -> None:
    target = vault.create_node("Beta", content="flag{...}")
    source = vault.create_node("Writeup", content="[[Beta]] then [[Beta|again]]")

    links = note_links(vault, source.id)

    assert len(links.outlinks) == 1
    assert links.outlinks[0].node_id == target.id
    assert links.outlinks[0].alias == ""


def test_unresolved_wikilinks_are_reported(vault: Vault) -> None:
    note = vault.create_node("Writeup", content="Remember [[Missing Note]] someday.")

    links = note_links(vault, note.id)

    assert len(links.unresolved) == 1
    assert links.unresolved[0].target == "Missing Note"


def test_note_links_rejects_missing_note(vault: Vault) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        note_links(vault, 9999)


def test_note_links_for_folder_is_empty(vault: Vault) -> None:
    folder = vault.create_node("CTF", kind="folder")
    vault.create_node("Writeup", folder.id, content="[[CTF]]")

    links = note_links(vault, folder.id)

    assert links.backlinks == ()
    assert links.outlinks == ()
    assert links.unresolved == ()


def test_note_links_payload_serializes(vault: Vault) -> None:
    target = vault.create_node("Target", content="flag{...}")
    vault.create_node("Source", content="[[Target]]")

    payload = note_links_payload(note_links(vault, target.id))

    assert set(payload) == {"backlinks", "outlinks", "unresolved"}
    assert payload["backlinks"][0]["title"] == "Source"


def test_timeline_orders_newest_first(vault: Vault) -> None:
    first = vault.create_node("First", content="one")
    second = vault.create_node("Second", content="two")

    events = build_timeline(vault)

    assert events[0].node_id == second.id
    assert events[0].activity == "created"
    assert any(event.node_id == first.id for event in events)
    assert events[-1].node_id == first.id


def test_timeline_scopes_to_folder_subtree(vault: Vault) -> None:
    folder = vault.create_node("Engagement", kind="folder")
    inside = vault.create_node("Inside", folder.id, content="flag{...}")
    vault.create_node("Outside", content="flag{...}")

    events = build_timeline(vault, folder_id=folder.id)

    ids = {event.node_id for event in events}
    assert inside.id in ids
    assert folder.id in ids
    assert all(event.path.startswith("Engagement") or event.title == "Engagement" for event in events)


def test_timeline_rejects_missing_folder(vault: Vault) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        build_timeline(vault, folder_id=9999)


def test_timeline_respects_limit(vault: Vault) -> None:
    for index in range(5):
        vault.create_node(f"Note {index}", content=f"content {index}")

    events = build_timeline(vault, limit=2)

    assert len(events) == 2


def test_api_backlinks_returns_note_links(vault: Vault) -> None:
    api = Api(vault)
    target = vault.create_node("Target", content="flag{...}")
    vault.create_node("Source", content="[[Target]]")

    payload = api.backlinks({"id": target.id})

    assert set(payload) == {"backlinks", "outlinks", "unresolved"}
    assert payload["backlinks"][0]["title"] == "Source"


def test_api_backlinks_missing_note_is_api_error(vault: Vault) -> None:
    api = Api(vault)

    with pytest.raises(ApiError):
        api.backlinks({"id": 9999})


def test_api_timeline_returns_events(vault: Vault) -> None:
    api = Api(vault)
    vault.create_node("Writeup", content="flag{...}")

    events = api.timeline({})

    assert events
    assert events[0]["title"] == "Writeup"
    assert events[0]["activity"] == "created"
