from __future__ import annotations

import pytest

from redscribe.services.graph import (
    TimelineEvent,
    backlinks_for,
    build_timeline,
    group_timeline,
    note_links,
    note_links_payload,
    timeline_activity,
    timeline_group_payload,
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
    assert all(
        event.path.startswith("Engagement") or event.title == "Engagement" for event in events
    )


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


def _event(title: str, at: str, *, activity: str = "updated") -> TimelineEvent:
    return TimelineEvent(node_id=len(title), title=title, at=at, activity=activity)


def test_group_timeline_by_day_keeps_newest_group_first() -> None:
    events = (
        _event("New", "2026-11-17T09:00:00+00:00"),
        _event("Same day", "2026-11-17T08:00:00+00:00"),
        _event("Old", "2026-11-16T22:00:00+00:00"),
    )

    groups = group_timeline(events)

    assert [group.key for group in groups] == ["2026-11-17", "2026-11-16"]
    assert [group.label for group in groups] == ["2026-11-17", "2026-11-16"]
    assert [event.title for event in groups[0].events] == ["New", "Same day"]
    assert [event.title for event in groups[1].events] == ["Old"]


def test_group_timeline_by_week_uses_iso_weeks() -> None:
    events = (
        _event("Sunday", "2026-01-04T12:00:00+00:00"),
        _event("Thursday", "2026-01-01T12:00:00+00:00"),
        _event("Next week", "2026-01-05T12:00:00+00:00"),
    )

    groups = group_timeline(events, period="week")

    assert [group.key for group in groups] == ["2026-W01", "2026-W02"]
    assert len(groups[0].events) == 2


def test_group_timeline_by_month() -> None:
    events = (
        _event("November", "2026-11-01T00:00:00+00:00"),
        _event("October late", "2026-10-31T23:00:00+00:00"),
        _event("October early", "2026-10-02T01:00:00+00:00"),
    )

    groups = group_timeline(events, period="month")

    assert [group.key for group in groups] == ["2026-11", "2026-10"]
    assert [event.title for event in groups[1].events] == ["October late", "October early"]


def test_group_timeline_collects_undated_events() -> None:
    events = (_event("Known", "2026-11-17T00:00:00Z"), _event("Unknown", ""))

    groups = group_timeline(events)

    assert groups[-1].key == "unknown"
    assert groups[-1].label == "Undated"
    assert groups[-1].events[0].title == "Unknown"


def test_group_timeline_handles_empty_and_invalid_periods() -> None:
    assert group_timeline(()) == ()
    with pytest.raises(ValueError, match="Unknown timeline period"):
        group_timeline((), period="year")


def test_group_timeline_accepts_vault_events(vault: Vault) -> None:
    vault.create_node("First")
    vault.create_node("Second")
    events = build_timeline(vault)

    groups = group_timeline(events)

    assert len(groups) == 1
    assert len(groups[0].events) == 2


def test_timeline_activity_counts_activities() -> None:
    events = (
        _event("One", "2026-11-17T00:00:00Z", activity="created"),
        _event("Two", "2026-11-17T00:00:00Z", activity="updated"),
        _event("Three", "2026-11-17T00:00:00Z", activity="other"),
    )

    assert timeline_activity(events) == {"created": 1, "updated": 1}


def test_timeline_group_payload_serializes_buckets() -> None:
    events = (
        _event("One", "2026-11-17T00:00:00Z", activity="created"),
        _event("Two", "2026-11-16T00:00:00Z"),
    )

    payload = timeline_group_payload(group_timeline(events))

    assert [entry["key"] for entry in payload] == ["2026-11-17", "2026-11-16"]
    assert payload[0]["count"] == 1
    assert payload[0]["events"][0]["title"] == "One"
    assert payload[0]["events"][0]["activity"] == "created"
