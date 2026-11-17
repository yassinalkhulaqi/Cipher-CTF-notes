from __future__ import annotations

from typing import Any

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api, ApiError
from redscribe.ui.web.api_contract import (
    CONTRACTS,
    MAX_CONTENT_LENGTH,
    MAX_SHORT_LENGTH,
    MAX_TAG_LENGTH,
    MAX_TITLE_LENGTH,
    ApiErrorCode,
    ContractError,
    FieldKind,
    describe_api,
    validate_call,
)


def test_quick_capture_creates_a_note_with_content(vault: Vault) -> None:
    api = Api(vault)

    created = api.quick_capture(
        {
            "title": "Found a weak endpoint",
            "content": "GET /api/user/1 without auth",
            "target": "app.acme.test",
            "tags": "web, idor",
        }
    )

    assert created["title"] == "Found a weak endpoint"
    assert created["target"] == "app.acme.test"
    assert created["tag_list"] == ["web", "idor"]
    node = vault.get_node(created["id"])
    assert node is not None
    assert node.content == "GET /api/user/1 without auth"


def test_quick_capture_falls_back_to_the_first_content_line(vault: Vault) -> None:
    api = Api(vault)

    created = api.quick_capture({"content": "nmap -sC -sV -p- 10.10.10.42"})

    assert created["title"] == "nmap -sC -sV -p- 10.10.10.42"
    node = vault.get_node(created["id"])
    assert node is not None
    assert node.content == "nmap -sC -sV -p- 10.10.10.42"


def test_quick_capture_rejects_empty_input(vault: Vault) -> None:
    api = Api(vault)

    with pytest.raises(ApiError):
        api.quick_capture({"title": "  ", "content": ""})


def test_quick_capture_through_the_dispatcher(vault: Vault) -> None:
    api = Api(vault)

    created = api.handle("quick_capture", {"content": "SAML request"})

    assert created["title"] == "SAML request"


def test_quick_capture_contract_describes_every_field() -> None:
    contract = CONTRACTS["quick_capture"]
    assert {spec.name: spec.kind for spec in contract.fields} == {
        "title": FieldKind.STRING,
        "content": FieldKind.STRING,
        "tags": FieldKind.STRING,
        "target": FieldKind.STRING,
    }
    assert all(not spec.required for spec in contract.fields)
    assert all(spec.default == "" for spec in contract.fields)
    assert {spec.name: spec.max_length for spec in contract.fields} == {
        "title": MAX_TITLE_LENGTH,
        "content": MAX_CONTENT_LENGTH,
        "tags": MAX_TAG_LENGTH,
        "target": MAX_SHORT_LENGTH,
    }
    assert describe_api()["methods"]["quick_capture"]["name"] == "quick_capture"


def test_quick_capture_contract_normalizes_defaults() -> None:
    assert validate_call("quick_capture", {"content": "body"}) == {
        "title": "",
        "content": "body",
        "tags": "",
        "target": "",
    }
    assert validate_call("quick_capture", {}) == {
        "title": "",
        "content": "",
        "tags": "",
        "target": "",
    }


@pytest.mark.parametrize(
    "field",
    ["title", "content", "tags", "target"],
)
def test_quick_capture_rejects_non_string_fields(field: str) -> None:
    with pytest.raises(ContractError) as error:
        validate_call("quick_capture", {field: 42})
    assert error.value.code is ApiErrorCode.INVALID_TYPE
    assert error.value.message == f"'{field}' must be a string"
    assert error.value.field == field


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("title", MAX_TITLE_LENGTH),
        ("content", MAX_CONTENT_LENGTH),
        ("tags", MAX_TAG_LENGTH),
        ("target", MAX_SHORT_LENGTH),
    ],
)
def test_quick_capture_enforces_length_limits_through_the_dispatcher(
    vault: Vault, field: str, limit: int
) -> None:
    api = Api(vault)
    assert validate_call("quick_capture", {field: "x" * limit})
    with pytest.raises(ApiError) as error:
        api.handle("quick_capture", {field: "x" * (limit + 1)})
    assert error.value.message == f"{field} exceeds {limit} characters"
    assert error.value.status == 400


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"title": 1}, "'title' must be a string"),
        ({"content": None}, "'content' must be a string"),
        ({"title": "t", "content": "c", "tags": []}, "'tags' must be a string"),
        ({"title": "t", "content": "c", "target": True}, "'target' must be a string"),
    ],
)
def test_quick_capture_dispatch_errors_match_direct_calls(
    vault: Vault, body: dict[str, Any], message: str
) -> None:
    api = Api(vault)
    with pytest.raises(ApiError) as direct:
        api.quick_capture(body)
    with pytest.raises(ApiError) as dispatched:
        api.handle("quick_capture", body)
    assert direct.value.message == dispatched.value.message == message
    assert direct.value.status == dispatched.value.status == 400


def test_quick_capture_preserves_explicit_title_and_empty_content(vault: Vault) -> None:
    api = Api(vault)
    created = api.handle("quick_capture", {"title": "Protocol notes", "content": ""})
    node = vault.get_node(created["id"])
    assert node is not None
    assert created["title"] == "Protocol notes"
    assert node.content == ""
    assert created["path"] == ""
    assert created["trashed"] is False


def test_quick_capture_accepts_nullable_free_optional_fields(vault: Vault) -> None:
    api = Api(vault)
    created = api.handle(
        "quick_capture",
        {"title": "Capture", "content": "line", "tags": "", "target": "host.test"},
    )
    assert created["tag_list"] == []
    assert created["target"] == "host.test"
    assert vault.get_node(created["id"]) is not None
