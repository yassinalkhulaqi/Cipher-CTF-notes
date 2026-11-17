from __future__ import annotations

from typing import Any

import pytest

from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api, ApiError
from redscribe.ui.web.api_contract import (
    CONTRACTS,
    MAX_SNIPPET_COMMAND_LENGTH,
    MAX_SNIPPET_DESCRIPTION_LENGTH,
    MAX_TAG_LENGTH,
    MAX_TITLE_LENGTH,
    ApiErrorCode,
    ContractError,
    FieldKind,
    describe_api,
    validate_call,
)


def test_search_snippets_matches_titles_and_commands(vault: Vault) -> None:
    api = Api(vault)

    results = api.search_snippets({"query": "nmap"})

    assert results
    assert any("nmap" in item["title"].lower() for item in results)
    # The strongest hit must be an Nmap entry (ranking sanity); fuzzy search
    # may pull in tooling whose *description* mentions Nmap (e.g. RustScan),
    # so an all() assertion would over-constrain the intended behaviour.
    assert "nmap" in results[0]["title"].lower()


def test_search_snippets_ranks_exact_title_hits_first(vault: Vault) -> None:
    api = Api(vault)

    results = api.search_snippets({"query": "nmap full tcp"})

    assert results
    assert "full tcp" in results[0]["title"].lower()


def test_search_snippets_includes_custom_snippets(vault: Vault) -> None:
    vault.create_snippet(
        "My gobustermole",
        "gobuster dir -u {{target}} -w wordlist.txt",
        "custom directory fuzzing",
        "web",
    )
    api = Api(vault)

    results = api.search_snippets({"query": "gobustermole"})

    assert results
    assert results[0]["title"] == "My gobustermole"
    assert results[0]["builtin"] is False


def test_search_snippets_returns_empty_for_misses(vault: Vault) -> None:
    api = Api(vault)

    assert api.search_snippets({"query": "zzzz-no-such-snippet-zzzz"}) == []


def test_search_snippets_respects_the_limit(vault: Vault) -> None:
    api = Api(vault)

    results = api.search_snippets({"query": "nmap", "limit": 1})

    assert len(results) == 1


def test_search_snippets_available_through_the_dispatcher(vault: Vault) -> None:
    api = Api(vault)

    results = api.handle("search_snippets", {"query": "shell"})

    assert results
    assert results[0]["title"]


@pytest.mark.parametrize(
    ("method", "fields"),
    [
        ("search_snippets", ("query", "limit")),
        ("resolve_snippet", ("command", "target")),
        ("create_snippet", ("title", "command", "description", "tags")),
        ("update_snippet", ("id", "title", "command", "description", "tags")),
        ("delete_snippet", ("id",)),
    ],
)
def test_snippet_contracts_expose_expected_fields(method: str, fields: tuple[str, ...]) -> None:
    contract = CONTRACTS[method]
    assert tuple(spec.name for spec in contract.fields) == fields
    assert contract.name == method
    assert describe_api()["methods"][method]["fields"] == [
        spec.as_dict() for spec in contract.fields
    ]


def test_search_snippets_contract_types_and_defaults() -> None:
    specs = {spec.name: spec for spec in CONTRACTS["search_snippets"].fields}
    assert specs["query"].kind is FieldKind.STRING
    assert specs["query"].required is True
    assert specs["limit"].kind is FieldKind.INTEGER
    assert specs["limit"].nullable is True
    assert specs["limit"].required is False
    assert validate_call("search_snippets", {"query": "nmap"}) == {"query": "nmap"}
    assert validate_call("search_snippets", {"query": "nmap", "limit": None}) == {"query": "nmap"}


@pytest.mark.parametrize(
    ("body", "code", "message"),
    [
        ({}, ApiErrorCode.MISSING_FIELD, "Missing 'query'"),
        ({"query": 5}, ApiErrorCode.INVALID_TYPE, "'query' must be a string"),
        (
            {"query": "nmap", "limit": True},
            ApiErrorCode.INVALID_TYPE,
            "'limit' must be an integer",
        ),
        (
            {"query": "nmap", "limit": "5"},
            ApiErrorCode.INVALID_TYPE,
            "'limit' must be an integer",
        ),
    ],
)
def test_search_snippets_contract_failures(
    body: dict[str, Any], code: ApiErrorCode, message: str
) -> None:
    with pytest.raises(ContractError) as error:
        validate_call("search_snippets", body)
    assert error.value.code is code
    assert error.value.message == message


@pytest.mark.parametrize(
    "body",
    [{}, {"query": 5}, {"query": "nmap", "limit": True}],
)
def test_search_snippets_dispatch_errors_match_direct_calls(
    vault: Vault, body: dict[str, Any]
) -> None:
    api = Api(vault)
    with pytest.raises(ApiError) as direct:
        api.search_snippets(body)
    with pytest.raises(ApiError) as dispatched:
        api.handle("search_snippets", body)
    assert direct.value.message == dispatched.value.message
    assert direct.value.status == dispatched.value.status == 400


def test_search_snippets_null_limit_through_the_dispatcher(vault: Vault) -> None:
    api = Api(vault)
    results = api.handle("search_snippets", {"query": "nmap", "limit": None})
    assert results
    assert len(results) <= 12


def test_snippet_creation_contract_limits() -> None:
    specs = {spec.name: spec for spec in CONTRACTS["create_snippet"].fields}
    assert {spec.name: spec.max_length for spec in specs.values()} == {
        "title": MAX_TITLE_LENGTH,
        "command": MAX_SNIPPET_COMMAND_LENGTH,
        "description": MAX_SNIPPET_DESCRIPTION_LENGTH,
        "tags": MAX_TAG_LENGTH,
    }
    with pytest.raises(ContractError) as error:
        validate_call("create_snippet", {"title": "t", "command": "c", "tags": "x" * 501})
    assert error.value.code is ApiErrorCode.FIELD_TOO_LONG
    assert error.value.field == "tags"


def test_snippet_update_contract_requires_all_fields() -> None:
    with pytest.raises(ContractError) as error:
        validate_call("update_snippet", {"id": 1, "title": "t"})
    assert error.value.code is ApiErrorCode.MISSING_FIELD
    assert error.value.field == "command"
    valid = validate_call("update_snippet", {"id": 1, "title": "t", "command": "c"})
    assert valid == {"id": 1, "title": "t", "command": "c", "description": "", "tags": ""}


def test_resolve_snippet_contract_defaults_target() -> None:
    assert validate_call("resolve_snippet", {"command": "whoami"}) == {
        "command": "whoami",
        "target": "",
    }
    with pytest.raises(ContractError) as error:
        validate_call("resolve_snippet", {"target": "host.test"})
    assert error.value.code is ApiErrorCode.MISSING_FIELD
    assert error.value.field == "command"


def test_delete_snippet_contract_requires_an_integer_id() -> None:
    with pytest.raises(ContractError) as error:
        validate_call("delete_snippet", {"id": "1"})
    assert error.value.code is ApiErrorCode.INVALID_TYPE
    assert error.value.message == "'id' must be an integer"
