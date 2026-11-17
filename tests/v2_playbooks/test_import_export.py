from __future__ import annotations

import json

import pytest

from redscribe.v2.playbooks.catalog import PLAYBOOKS
from redscribe.v2.playbooks.errors import BundleError, VersionConflictError
from redscribe.v2.playbooks.import_export import (
    BUNDLE_KIND,
    BUNDLE_VERSION,
    build_bundle,
    canonical_json,
    checklist_from_dict,
    checksum,
    condition_from_dict,
    import_bundle,
    merge_bundles,
    playbook_from_dict,
    run_from_dict,
    snippet_from_dict,
    template_from_dict,
    validate_bundle,
    value_from_json,
    variable_from_dict,
    verify_checksum,
)
from redscribe.v2.playbooks.snippets import builtin_snippets
from redscribe.v2.playbooks.templates import builtin_templates
from redscribe.v2.playbooks.types import (
    ConditionOperator,
    RunStatus,
    StepStatus,
    VariableKind,
)


def _bundle(playbook: object) -> object:
    return build_bundle(
        (playbook,),
        builtin_snippets()[:2],
        builtin_templates()[:2],
        source="tests",
        exported_at="2026-03-01T00:00:00+00:00",
    )


def test_canonical_json_is_deterministic() -> None:
    first = {"b": 1, "a": [2, 3]}
    second = {"a": [2, 3], "b": 1}

    assert canonical_json(first) == canonical_json(second)
    assert checksum(first) == checksum(second)


def test_build_bundle_metadata_and_manifest(playbook: object) -> None:
    bundle = _bundle(playbook)

    assert bundle.kind == BUNDLE_KIND
    assert bundle.schema_version == BUNDLE_VERSION
    assert bundle.source == "tests"
    assert bundle.manifest == {
        "playbooks": 1,
        "snippets": 2,
        "templates": 2,
        "runs": 0,
        "keys": {
            "playbooks": [playbook.key],
            "snippets": sorted(item.key for item in builtin_snippets()[:2]),
            "templates": [item.key for item in builtin_templates()[:2]],
        },
    }
    assert bundle.checksum


def test_bundle_to_json_is_sorted(playbook: object) -> None:
    payload = _bundle(playbook).as_dict()
    encoded = _bundle(playbook).to_json(indent=None)

    assert list(json.loads(encoded)) == sorted(payload)
    assert verify_checksum(json.loads(encoded))


def test_validate_bundle_accepts_generated_bundle(playbook: object) -> None:
    assert validate_bundle(_bundle(playbook).as_dict()) == ()


def test_validate_bundle_rejects_non_object() -> None:
    assert validate_bundle([])[0].code == "invalid-bundle"


def test_validate_bundle_checks_kind_and_sections() -> None:
    issues = validate_bundle({"kind": "wrong", "playbooks": {}, "snippets": [], "templates": []})
    codes = {issue.code for issue in issues}

    assert {"invalid-kind", "unsupported-version", "invalid-section"}.issubset(codes)


def test_validate_bundle_warns_on_legacy_and_errors_on_future() -> None:
    legacy = validate_bundle({"kind": BUNDLE_KIND, "schema_version": "0.9"})
    future = validate_bundle({"kind": BUNDLE_KIND, "schema_version": "2.0"})

    assert legacy[0].severity == "warning"
    assert future[0].severity == "error"


def test_validate_bundle_checks_manifest_counts(playbook: object) -> None:
    payload = _bundle(playbook).as_dict()
    payload["manifest"]["playbooks"] = 9

    assert any(issue.code == "manifest-mismatch" for issue in validate_bundle(payload))


def test_verify_checksum_fails_without_or_with_bad_checksum(playbook: object) -> None:
    payload = _bundle(playbook).as_dict()
    without = dict(payload)
    without.pop("checksum")

    assert verify_checksum(without) is False
    assert verify_checksum({**payload, "checksum": "deadbeef"}) is False


def test_import_bundle_round_trips_playbook(playbook: object) -> None:
    payload = _bundle(playbook).as_dict()
    report = import_bundle(payload)

    assert report.ok
    assert report.playbooks[0].as_dict() == playbook.as_dict()
    snippet_keys = [item.key for item in report.snippets]
    assert snippet_keys == sorted(item.key for item in builtin_snippets()[:2])
    assert [item.key for item in report.templates] == [item.key for item in builtin_templates()[:2]]


def test_import_bundle_skip_reports_conflicts(playbook: object) -> None:
    report = import_bundle(
        _bundle(playbook).as_dict(),
        existing={"playbooks": {playbook.key}, "snippets": set(), "templates": set()},
    )

    assert report.playbooks == ()
    assert report.conflicts == (playbook.key,)
    assert report.ok


def test_import_bundle_rename_creates_unique_keys(playbook: object) -> None:
    present = {
        "playbooks": {playbook.key, f"{playbook.key}-import-2"},
        "snippets": set(),
        "templates": set(),
    }
    report = import_bundle(_bundle(playbook).as_dict(), strategy="rename", existing=present)

    assert report.playbooks[0].key == f"{playbook.key}-import-3"
    assert report.renamed == (f"{playbook.key}-import-3",)
    assert report.conflicts == ()


def test_import_bundle_replace_keeps_incoming_record(playbook: object) -> None:
    report = import_bundle(
        _bundle(playbook).as_dict(),
        strategy="replace",
        existing={"playbooks": {playbook.key}, "snippets": set(), "templates": set()},
    )

    assert report.playbooks[0].key == playbook.key


def test_import_bundle_rejects_unknown_strategy(playbook: object) -> None:
    with pytest.raises(BundleError, match="Unknown import strategy"):
        import_bundle(_bundle(playbook).as_dict(), strategy="overlay")


def test_import_bundle_rejects_invalid_bundle() -> None:
    with pytest.raises(BundleError, match="Bundle validation failed"):
        import_bundle({"kind": "other", "schema_version": "2.0"})


def test_import_bundle_rejects_checksum_mismatch(playbook: object) -> None:
    payload = _bundle(playbook).as_dict()
    payload["checksum"] = "0" * 64

    with pytest.raises(BundleError, match="checksum"):
        import_bundle(payload)


def test_import_bundle_warns_about_legacy_schema(playbook: object) -> None:
    payload = _bundle(playbook).as_dict()
    payload.pop("checksum")
    payload["schema_version"] = "0.9"
    report = import_bundle(payload)

    assert report.ok
    assert any(issue.code == "unsupported-version" for issue in report.issues)


def test_import_bundle_parses_runs(playbook: object) -> None:
    payload = _bundle(playbook).as_dict()
    payload.pop("checksum")
    payload["runs"] = [
        {
            "id": 7,
            "playbook_key": playbook.key,
            "version": playbook.version,
            "status": "running",
            "step_status": {"a": "done"},
            "values": {"target": "example.com"},
            "events": [{"seq": 1, "kind": "start", "message": "Started"}],
        }
    ]
    report = import_bundle(payload)

    assert report.runs[0].id == 7
    assert report.runs[0].status == RunStatus.RUNNING
    assert report.runs[0].step_status["a"] == StepStatus.DONE
    assert report.runs[0].values["target"] == "example.com"


def test_import_bundle_skips_invalid_runs(playbook: object) -> None:
    payload = _bundle(playbook).as_dict()
    payload.pop("checksum")
    payload["runs"] = [{"id": "broken"}]
    report = import_bundle(payload)

    assert report.runs == ()
    assert any(issue.code == "invalid-run" for issue in report.issues)


def test_merge_bundles_is_first_wins(playbook: object) -> None:
    first = _bundle(playbook)
    second = build_bundle(
        (playbook.with_changes(key="other", title="Other"),),
        (),
        (),
        source="other",
        exported_at="2026-03-02T00:00:00+00:00",
    )
    merged = merge_bundles(first, second)

    assert [item["key"] for item in merged.playbooks] == [playbook.key, "other"]
    assert merged.source == "merge"
    assert verify_checksum(merged.as_dict())


def test_merge_bundles_without_arguments_is_empty() -> None:
    merged = merge_bundles()

    assert merged.playbooks == ()
    assert merged.snippets == ()
    assert merged.manifest["playbooks"] == 0


@pytest.mark.parametrize(
    ("payload", "expected"),
    [("text", "text"), (5, 5), ([1, "a"], (1, "a")), (None, ""), ({"a": 1}, "{'a': 1}")],
)
def test_value_from_json(payload: object, expected: object) -> None:
    assert value_from_json(payload) == expected


def test_parsers_restore_variable_condition_and_checklist() -> None:
    variable = variable_from_dict(
        {"name": "level", "kind": "choice", "choices": ["low", "high"], "default": "low"}
    )
    condition = condition_from_dict({"field": "target", "operator": "contains", "value": "lab"})
    item = checklist_from_dict({"id": "c1", "label": "Check", "required": True})

    assert variable.kind == VariableKind.CHOICE
    assert variable.choices == ("low", "high")
    assert condition.operator == ConditionOperator.CONTAINS
    assert item.required is True


def test_parsers_restore_domain_records(playbook: object) -> None:
    data = playbook.as_dict()
    restored = playbook_from_dict(data)
    snippet = snippet_from_dict(builtin_snippets()[0].as_dict())
    template = template_from_dict(builtin_templates()[0].as_dict())

    assert restored.key == playbook.key
    assert len(restored.steps) == len(playbook.steps)
    assert snippet.key == builtin_snippets()[0].key
    assert template.key == builtin_templates()[0].key


def test_parsers_raise_bundle_errors_for_bad_payloads() -> None:
    with pytest.raises(BundleError):
        variable_from_dict("bad")
    with pytest.raises(BundleError):
        playbook_from_dict([])


def test_run_from_dict_rejects_future_step_version() -> None:
    with pytest.raises(VersionConflictError, match="Unsupported StepStatus"):
        run_from_dict({"id": 1, "step_status": {"a": "future"}})


def test_catalog_can_be_exported_as_one_bundle() -> None:
    bundle = build_bundle(
        PLAYBOOKS,
        builtin_snippets(),
        builtin_templates(),
        exported_at="2026-03-03T00:00:00+00:00",
    )

    assert len(bundle.playbooks) == len(PLAYBOOKS)
    assert validate_bundle(bundle.as_dict()) == ()
    assert verify_checksum(bundle.as_dict())
