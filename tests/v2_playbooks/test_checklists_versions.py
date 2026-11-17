from __future__ import annotations

import pytest

from redscribe.v2.playbooks.checklists import (
    ChecklistTracker,
    checklist_summary,
    merge_trackers,
    required_ids,
)
from redscribe.v2.playbooks.errors import InvalidStateError, VersionConflictError
from redscribe.v2.playbooks.types import ChecklistItem, Condition, ConditionOperator, Values
from redscribe.v2.playbooks.versions import (
    Version,
    VersionHistory,
    bump_version,
    diff_payloads,
    suggest_bump,
    versions_compatible,
)

ITEMS = (
    ChecklistItem(id="a", label="First"),
    ChecklistItem(id="b", label="Second", required=False),
    ChecklistItem(
        id="c",
        label="Third",
        condition=Condition(field="target", operator=ConditionOperator.EXISTS),
    ),
)


def test_checklist_tracker_initializes_pending_states() -> None:
    tracker = ChecklistTracker.from_items(ITEMS)

    assert tracker.state("a") == "pending"
    assert tracker.state("missing") == "pending"
    assert tracker.progress().total == 3
    assert tracker.progress().required_total == 2


def test_checklist_tracker_set_state_is_immutable() -> None:
    tracker = ChecklistTracker.from_items(ITEMS)
    done = tracker.set_state("a", "done")

    assert tracker.state("a") == "pending"
    assert done.state("a") == "done"


def test_checklist_tracker_toggle_and_note() -> None:
    tracker = ChecklistTracker.from_items(ITEMS)
    toggled = tracker.toggle("a").set_note("a", "verified")

    assert toggled.state("a") == "done"
    assert toggled.notes["a"] == "verified"
    assert toggled.toggle("a").state("a") == "pending"


def test_checklist_tracker_rejects_bad_states_and_items() -> None:
    tracker = ChecklistTracker.from_items(ITEMS)

    with pytest.raises(InvalidStateError, match="Unknown checklist state"):
        tracker.set_state("a", "bogus")

    with pytest.raises(InvalidStateError, match="Unknown checklist item"):
        tracker.set_state("missing", "done")


def test_checklist_tracker_applies_conditions() -> None:
    tracker = ChecklistTracker.from_items(ITEMS)
    blocked: Values = {}
    unblocked: Values = {"target": "example.com"}

    assert tracker.apply_conditions(blocked).state("c") == "blocked"

    visible = tracker.apply_conditions(blocked).apply_conditions(unblocked)
    assert visible.state("c") == "pending"


def test_checklist_tracker_preserves_done_items_when_conditions_change() -> None:
    tracker = ChecklistTracker.from_items(ITEMS).set_state("c", "done")

    assert tracker.apply_conditions({}).state("c") == "done"


def test_checklist_progress_counts_all_states() -> None:
    tracker = ChecklistTracker.from_items(ITEMS)
    tracker = tracker.set_state("a", "done").set_state("b", "skipped").set_state("c", "blocked")
    progress = tracker.progress()

    assert progress.done == 1
    assert progress.skipped == 1
    assert progress.blocked == 1
    assert progress.required_done == 1
    assert progress.percent == 33
    assert progress.complete is False


def test_checklist_progress_is_complete_when_required_items_settle() -> None:
    tracker = ChecklistTracker.from_items(ITEMS)
    tracker = tracker.set_state("a", "done").set_state("c", "skipped")
    progress = tracker.progress()

    assert progress.complete is True
    assert tracker.incomplete_required() == ()


def test_checklist_tracker_empty_progress_is_complete() -> None:
    progress = ChecklistTracker().progress()

    assert progress.percent == 100
    assert progress.complete is True


def test_checklist_visible_items_orders_pending_first() -> None:
    tracker = ChecklistTracker.from_items(ITEMS).set_state("a", "done")

    assert [item.id for item in tracker.visible_items()] == ["b", "c", "a"]


def test_checklist_from_dict_reads_states_and_notes() -> None:
    tracker = ChecklistTracker.from_dict(
        {"states": {"a": "done"}, "notes": {"a": "ok"}}, items=ITEMS
    )

    assert tracker.state("a") == "done"
    assert tracker.notes["a"] == "ok"


def test_checklist_as_dict_contains_progress_and_items() -> None:
    data = ChecklistTracker.from_items(ITEMS).as_dict()

    assert data["progress"]["total"] == 3
    assert [item["id"] for item in data["items"]] == ["a", "b", "c"]


def test_merge_trackers_prefers_settled_primary_states() -> None:
    primary = ChecklistTracker.from_items(ITEMS, state={"a": "done"})
    secondary = ChecklistTracker.from_items(ITEMS, state={"a": "pending", "b": "skipped"})
    merged = merge_trackers(primary, secondary)

    assert merged.state("a") == "done"
    assert merged.state("b") == "skipped"
    assert merged.state("c") == "pending"


def test_required_ids_and_checklist_summary() -> None:
    assert required_ids(ITEMS) == ("a", "c")
    assert checklist_summary(ITEMS) == {
        "total": 3,
        "required": 2,
        "item_ids": ["a", "b", "c"],
    }


def test_version_parse_and_compare() -> None:
    assert str(Version.parse("v1.2.3")) == "1.2.3"
    assert Version.parse("1.2.3") < Version.parse("1.3.0")
    assert Version.parse("2.0.0") > Version.parse("1.9.9")


def test_version_parse_rejects_bad_versions() -> None:
    with pytest.raises(VersionConflictError):
        Version.parse("1.2")


@pytest.mark.parametrize(
    ("part", "expected"),
    [("major", "2.0.0"), ("minor", "1.3.0"), ("patch", "1.2.4")],
)
def test_bump_version(part: str, expected: str) -> None:
    assert bump_version("1.2.3", part) == expected


def test_bump_version_rejects_unknown_part() -> None:
    with pytest.raises(VersionConflictError):
        bump_version("1.2.3", "epoch")


def test_versions_compatible_shares_major_series() -> None:
    assert versions_compatible("1.2.3", "1.9.0")
    assert not versions_compatible("1.2.3", "2.0.0")


def test_version_history_append_and_changelog() -> None:
    history = VersionHistory("playbook")
    history = history.append("1.0.0", "Initial", author="alice", checksum="abc")
    history = history.append("1.1.0", "Added step")

    assert history.versions == ("1.0.0", "1.1.0")
    assert history.latest.version == "1.1.0"
    assert history.changelog()[0]["author"] == "alice"
    assert history.as_dict()["key"] == "playbook"


def test_version_history_rejects_non_increasing_versions() -> None:
    history = VersionHistory("playbook").append("1.1.0")

    with pytest.raises(VersionConflictError):
        history.append("1.0.0")


def test_version_history_between_and_entry() -> None:
    history = VersionHistory("playbook")
    history = history.append("1.0.0").append("1.1.0").append("2.0.0")

    assert [item.version for item in history.between("1.0.0", "1.1.0")] == ["1.0.0", "1.1.0"]
    assert history.entry("1.1.0").message == ""
    assert history.entry("9.9.9") is None


def test_version_history_from_dict_roundtrip() -> None:
    history = VersionHistory("playbook").append("1.0.0", "Initial", checksum="abc")
    restored = VersionHistory.from_dict(history.as_dict())

    assert restored.key == "playbook"
    assert restored.versions == ("1.0.0",)
    assert restored.latest.checksum == "abc"


def test_diff_payloads_reports_added_removed_and_changed_fields() -> None:
    differences = diff_payloads(
        {"title": "Old", "steps": [1], "remove": True},
        {"title": "New", "steps": [2], "added": 1},
    )

    assert [(item.path, item.kind) for item in differences] == [
        ("added", "added"),
        ("remove", "removed"),
        ("steps", "changed"),
        ("title", "changed"),
    ]


def test_diff_payloads_ignores_identical_values() -> None:
    assert diff_payloads({"a": [1, 2]}, {"a": [1, 2]}) == ()


def test_suggest_bump_uses_change_shape() -> None:
    history = VersionHistory("playbook").append("1.2.3")
    changes = diff_payloads({}, {"steps": []})

    assert suggest_bump(history, ()) == "patch"
    assert suggest_bump(history, changes) == "minor"
