"""Tests for three-way merge, field diffs, and conflict reason codes."""

from __future__ import annotations

import pytest

from redscribe.v3.entities.types import EntityId, EntityLink, LinkKind
from redscribe.v3.portability.errors import ResolutionError
from redscribe.v3.portability.merge import (
    ConflictReason,
    MergeResult,
    ResolutionChoice,
    ResolutionStrategy,
    apply_resolution,
    detect_vector_regressions,
    group_conflicts_by_reason,
    merge_families,
    merge_links,
    require_choice,
    suggest_for,
    three_way_merge,
)
from redscribe.v3.portability.records import PortableEntity
from redscribe.v3.portability.vectors import VersionVector
from tests.v3_portability.conftest import make_entity


def edit(source: PortableEntity, **fields: object) -> PortableEntity:
    """Return a new snapshot with explicit edits and a bumped vector."""
    vector = {"alpha": source.vector.get("alpha") + 1}
    return source.apply_fields(fields, vector=VersionVector(vector))  # type: ignore[arg-type]


def link(source: str, target: str, *, label: str = "") -> EntityLink:
    """Build a typed link for merge tests."""
    return EntityLink(
        source=EntityId.parse(source),
        target=EntityId.parse(target),
        kind=LinkKind.RELATES,
        label=label,
    )


def test_fast_forward_when_local_changed() -> None:
    base = make_entity("note:1", title="Base")
    local = edit(base, title="Local")
    outcome = three_way_merge("note:1", base, local, base)
    assert outcome.status == "applied"
    assert outcome.entity is not None
    assert outcome.entity.title == "Local"
    assert outcome.conflict is None


def test_fast_forward_when_remote_changed() -> None:
    base = make_entity("note:1", title="Base")
    remote = edit(base, title="Remote")
    outcome = three_way_merge("note:1", base, base, remote)
    assert outcome.status == "applied"
    assert outcome.entity is not None
    assert outcome.entity.title == "Remote"


def test_unchanged_on_both_sides() -> None:
    base = make_entity("note:1")
    outcome = three_way_merge("note:1", base, base, base)
    assert outcome.status == "unchanged"
    assert outcome.entity is base
    assert outcome.conflict is None


def test_identical_concurrent_edits_are_accepted() -> None:
    base = make_entity("note:1", title="Base")
    left = edit(base, title="Same")
    right = edit(base, title="Same")
    outcome = three_way_merge("note:1", base, left, right)
    assert outcome.status == "applied"
    assert outcome.entity is not None
    assert outcome.entity.title == "Same"


def test_disjoint_field_edits_auto_merge() -> None:
    base = make_entity("note:1", title="Base", body="base body")
    local = edit(base, title="Local title")
    remote = edit(base, body="remote body")
    outcome = three_way_merge("note:1", base, local, remote)
    assert outcome.status == "applied"
    assert outcome.entity is not None
    assert outcome.entity.title == "Local title"
    assert outcome.entity.body == "remote body"
    assert outcome.entity.vector.as_dict() == {"alpha": 2}


def test_body_edits_are_content_conflicts() -> None:
    base = make_entity("note:1", body="base")
    local = edit(base, body="local body")
    remote = edit(base, body="remote body")
    outcome = three_way_merge("note:1", base, local, remote)
    assert outcome.status == "conflict"
    assert outcome.conflict is not None
    assert outcome.conflict.reason is ConflictReason.CONTENT_DIVERGENCE
    assert [field.field for field in outcome.conflict.fields] == ["body"]
    assert "both devices" in outcome.conflict.message.lower()


def test_tag_edits_are_tag_conflicts() -> None:
    base = make_entity("note:1", tags=("one",))
    local = edit(base, tags=("one", "local"))
    remote = edit(base, tags=("one", "remote"))
    outcome = three_way_merge("note:1", base, local, remote)
    assert outcome.conflict is not None
    assert outcome.conflict.reason is ConflictReason.TAG_SET_DIVERGENCE


def test_title_edits_are_field_conflicts() -> None:
    base = make_entity("note:1", title="Base")
    local = edit(base, title="Local")
    remote = edit(base, title="Remote")
    outcome = three_way_merge("note:1", base, local, remote)
    assert outcome.conflict is not None
    assert outcome.conflict.reason is ConflictReason.FIELD_BOTH_EDITED
    assert outcome.conflict.severity == "error"


def test_delete_modify_conflict_local_deleted() -> None:
    base = make_entity("note:1", title="Base")
    local = edit(base, deleted=True)
    remote = edit(base, title="Remote")
    outcome = three_way_merge("note:1", base, local, remote)
    assert outcome.conflict is not None
    assert outcome.conflict.reason is ConflictReason.DELETE_MODIFY
    assert outcome.conflict.suggestion is ResolutionChoice.KEEP_REMOTE


def test_delete_modify_conflict_remote_deleted() -> None:
    base = make_entity("note:1", title="Base")
    local = edit(base, title="Local")
    remote = edit(base, deleted=True)
    outcome = three_way_merge("note:1", base, local, remote)
    assert outcome.conflict is not None
    assert outcome.conflict.reason is ConflictReason.DELETE_MODIFY
    assert outcome.conflict.suggestion is ResolutionChoice.KEEP_LOCAL


def test_both_deleted_is_unchanged() -> None:
    base = make_entity("note:1")
    deleted_local = edit(base, deleted=True)
    deleted_remote = edit(base, deleted=True)
    outcome = three_way_merge("note:1", base, deleted_local, deleted_remote)
    assert outcome.status == "applied"
    assert outcome.entity is not None
    assert outcome.entity.deleted
    assert outcome.conflict is None


def test_concurrent_add_is_conflict() -> None:
    local = make_entity("note:dup", title="Local version")
    remote = make_entity("note:dup", title="Remote version", vector={"beta": 1})
    outcome = three_way_merge("note:dup", None, local, remote)
    assert outcome.conflict is not None
    assert outcome.conflict.reason is ConflictReason.CONCURRENT_ADD
    assert outcome.conflict.severity == "critical"


def test_single_side_add_is_applied() -> None:
    local = make_entity("note:new")
    assert three_way_merge("note:new", None, local, None).entity is local
    remote = make_entity("note:remote")
    assert three_way_merge("note:remote", None, None, remote).entity is remote


def test_merge_families_groups_by_family() -> None:
    note = make_entity("note:1", title="Base")
    finding = make_entity("finding:1", title="Finding")
    result = merge_families((note,), (note,), (edit(note, title="Local"), finding))
    assert result.clean
    assert any(entity.ref == "finding:1" for entity in result.entities)
    assert set(result.families) == {"finding", "note"}


def test_merge_families_can_filter_families() -> None:
    note = make_entity("note:1")
    finding = make_entity("finding:1")
    result = merge_families((note, finding), (note, finding), (note, finding), families=("note",))
    assert [entity.ref for entity in result.entities] == ["note:1"]


def test_merge_links_fast_forward_and_conflict() -> None:
    base_link = link("note:1", "finding:1", label="base")
    local_link = link("note:1", "finding:1", label="local")
    remote_link = link("note:1", "finding:1", label="remote")
    links, conflicts = merge_links(
        (base_link,),
        (local_link,),
        (base_link,),
        valid_refs=frozenset({"note:1", "finding:1"}),
    )
    assert links == (local_link,)
    assert conflicts == ()
    _, conflicts = merge_links(
        (base_link,),
        (local_link,),
        (remote_link,),
        valid_refs=frozenset({"note:1", "finding:1"}),
    )
    assert conflicts[0].reason is ConflictReason.FIELD_BOTH_EDITED


def test_merge_links_reports_missing_endpoint() -> None:
    dangling = link("note:1", "finding:missing")
    links, conflicts = merge_links((), (dangling,), (), valid_refs=frozenset({"note:1"}))
    assert links == ()
    assert conflicts[0].reason is ConflictReason.LINK_TARGET_MISSING
    assert "finding:missing" in conflicts[0].detail


def test_merge_result_counts_and_serialization() -> None:
    base = make_entity("note:1", title="Base")
    result = merge_families((base,), (base,), (edit(base, title="Remote"),))
    assert result.counts()["entities"] == 1
    assert result.counts()["applied"] == 1
    payload = result.as_dict()
    assert payload["conflicts"] == []
    assert payload["entities"][0]["record"]["entity_id"] == "note:1"


def test_group_conflicts_by_reason() -> None:
    base = make_entity("note:1", body="base")
    local = edit(base, body="local")
    remote = edit(base, body="remote")
    result = merge_families((base,), (local,), (remote,))
    groups = group_conflicts_by_reason(result.conflicts)
    assert list(groups) == [ConflictReason.CONTENT_DIVERGENCE]
    assert len(groups[ConflictReason.CONTENT_DIVERGENCE]) == 1


def test_suggest_for_strategies() -> None:
    conflict = three_way_merge(
        "note:1",
        make_entity("note:1", title="Base"),
        edit(make_entity("note:1", title="Base"), title="Local"),
        edit(make_entity("note:1", title="Base"), title="Remote"),
    ).conflict
    assert conflict is not None
    assert suggest_for(conflict, ResolutionStrategy.KEEP_LOCAL) is ResolutionChoice.KEEP_LOCAL
    assert suggest_for(conflict, ResolutionStrategy.KEEP_REMOTE) is ResolutionChoice.KEEP_REMOTE
    assert suggest_for(conflict, ResolutionStrategy.SKIP) is ResolutionChoice.SKIP
    assert suggest_for(conflict, ResolutionStrategy.MERGE_FIELDS) is ResolutionChoice.MERGE_FIELDS
    assert suggest_for(conflict) is ResolutionChoice.MANUAL


def test_require_choice_rejects_invalid_decisions() -> None:
    conflict = three_way_merge(
        "note:1",
        make_entity("note:1", title="Base"),
        edit(make_entity("note:1", title="Base"), title="Local"),
        edit(make_entity("note:1", title="Base"), title="Remote"),
    ).conflict
    assert conflict is not None
    with pytest.raises(ResolutionError):
        require_choice(conflict, ResolutionChoice.MANUAL)
    base = make_entity("note:2", title="Base")
    no_local = three_way_merge("note:2", base, None, edit(base, title="Remote")).conflict
    assert no_local is not None
    with pytest.raises(ResolutionError):
        require_choice(no_local, ResolutionChoice.KEEP_LOCAL)


def test_apply_resolution_keep_local_and_remote() -> None:
    base = make_entity("note:1", title="Base")
    result = merge_families((base,), (edit(base, title="Local"),), (edit(base, title="Remote"),))
    conflict = result.conflicts[0]
    local_result = apply_resolution(result, conflict, ResolutionChoice.KEEP_LOCAL)
    remote_result = apply_resolution(result, conflict, ResolutionChoice.KEEP_REMOTE)
    assert local_result.clean
    assert remote_result.clean
    assert local_result.entities[0].title == "Local"
    assert remote_result.entities[0].title == "Remote"
    assert local_result.counts()["applied"] == 1


def test_apply_resolution_merge_fields_and_skip() -> None:
    base = make_entity("note:1", title="Base")
    result = merge_families((base,), (edit(base, title="Local"),), (edit(base, title="Remote"),))
    conflict = result.conflicts[0]
    merged = apply_resolution(result, conflict, ResolutionChoice.MERGE_FIELDS)
    assert merged.clean
    assert merged.entities[0].title == "Local"
    skipped = apply_resolution(result, conflict, ResolutionChoice.SKIP)
    assert skipped.clean
    assert skipped.entities == ()
    assert skipped.counts()["unchanged"] == 1


def test_detect_vector_regressions() -> None:
    base = VersionVector({"alpha": 2, "beta": 1})
    local = VersionVector({"alpha": 3, "beta": 1})
    remote = VersionVector({"alpha": 1})
    conflicts = detect_vector_regressions(base, local, remote)
    assert len(conflicts) == 1
    assert conflicts[0].reason is ConflictReason.VECTOR_REGRESSION
    assert conflicts[0].suggestion is ResolutionChoice.KEEP_LOCAL


def test_merge_result_default_is_clean() -> None:
    result = MergeResult()
    assert result.clean
    assert result.counts()["entities"] == 0
