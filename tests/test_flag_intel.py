from __future__ import annotations

from redscribe.domain.flags import FLAG_PREFIXES
from redscribe.services.flag_intel import (
    KNOWN_FLAG_PATTERNS,
    PATTERNS_BY_PREFIX,
    build_flag_insights,
    check_flag,
    flag_insights_payload,
    flag_patterns_payload,
)
from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api


def test_registry_covers_every_detected_prefix() -> None:
    assert {pattern.pattern_key for pattern in KNOWN_FLAG_PATTERNS} == set(FLAG_PREFIXES)


def test_registry_keys_are_unique_and_lowercase() -> None:
    keys = [pattern.pattern_key for pattern in KNOWN_FLAG_PATTERNS]
    assert len(keys) == len(set(keys))
    assert all(key == key.lower() for key in keys)
    assert set(PATTERNS_BY_PREFIX) == set(keys)


def test_curated_platforms_describe_the_well_known_events() -> None:
    assert PATTERNS_BY_PREFIX["htb"].platform == "Hack The Box"
    assert PATTERNS_BY_PREFIX["thm"].platform == "TryHackMe"
    assert PATTERNS_BY_PREFIX["picoctf"].platform == "picoCTF"


def test_check_flag_accepts_a_known_format() -> None:
    check = check_flag("HTB{demo_value}")
    assert check.ok is True
    assert check.known_prefix is True
    assert check.platform == "Hack The Box"
    assert check.value_length == len("demo_value")


def test_check_flag_accepts_an_unknown_but_wellformed_prefix() -> None:
    check = check_flag("unknownctf{demo_value}")
    assert check.ok is True
    assert check.known_prefix is False
    assert "not a known event prefix" in check.hint


def test_check_flag_rejects_empty_and_unbalanced_values() -> None:
    assert check_flag("").ok is False
    assert check_flag("flag{}").ok is False
    assert check_flag("flag{unterminated").ok is False
    assert check_flag("flag{a}b}").ok is False


def test_check_flag_trims_surrounding_quotes_and_whitespace() -> None:
    check = check_flag('  "HTB{abc}"  ')
    assert check.ok is True
    assert check.known_prefix is True


def _seed(vault: Vault) -> None:
    htb = vault.create_node(
        "HTB — Corporate",
        content="loot:\nHTB{one}\n",
        flag="HTB{one}",
        status="done",
    )
    vault.create_node("Same flag elsewhere", content=htb.flag, status="todo")
    vault.create_node(
        "Done without flag",
        content="## progress\n\nnothing captured yet",
        status="done",
    )
    vault.create_node("Open and flagless", content="## idea", status="todo")


def test_build_flag_insights_counts_manual_detected_and_duplicates(vault: Vault) -> None:
    _seed(vault)

    insights = build_flag_insights(vault)

    assert insights.unique_flags == 1
    assert insights.manual_flags == 1
    assert insights.detected_flags == 0
    assert [(item.prefix, item.platform, item.count) for item in insights.by_source] == [
        ("htb", "Hack The Box", 1)
    ]
    assert len(insights.duplicates) == 1
    assert insights.duplicates[0].flag == "HTB{one}"
    assert insights.duplicates[0].note_count == 2
    assert insights.missing_flag_notes == 1


def test_build_flag_insights_empty_vault(vault: Vault) -> None:
    insights = build_flag_insights(vault)

    assert insights.unique_flags == 0
    assert insights.by_source == ()
    assert insights.duplicates == ()
    assert insights.missing_flag_notes == 0


def test_flag_patterns_payload_shapes_registry() -> None:
    payload = flag_patterns_payload()

    assert payload
    first = payload[0]
    assert set(first) == {"prefix", "pattern_key", "platform", "example", "hint", "category"}
    assert first["example"] == f"{first['prefix']}{{...}}"


def test_flag_insights_payload_serializes(vault: Vault) -> None:
    _seed(vault)

    payload = flag_insights_payload(build_flag_insights(vault))

    assert set(payload) == {
        "unique_flags",
        "manual_flags",
        "detected_flags",
        "by_source",
        "duplicates",
        "missing_flag_notes",
    }
    assert payload["unique_flags"] == 1


def test_api_flag_endpoints(vault: Vault) -> None:
    api = Api(vault)

    patterns = api.flag_patterns({})
    assert patterns
    assert patterns[0]["example"].endswith("{...}")

    insights = api.flag_insights({})
    assert set(insights) == {
        "unique_flags",
        "manual_flags",
        "detected_flags",
        "by_source",
        "duplicates",
        "missing_flag_notes",
    }
