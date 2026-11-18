from __future__ import annotations

from typing import Any

import pytest

from redscribe.v2.engagements.models import (
    Engagement,
    Finding,
    FindingStatus,
    Severity,
    Target,
)
from redscribe.v2.engagements.repositories import (
    SNAPSHOT_VERSION,
    EngagementStore,
    Repository,
    RepositoryError,
    seed_demo,
)


def test_repository_add_assigns_sequential_ids(target_factory: Any) -> None:
    repository: Repository[Target] = Repository("targets", Target)
    first = repository.add(target_factory(id=0, value="first.test"))
    second = repository.add(target_factory(id=0, value="second.test"))
    assert (first.id, second.id) == (1, 2)
    assert repository.next_id == 3
    assert [item.id for item in repository.all()] == [1, 2]


def test_repository_add_rejects_duplicate_and_nonpositive_ids(target_factory: Any) -> None:
    repository: Repository[Target] = Repository("targets", Target)
    repository.add(target_factory(id=0))
    with pytest.raises(RepositoryError, match="already exists"):
        repository.add(target_factory(id=0), entity_id=1)
    with pytest.raises(RepositoryError, match="positive"):
        repository.add(target_factory(id=0), entity_id=0)
    assert repository.count() == 1


def test_repository_add_with_explicit_id_advances_sequence(target_factory: Any) -> None:
    repository: Repository[Target] = Repository("targets", Target)
    repository.add(target_factory(id=0), entity_id=7)
    assert repository.next_id == 8
    assert repository.add(target_factory(id=0)).id == 8


def test_repository_get_require_exists_and_count(target_factory: Any) -> None:
    repository: Repository[Target] = Repository("targets", Target)
    assert repository.get(1) is None
    assert repository.exists(1) is False
    with pytest.raises(RepositoryError, match="targets 1 does not exist"):
        repository.require(1)
    stored = repository.add(target_factory(id=0))
    assert repository.get(stored.id) is stored
    assert repository.exists(stored.id) is True
    assert repository.count() == 1


def test_repository_where_first_where_and_filter_by_engagement(target_factory: Any) -> None:
    repository: Repository[Target] = Repository("targets", Target)
    first = repository.add(target_factory(id=0, engagement_id=1, value="a.test"))
    repository.add(target_factory(id=0, engagement_id=2, value="b.test"))
    assert [item.id for item in repository.where(lambda item: item.engagement_id == 1)] == [
        first.id
    ]
    assert repository.first_where(lambda item: item.value == "a.test") is not None
    assert repository.first_where(lambda item: item.value == "missing") is None
    assert [item.id for item in repository.filter_by_engagement(1)] == [1]


def test_repository_update_replaces_from_serialized_snapshot(target_factory: Any) -> None:
    repository: Repository[Target] = Repository("targets", Target)
    stored = repository.add(target_factory(id=0))
    updated = repository.update(stored.id, {"name": "Renamed", "id": 999})
    assert updated.id == stored.id
    assert updated.name == "Renamed"
    assert repository.get(stored.id) is updated
    assert len(repository.all()) == 1


def test_repository_delete_and_clear(target_factory: Any) -> None:
    repository: Repository[Target] = Repository("targets", Target)
    first = repository.add(target_factory(id=0))
    repository.add(target_factory(id=0))
    assert repository.delete(first.id).id == first.id
    with pytest.raises(RepositoryError):
        repository.delete(first.id)
    repository.clear()
    assert repository.count() == 0
    assert repository.next_id == 1


def test_repository_snapshot_and_restore_roundtrip(target_factory: Any) -> None:
    repository: Repository[Target] = Repository("targets", Target)
    repository.add(target_factory(id=0, value="a.test"))
    repository.add(target_factory(id=0, value="b.test"))
    snapshot = repository.snapshot()
    assert [item["id"] for item in snapshot] == [1, 2]
    replacement: Repository[Target] = Repository("targets", Target)
    replacement.restore(snapshot)
    assert replacement.snapshot() == snapshot
    assert replacement.next_id == 3


def test_engagement_store_restore_ignores_non_mapping_values(engagement_factory: Any) -> None:
    store = EngagementStore()
    store.restore(
        {
            "version": SNAPSHOT_VERSION,
            "repositories": {"engagements": [engagement_factory(id=1).as_dict(), None, 7]},
        }
    )
    assert store.engagements.count() == 1


def test_engagement_store_owns_all_repositories() -> None:
    store = EngagementStore()
    names = set(store.repositories())
    assert names == {
        "engagements",
        "scope_rules",
        "targets",
        "assets",
        "services",
        "credentials",
        "findings",
        "activities",
    }
    assert store.stats() == dict.fromkeys(names, 0)


def test_engagement_store_snapshot_has_version_and_sections(engagement_factory: Any) -> None:
    store = EngagementStore()
    store.engagements.add(engagement_factory(id=0))
    snapshot = store.snapshot()
    assert snapshot["version"] == SNAPSHOT_VERSION
    assert set(snapshot["repositories"]) == set(store.repositories())
    assert len(snapshot["repositories"]["engagements"]) == 1


def test_engagement_store_restore_roundtrip(engagement_factory: Any, target_factory: Any) -> None:
    store = EngagementStore()
    store.engagements.add(engagement_factory(id=0))
    store.targets.add(target_factory(id=0, engagement_id=1))
    snapshot = store.snapshot()
    replacement = EngagementStore()
    replacement.restore(snapshot)
    assert replacement.snapshot() == snapshot


def test_engagement_store_restore_rejects_bad_version() -> None:
    store = EngagementStore()
    with pytest.raises(RepositoryError, match="Unsupported engagement snapshot version"):
        store.restore({"version": 999, "repositories": {}})


def test_engagement_store_restore_rejects_missing_repositories() -> None:
    store = EngagementStore()
    with pytest.raises(RepositoryError, match="missing repositories"):
        store.restore({"version": SNAPSHOT_VERSION})
    with pytest.raises(RepositoryError, match="Invalid snapshot section"):
        store.restore({"version": SNAPSHOT_VERSION, "repositories": {"findings": {}}})


def test_engagement_store_save_and_load_roundtrip(tmp_path: Any, engagement_factory: Any) -> None:
    store = EngagementStore()
    store.engagements.add(engagement_factory(id=0))
    path = tmp_path / "snapshots" / "engagements.json"
    store.save(path)
    assert path.exists()
    assert "version" in path.read_text(encoding="utf-8")
    replacement = EngagementStore()
    replacement.load(path)
    assert replacement.snapshot() == store.snapshot()


def test_engagement_store_load_rejects_missing_and_malformed_files(tmp_path: Any) -> None:
    store = EngagementStore()
    with pytest.raises(RepositoryError, match="Cannot read engagement snapshot"):
        store.load(tmp_path / "missing.json")
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(RepositoryError, match="must be an object"):
        store.load(bad)


def test_seed_demo_creates_related_records() -> None:
    store = EngagementStore()
    engagement = seed_demo(store)
    assert engagement.id == 1
    assert engagement.key == "demo-engagement"
    stats = store.stats()
    assert stats["engagements"] == 1
    assert stats["targets"] == 1
    assert stats["assets"] == 1
    assert stats["services"] == 1
    assert stats["findings"] == 1
    assert store.targets.get(1) is not None
    assert store.findings.get(1) is not None


def test_engagement_store_clear_resets_all_sequences(engagement_factory: Any) -> None:
    store = EngagementStore()
    store.engagements.add(engagement_factory(id=0))
    store.engagements.add(engagement_factory(id=0, key="second"))
    store.clear()
    assert store.stats() == dict.fromkeys(store.repositories(), 0)
    assert all(repository.next_id == 1 for repository in store.repositories().values())


def test_finding_repository_preserves_enums(finding_factory: Any) -> None:
    repository: Repository[Finding] = Repository("findings", Finding)
    stored = repository.add(
        finding_factory(id=0, severity=Severity.CRITICAL, status=FindingStatus.OPEN)
    )
    assert stored.severity is Severity.CRITICAL
    assert stored.status is FindingStatus.OPEN
    assert repository.snapshot()[0]["severity"] == "critical"


def test_engagement_repository_is_generic_over_models(engagement_factory: Any) -> None:
    repository: Repository[Engagement] = Repository("engagements", Engagement)
    stored = repository.add(engagement_factory(id=0))
    assert stored.display_name == "Test Engagement"
    assert isinstance(repository.all()[0], Engagement)
