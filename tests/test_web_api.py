from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable
from typing import Any

import pytest

from redscribe import __version__
from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api, ApiError, WebOverrides
from redscribe.ui.web.api_contract import (
    CONTRACT_VERSION,
    CONTRACTS,
    MAX_CONTENT_LENGTH,
    MAX_SHORT_LENGTH,
    MAX_SNIPPET_COMMAND_LENGTH,
    MAX_SNIPPET_DESCRIPTION_LENGTH,
    MAX_TAG_LENGTH,
    MAX_TITLE_LENGTH,
    ApiErrorCode,
    ContractError,
    FieldKind,
    contract_counts,
    describe_api,
    validate_call,
)


def test_api_covers_core_routes(vault: Vault) -> None:
    api = Api(vault, WebOverrides(theme="light", font_size=15))

    boot = api.handle("boot", {})
    assert boot["theme"] == "light"
    assert boot["font_size"] == 15
    assert api.handle("tree", {}) == []
    assert api.handle("templates", {})
    assert api.handle("flag_patterns", {})

    folder = api.handle("create_folder", {"title": "Web"})
    note = api.handle(
        "create_note",
        {
            "title": "SAML",
            "template_key": "ctf",
            "parent_id": folder["id"],
            "target": "example.com",
        },
    )
    assert api.handle("node", {"id": folder["id"]})["children"]
    assert api.handle("node", {"id": note["id"]})["content"]

    api.handle(
        "update_node",
        {
            "id": note["id"],
            "tags": "web, saml",
            "status": "active",
            "difficulty": "medium",
            "flag": "flag{x}",
            "target": "target.tld",
        },
    )
    api.handle("save_content", {"id": note["id"], "content": "# body\n[link](missing)"})
    api.handle("set_pinned", {"id": note["id"], "pinned": True})
    assert api.handle("pinned_notes", {})
    assert api.handle("recent_notes", {"limit": 5})
    assert api.handle("stats", {})
    assert api.handle("search", {"query": "body"})
    assert api.handle("quick_jump", {"query": "SAML"})
    assert api.handle("render_preview", {"content": "# hi"})["html"]
    assert api.handle("graph", {})["nodes"]
    assert api.handle("backlinks", {"id": note["id"]})
    assert api.handle("timeline", {"folder_id": folder["id"], "limit": 5})
    assert api.handle("tag_counts", {})
    assert api.handle("notes_tagged", {"tag": "web"})
    assert api.handle("collected_flags", {})
    assert api.handle("flag_insights", {})

    assert api.handle("list_snippets", {})
    assert api.handle("search_snippets", {"query": "curl"})
    assert api.handle("resolve_snippet", {"command": "curl {{target}}", "target": "x"})
    snippet = api.handle(
        "create_snippet",
        {"title": "Mine", "command": "echo {{target}}", "description": "d", "tags": "x"},
    )
    api.handle("update_snippet", {**snippet, "title": "Renamed"})
    api.handle("delete_snippet", {"id": snippet["id"]})

    assert api.handle("export_note_markdown", {"id": note["id"]})["mime"] == "text/markdown"
    assert api.handle("export_note_html", {"id": note["id"]})["mime"] == "text/html"
    assert api.handle("export_vault_html", {})["filename"]
    assert api.handle("backup_vault", {})["filename"]
    assert api.handle("rebuild_search_index", {}) == {"rebuilt": True}
    assert api.handle("quick_capture", {"content": "captured line"})["title"] == "captured line"

    versions = api.handle("list_versions", {"id": note["id"]})
    assert versions
    assert api.handle("get_version", {"version_id": versions[0]["id"]})
    assert api.handle("restore_version", {"version_id": versions[0]["id"]})

    api.handle(
        "set_settings",
        {
            "theme": "dark",
            "font_size": 14,
            "view_mode": "preview",
            "last_template": "blank",
            "last_note": note["id"],
            "sidebar_width": 300,
            "split_sash": 50,
            "tree_expanded": str(folder["id"]),
            "restore_last_note": True,
            "sync_preview_scroll": "off",
        },
    )
    assert api.handle("get_settings", {})["theme"] == "dark"

    duplicate = api.handle("duplicate_node", {"id": note["id"]})
    api.handle("reorder_node", {"id": duplicate["id"], "offset": -1})
    api.handle("move_node", {"id": duplicate["id"], "parent_id": folder["id"]})
    assert api.handle("trash_node", {"id": duplicate["id"]}) == {"removed": 1}
    assert api.handle("trashed_nodes", {})
    assert api.handle("restore_node", {"id": duplicate["id"]})
    assert api.handle("empty_trash", {})["removed"] == 0


@pytest.mark.parametrize(
    ("method", "body"),
    [
        ("missing", {}),
        ("create_folder", {"title": "x" * 201}),
        ("node", {}),
        ("create_note", {"title": "x" * 201}),
        ("rename", {"id": 1, "title": " "}),
        ("update_node", {"id": 1, "status": "nope"}),
        ("update_node", {"id": 1, "difficulty": "nope"}),
        ("update_node", {"id": 1}),
        ("save_content", {"id": 1, "content": 5}),
        ("set_pinned", {"id": 1, "pinned": "yes"}),
        ("quick_jump", {"query": 5}),
        ("notes_tagged", {}),
        ("backlinks", {"id": "x"}),
        ("search_snippets", {}),
        ("create_snippet", {"title": "x", "command": "y", "tags": "z" * 501}),
        ("delete_snippet", {"id": 999}),
        ("render_preview", {}),
        ("set_settings", {"unknown": 1}),
        ("set_settings", {"font_size": 99}),
        ("set_settings", {"theme": "blue"}),
        ("set_settings", {"view_mode": "wide"}),
        ("set_settings", {"last_template": "nope"}),
        ("set_settings", {"tree_expanded": "abc"}),
        ("export_note_markdown", {"id": 999}),
        ("get_version", {"version_id": 999}),
    ],
)
def test_api_rejects_bad_requests(vault: Vault, method: str, body: dict[str, Any]) -> None:
    api = Api(vault)
    with pytest.raises(ApiError):
        api.handle(method, body)


def test_api_reports_missing_nodes(vault: Vault) -> None:
    api = Api(vault)
    with pytest.raises(ApiError) as error:
        api.handle("node", {"id": 999})
    assert error.value.status == 404


def _error_of(call: Callable[[], Any]) -> tuple[str, int]:
    with pytest.raises(ApiError) as error:
        call()
    return error.value.message, error.value.status


_INVALID_CALLS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("missing", {}),
    ("node", {}),
    ("node", {"id": "x"}),
    ("create_folder", {"title": "x" * (MAX_TITLE_LENGTH + 1)}),
    ("rename", {"id": 1}),
    ("update_node", {"id": 1, "status": "nope"}),
    ("update_node", {"id": 1, "difficulty": "nope"}),
    ("save_content", {"id": 1, "content": 5}),
    ("set_pinned", {"id": 1, "pinned": 1}),
    ("search", {}),
    ("quick_jump", {"query": 5}),
    ("notes_tagged", {}),
    ("backlinks", {"id": "x"}),
    ("search_snippets", {}),
    ("create_snippet", {"title": "x", "command": "y", "tags": "z" * (MAX_TAG_LENGTH + 1)}),
    ("render_preview", {}),
    ("set_settings", {"unknown": 1}),
    ("set_settings", {"font_size": 99}),
    ("set_settings", {"theme": "blue"}),
    ("set_settings", {"view_mode": "wide"}),
    ("set_settings", {"last_template": "nope"}),
    ("set_settings", {"tree_expanded": "abc"}),
    ("export_note_markdown", {"id": 999}),
    ("get_version", {"version_id": 999}),
)


@pytest.mark.parametrize(("method", "body"), _INVALID_CALLS)
def test_dispatch_preserves_direct_error_wire_shape(
    vault: Vault, method: str, body: dict[str, Any]
) -> None:
    api = Api(vault)
    route = api._routes.get(method)
    if route is None:
        direct = (f"Unknown API method '{method}'", 404)
    else:
        direct = _error_of(lambda: route(body))
    dispatched = _error_of(lambda: api.handle(method, body))
    assert dispatched == direct


def test_dispatch_passes_the_original_body_to_the_route(vault: Vault) -> None:
    api = Api(vault)
    seen: dict[str, Any] = {}
    original = api._routes["boot"]

    def capture(body: dict[str, Any]) -> dict[str, Any]:
        seen.update(body)
        return original(body)

    api._routes["boot"] = capture
    api.handle("boot", {"extra": 1})
    assert seen == {"extra": 1}


def test_contract_registry_covers_every_dispatch_route(vault: Vault) -> None:
    api = Api(vault)
    assert set(CONTRACTS) == set(api._routes)
    assert list(CONTRACTS) == [contract.name for contract in CONTRACTS.values()]


def test_error_codes_have_stable_wire_values() -> None:
    assert {code.name: code.value for code in ApiErrorCode} == {
        "UNKNOWN_METHOD": "unknown_method",
        "MISSING_FIELD": "missing_field",
        "INVALID_TYPE": "invalid_type",
        "INVALID_CHOICE": "invalid_choice",
        "FIELD_TOO_LONG": "field_too_long",
        "UNKNOWN_KEYS": "unknown_keys",
        "NOT_FOUND": "not_found",
        "INVALID_STATE": "invalid_state",
        "INTERNAL": "internal",
    }


def test_field_kinds_have_stable_wire_values() -> None:
    assert {kind.name: kind.value for kind in FieldKind} == {
        "STRING": "string",
        "INTEGER": "integer",
        "BOOLEAN": "boolean",
        "CHOICE": "choice",
        "ANY": "any",
    }


def test_contract_counts_match_the_registry() -> None:
    counts = contract_counts()
    fields = [spec for contract in CONTRACTS.values() for spec in contract.fields]
    assert counts == {
        "methods": len(CONTRACTS),
        "fields": len(fields),
        "required_fields": sum(1 for spec in fields if spec.required),
        "error_codes": len(list(ApiErrorCode)),
    }


def test_describe_api_is_complete_and_json_serializable() -> None:
    schema = describe_api()
    assert schema["version"] == CONTRACT_VERSION
    assert schema["application_version"] == __version__
    assert schema["counts"] == contract_counts()
    assert schema["error_codes"] == [code.value for code in ApiErrorCode]
    assert set(schema["methods"]) == set(CONTRACTS)
    assert json.loads(json.dumps(schema)) == schema


def test_describe_api_is_repeatable() -> None:
    assert describe_api() == describe_api()


@pytest.mark.parametrize("method", sorted(CONTRACTS))
def test_describe_api_documents_each_contract(method: str) -> None:
    entry = describe_api()["methods"][method]
    assert entry["name"] == method
    assert entry["summary"]
    assert isinstance(entry["allow_unknown"], bool)
    assert all(code in {item.value for item in ApiErrorCode} for code in entry["errors"])
    for field in entry["fields"]:
        assert set(field) == {
            "name",
            "kind",
            "required",
            "default",
            "nullable",
            "max_length",
            "choices",
            "description",
        }
        assert field["kind"] in {kind.value for kind in FieldKind}


def test_contract_specs_are_frozen() -> None:
    spec = CONTRACTS["search"].fields[0]
    assert dataclasses.is_dataclass(spec)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.name = "changed"
    with pytest.raises(dataclasses.FrozenInstanceError):
        CONTRACTS["search"].summary = "changed"


@pytest.mark.parametrize(
    ("method", "body", "expected"),
    [
        ("boot", {}, {}),
        ("node", {"id": 3}, {"id": 3}),
        ("create_note", {}, {"template_key": "blank", "title": "", "target": ""}),
        ("create_folder", {"title": "Web"}, {"title": "Web"}),
        ("rename", {"id": 1}, {"id": 1, "title": ""}),
        ("update_node", {"id": 1}, {"id": 1}),
        ("recent_notes", {"limit": None}, {}),
        ("recent_notes", {"limit": 5}, {"limit": 5}),
        ("move_node", {"id": 1, "parent_id": None, "before_id": 2}, {"id": 1, "before_id": 2}),
        ("resolve_snippet", {"command": "x"}, {"command": "x", "target": ""}),
        (
            "quick_capture",
            {"content": "x"},
            {"title": "", "content": "x", "tags": "", "target": ""},
        ),
        ("set_settings", {}, {}),
        ("api_schema", {"extra": 1}, {}),
        ("search_snippets", {"query": "x", "limit": None}, {"query": "x"}),
    ],
)
def test_validate_call_accepts_valid_bodies(
    method: str, body: dict[str, Any], expected: dict[str, Any]
) -> None:
    original = dict(body)
    assert validate_call(method, body) == expected
    assert body == original


@pytest.mark.parametrize(
    ("method", "body", "code", "message", "field"),
    [
        ("search", {}, ApiErrorCode.MISSING_FIELD, "Missing 'query'", "query"),
        ("node", {}, ApiErrorCode.INVALID_TYPE, "'id' must be an integer", "id"),
        ("node", {"id": True}, ApiErrorCode.INVALID_TYPE, "'id' must be an integer", "id"),
        ("node", {"id": "x"}, ApiErrorCode.INVALID_TYPE, "'id' must be an integer", "id"),
        (
            "set_pinned",
            {"id": 1},
            ApiErrorCode.INVALID_TYPE,
            "'pinned' must be a boolean",
            "pinned",
        ),
        (
            "set_pinned",
            {"id": 1, "pinned": 1},
            ApiErrorCode.INVALID_TYPE,
            "'pinned' must be a boolean",
            "pinned",
        ),
        (
            "create_folder",
            {"title": "x" * (MAX_TITLE_LENGTH + 1)},
            ApiErrorCode.FIELD_TOO_LONG,
            f"title exceeds {MAX_TITLE_LENGTH} characters",
            "title",
        ),
        (
            "save_content",
            {"id": 1, "content": 5},
            ApiErrorCode.INVALID_TYPE,
            "'content' must be a string",
            "content",
        ),
        (
            "update_node",
            {"id": 1, "status": "nope"},
            ApiErrorCode.INVALID_CHOICE,
            "Unknown status: nope",
            "status",
        ),
        (
            "update_node",
            {"id": 1, "difficulty": "nope"},
            ApiErrorCode.INVALID_CHOICE,
            "Unknown difficulty: nope",
            "difficulty",
        ),
        (
            "set_settings",
            {"unknown": 1},
            ApiErrorCode.UNKNOWN_KEYS,
            "Unsupported setting keys: unknown",
            None,
        ),
        (
            "set_settings",
            {"alpha": 1, "beta": 2},
            ApiErrorCode.UNKNOWN_KEYS,
            "Unsupported setting keys: alpha, beta",
            None,
        ),
        ("nope", {}, ApiErrorCode.UNKNOWN_METHOD, "Unknown API method 'nope'", None),
    ],
)
def test_validate_call_reports_stable_contract_failures(
    method: str,
    body: dict[str, Any],
    code: ApiErrorCode,
    message: str,
    field: str | None,
) -> None:
    with pytest.raises(ContractError) as error:
        validate_call(method, body)
    assert error.value.code is code
    assert error.value.message == message
    assert error.value.field == field
    assert error.value.status == (404 if code is ApiErrorCode.UNKNOWN_METHOD else 400)
    assert str(error.value) == message


@pytest.mark.parametrize(
    ("method", "body", "message"),
    [
        ("search", {}, "Missing 'query'"),
        ("node", {}, "'id' must be an integer"),
        ("set_pinned", {"id": 1}, "'pinned' must be a boolean"),
        ("create_folder", {"title": "x" * 201}, "title exceeds 200 characters"),
        ("update_node", {"id": 1, "status": "nope"}, "Unknown status: nope"),
        ("set_settings", {"unknown": 1}, "Unsupported setting keys: unknown"),
        ("missing", {}, "Unknown API method 'missing'"),
    ],
)
def test_dispatch_surfaces_contract_failures_as_api_errors(
    vault: Vault, method: str, body: dict[str, Any], message: str
) -> None:
    api = Api(vault)
    with pytest.raises(ApiError, match=re.escape(message)) as error:
        api.handle(method, body)
    assert error.value.status == (404 if method == "missing" else 400)


def test_dispatch_exposes_stable_error_codes(vault: Vault) -> None:
    api = Api(vault)
    with pytest.raises(ApiError) as unknown:
        api.handle("no_such_method", {})
    assert unknown.value.code is ApiErrorCode.UNKNOWN_METHOD
    with pytest.raises(ApiError) as missing:
        api.handle("search", {})
    assert missing.value.code is ApiErrorCode.MISSING_FIELD
    with pytest.raises(ApiError) as invalid:
        api.handle("set_settings", {"unknown": 1})
    assert invalid.value.code is ApiErrorCode.UNKNOWN_KEYS
    with pytest.raises(ApiError) as route_error:
        api.handle("node", {"id": 999})
    assert route_error.value.code is None


def test_api_health_reports_runtime_and_contract_metadata(vault: Vault) -> None:
    api = Api(vault)
    health = api.handle("api_health", {})
    assert health == api.api_health({})
    assert health["ok"] is True
    assert health["version"] == __version__
    assert health["contract_version"] == CONTRACT_VERSION
    assert health["counts"] == contract_counts()
    assert health["counts"]["methods"] == len(CONTRACTS)
    assert health["counts"]["fields"] > health["counts"]["methods"]


def test_api_schema_returns_the_published_contract(vault: Vault) -> None:
    api = Api(vault)
    schema = api.handle("api_schema", {})
    assert schema == describe_api()
    assert schema == api.api_schema({})
    assert schema["version"] == CONTRACT_VERSION
    assert json.loads(json.dumps(schema)) == schema


@pytest.mark.parametrize(
    "method",
    [
        "boot",
        "tree",
        "trashed_nodes",
        "pinned_notes",
        "stats",
        "collected_flags",
        "flag_patterns",
        "flag_insights",
        "tag_counts",
        "graph",
        "templates",
        "list_snippets",
        "get_settings",
        "export_vault_html",
        "api_health",
        "api_schema",
    ],
)
def test_fieldless_methods_accept_an_empty_body(vault: Vault, method: str) -> None:
    assert CONTRACTS[method].fields == ()
    assert validate_call(method, {}) == {}
    assert Api(vault).handle(method, {}) is not None


@pytest.mark.parametrize(
    ("method", "body"),
    [
        ("create_folder", {"parent_id": None}),
        ("recent_notes", {"limit": None}),
        ("timeline", {"folder_id": None, "limit": None}),
        ("search_snippets", {"query": "curl", "limit": None}),
    ],
)
def test_nullable_fields_accept_null(vault: Vault, method: str, body: dict[str, Any]) -> None:
    validate_call(method, body)
    assert (
        Api(vault).handle(method, {"title": "ok", **body} if method == "create_folder" else body)
        is not None
    )


_LENGTH_BASE_BODIES: dict[str, dict[str, Any]] = {
    "create_snippet": {"title": "t", "command": "c"},
}


def _length_test_body(method: str, field: str, length: int) -> dict[str, Any]:
    body: dict[str, Any] = dict(_LENGTH_BASE_BODIES.get(method, {"id": 1}))
    body[field] = "x" * length
    return body


@pytest.mark.parametrize(
    ("method", "field", "length"),
    [
        ("create_folder", "title", MAX_TITLE_LENGTH),
        ("create_snippet", "title", MAX_TITLE_LENGTH),
        ("create_snippet", "command", MAX_SNIPPET_COMMAND_LENGTH),
        ("create_snippet", "description", MAX_SNIPPET_DESCRIPTION_LENGTH),
        ("create_snippet", "tags", MAX_TAG_LENGTH),
        ("quick_capture", "target", MAX_SHORT_LENGTH),
        ("save_content", "content", MAX_CONTENT_LENGTH),
    ],
)
def test_contract_length_limits_match_declared_constants(
    method: str, field: str, length: int
) -> None:
    spec = next(item for item in CONTRACTS[method].fields if item.name == field)
    assert spec.max_length == length
    assert validate_call(method, _length_test_body(method, field, length))[field] == "x" * length


@pytest.mark.parametrize(
    ("method", "field", "length"),
    [
        ("create_folder", "title", MAX_TITLE_LENGTH),
        ("create_note", "title", MAX_TITLE_LENGTH),
        ("create_snippet", "title", MAX_TITLE_LENGTH),
        ("create_snippet", "command", MAX_SNIPPET_COMMAND_LENGTH),
        ("create_snippet", "description", MAX_SNIPPET_DESCRIPTION_LENGTH),
        ("create_snippet", "tags", MAX_TAG_LENGTH),
        ("quick_capture", "title", MAX_TITLE_LENGTH),
        ("quick_capture", "tags", MAX_TAG_LENGTH),
        ("quick_capture", "target", MAX_SHORT_LENGTH),
    ],
)
def test_contract_rejects_fields_beyond_their_limit(method: str, field: str, length: int) -> None:
    body = _length_test_body(method, field, length + 1)
    with pytest.raises(ContractError) as error:
        validate_call(method, body)
    assert error.value.code is ApiErrorCode.FIELD_TOO_LONG
    assert error.value.message == f"{field} exceeds {length} characters"


def test_id_fields_reject_booleans_even_though_bool_is_an_int() -> None:
    for method in ("node", "rename", "duplicate_node", "delete_snippet", "get_version"):
        field = "version_id" if method == "get_version" else "id"
        with pytest.raises(ContractError) as error:
            validate_call(method, {field: True})
        assert error.value.code is ApiErrorCode.INVALID_TYPE


def test_set_settings_is_the_only_strict_key_contract() -> None:
    assert [name for name, contract in CONTRACTS.items() if not contract.allow_unknown] == [
        "set_settings"
    ]
    assert {spec.name for spec in CONTRACTS["set_settings"].fields} == {
        "theme",
        "font_size",
        "last_template",
        "view_mode",
        "restore_last_note",
        "sync_preview_scroll",
        "sidebar_width",
        "split_sash",
        "last_note",
        "tree_expanded",
    }
