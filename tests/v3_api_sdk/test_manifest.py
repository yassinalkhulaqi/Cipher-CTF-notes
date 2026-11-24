"""Manifest schema validation, data-only invariant, and store behavior."""

from __future__ import annotations

import json
from typing import Any

import pytest

from redscribe.v3.api.errors import V3Error
from redscribe.v3.api.pagination import decode_cursor
from redscribe.v3.api_sdk.errors import ManifestError
from redscribe.v3.api_sdk.manifest import (
    SCHEMA_ID,
    Contribution,
    ExtensionManifest,
    ManifestStore,
    example_manifest,
    manifest_schema,
    parse_manifest,
    validate_manifest,
)


def test_example_manifest_is_valid_and_fresh() -> None:
    first = example_manifest()
    second = example_manifest()
    assert first is not second
    report = validate_manifest(first)
    assert report.valid
    assert report.errors == ()
    assert report.normalized is not None
    assert report.fingerprint.startswith('"')
    assert report.as_dict()["issues"] == []


def test_manifest_requires_core_fields() -> None:
    report = validate_manifest({"schema": SCHEMA_ID})
    codes = {issue.code for issue in report.errors}
    paths = {issue.path for issue in report.errors}
    assert "missing_field" in codes
    assert ".id" in paths
    assert ".version" in paths
    assert ".title" in paths
    assert not report.valid


def test_manifest_rejects_non_mapping_input() -> None:
    report = validate_manifest(["not", "an", "object"])
    assert not report.valid
    assert report.issues[0].code == "invalid_type"


def test_manifest_rejects_code_execution_keys() -> None:
    document = example_manifest()
    document["metadata"] = {"code": "print(1)"}
    report = validate_manifest(document)
    assert not report.valid
    assert any(issue.code == "forbidden_key" for issue in report.errors)
    assert any(issue.path.endswith("code") for issue in report.errors)

    nested = example_manifest()
    nested["contributions"][0]["handler"] = "fn"
    report = validate_manifest(nested)
    assert any(issue.code == "unknown_field" for issue in report.errors)
    assert any(issue.code == "forbidden_key" and "handler" in issue.path for issue in report.errors)


def test_manifest_rejects_non_json_values() -> None:
    document = example_manifest()
    document["metadata"] = {"bad": {1, 2, 3}}
    report = validate_manifest(document)
    assert not report.valid
    assert any(issue.code == "not_data_only" for issue in report.errors)


def test_manifest_validates_identifier_version_and_schema() -> None:
    document = example_manifest()
    document["id"] = "Bad ID!"
    document["version"] = "latest"
    document["schema"] = "other/9"
    report = validate_manifest(document)
    codes = {issue.code for issue in report.errors}
    assert "invalid_choice" in codes


def test_manifest_validates_requirements() -> None:
    document = example_manifest()
    document["requires"] = ["extensions", "not_a_capability"]
    report = validate_manifest(document)
    assert not report.valid
    assert any(issue.code == "unknown_capability" for issue in report.errors)
    document["requires"] = "extensions"
    report = validate_manifest(document)
    assert any(issue.code == "invalid_type" for issue in report.errors)


def test_manifest_validates_contributions() -> None:
    document = example_manifest()
    document["contributions"] = [{"kind": "unknown", "id": "x", "title": "X"}]
    report = validate_manifest(document)
    assert any(issue.code == "invalid_choice" for issue in report.errors)

    document = example_manifest()
    document["contributions"][0]["location"] = "nowhere"
    report = validate_manifest(document)
    assert any("location" in issue.path for issue in report.errors)

    document = example_manifest()
    document["contributions"][2]["binding"] = "eval()"
    report = validate_manifest(document)
    assert any("binding" in issue.path for issue in report.errors)

    document = example_manifest()
    document["contributions"].append(dict(document["contributions"][0]))
    report = validate_manifest(document)
    assert any(issue.code == "conflict" for issue in report.errors)


def test_manifest_requires_at_least_one_contribution() -> None:
    document = example_manifest()
    document["contributions"] = []
    report = validate_manifest(document)
    assert any(issue.code == "missing_field" for issue in report.errors)


def test_manifest_enforces_limits() -> None:
    document = example_manifest()
    document["summary"] = "x" * 5000
    report = validate_manifest(document)
    assert any(issue.code == "field_too_long" for issue in report.errors)
    document = example_manifest()
    document["contributions"] = [
        {"kind": "command", "id": f"cmd-{index}", "title": "C"} for index in range(40)
    ]
    report = validate_manifest(document)
    assert any(issue.code == "field_too_long" for issue in report.errors)


def test_manifest_schema_descriptor_is_data_only() -> None:
    schema = manifest_schema()
    assert schema["data_only"] is True
    assert schema["executes_code"] is False
    assert "code" in schema["forbidden_keys"]
    assert "panel" in schema["contribution_kinds"]
    assert schema["limits"]["max_contributions"] == 32
    assert json.loads(json.dumps(schema)) == schema


def test_parse_manifest_builds_typed_models() -> None:
    manifest = parse_manifest(example_manifest())
    assert isinstance(manifest, ExtensionManifest)
    assert manifest.id == "example.panel"
    assert manifest.requires == ("extensions",)
    assert all(isinstance(item, Contribution) for item in manifest.contributions)
    assert manifest.contributions[0].attributes["location"] == "sidebar"
    assert manifest.fingerprint == validate_manifest(example_manifest()).fingerprint
    assert manifest.as_dict()["schema"] == SCHEMA_ID


def test_parse_manifest_raises_on_invalid_document() -> None:
    with pytest.raises(ManifestError) as excinfo:
        parse_manifest({})
    assert excinfo.value.field == "manifest"
    assert "Invalid extension manifest" in excinfo.value.message


def test_manifest_store_install_get_list_and_idempotency() -> None:
    store = ManifestStore()
    manifest = parse_manifest(example_manifest())
    _installed, replaced = store.install(manifest)
    assert not replaced
    assert store.size() == 1
    assert store.revision == 1
    assert store.contains("example.panel")

    _again, replaced = store.install(manifest)
    assert not replaced
    assert store.revision == 1

    changed = parse_manifest({**example_manifest(), "title": "Renamed"})
    updated, replaced = store.install(changed)
    assert replaced
    assert store.revision == 2
    assert store.get("example.panel").title == "Renamed"
    assert store.identifiers() == ("example.panel",)
    assert store.list()[0] == updated
    assert store.summaries()[0]["id"] == "example.panel"
    assert store.summaries(["extensions"])[0]["matched"] is True
    assert store.summaries(["i18n"])[0]["matched"] is False


def test_manifest_store_etag_preconditions_and_removal() -> None:
    store = ManifestStore()
    manifest = parse_manifest(example_manifest())
    with pytest.raises(V3Error):
        store.get("example.panel")
    store.install(manifest)
    with pytest.raises(V3Error) as excinfo:
        store.install(manifest, expected_etag='"stale"')
    assert excinfo.value.status == 412
    removed = store.remove("example.panel", expected_etag=manifest.fingerprint)
    assert removed.id == "example.panel"
    assert store.size() == 0
    with pytest.raises(V3Error):
        store.remove("example.panel")
    store.install(manifest)
    store.clear()
    assert store.revision == 4


def test_manifest_store_uses_b00_cursor_pagination() -> None:
    store = ManifestStore()
    for index in range(5):
        document = example_manifest()
        document["id"] = f"ext.{index:02d}"
        store.install(parse_manifest(document))
    items, meta, cursor = store.page(0, 2)
    assert len(items) == 2
    assert meta.has_next
    assert decode_cursor(cursor).offset == 2
    tail, tail_meta, tail_cursor = store.page(4, 2)
    assert len(tail) == 1
    assert not tail_meta.has_next
    assert tail_cursor == ""


def test_manifest_document_can_round_trip_json() -> None:
    document: dict[str, Any] = example_manifest()
    encoded = json.dumps(document, sort_keys=True)
    assert json.loads(encoded) == document
