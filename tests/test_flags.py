from __future__ import annotations

import pytest

from redscribe.domain.flags import (
    FLAG_PREFIXES,
    clean_flag,
    find_flags,
    flag_body,
    flag_fingerprint,
    flag_prefix,
    flags_by_prefix,
    has_flag,
    merge_flags,
    primary_flag,
)


def test_find_flags_extracts_common_formats() -> None:
    text = (
        "user flag: HTB{th1s_is_4_fl4g}\n"
        "root: picoCTF{demo_buffer_overflow}\n"
        "and again HTB{th1s_is_4_fl4g}"
    )
    assert find_flags(text) == [
        "HTB{th1s_is_4_fl4g}",
        "picoCTF{demo_buffer_overflow}",
    ]


def test_find_flags_is_case_insensitive_and_boundary_aware() -> None:
    assert find_flags("FLAG{upper}") == ["FLAG{upper}"]
    assert find_flags("xflag{joined}") == []
    assert find_flags("flag{with space}") == ["flag{with space}"]


def test_find_flags_ignores_empty_and_unterminated_values() -> None:
    assert find_flags("flag{}") == []
    assert find_flags("flag{unterminated") == []
    assert has_flag("flag{}") is False
    assert has_flag("flag{ok}") is True


def test_primary_flag_and_merge_flags() -> None:
    assert primary_flag("nothing here") is None
    assert primary_flag("ctf{one} and flag{two}") == "ctf{one}"
    assert merge_flags("flag{one}", "flag{one} ctf{two}", "") == [
        "flag{one}",
        "ctf{two}",
    ]


def test_supports_at_least_forty_event_prefixes() -> None:
    assert len(FLAG_PREFIXES) >= 40
    assert len(set(FLAG_PREFIXES)) == len(FLAG_PREFIXES)


@pytest.mark.parametrize("prefix", FLAG_PREFIXES)
def test_each_registered_prefix_is_detected(prefix: str) -> None:
    value = f"{prefix}{{sample_value}}"
    assert find_flags(f"prefix: {value}") == [value]


def test_clean_flag_removes_quotes_and_whitespace() -> None:
    assert clean_flag('  "HTB{abc}"  ') == "HTB{abc}"
    assert clean_flag("") == ""


def test_flag_prefix_and_body_handle_balanced_values() -> None:
    assert flag_prefix("HTB{demo_value}") == "HTB"
    assert flag_body("HTB{demo_value}") == "demo_value"
    assert flag_prefix("no-braces") == ""
    assert flag_body("flag{unterminated") == ""
    assert flag_body("flag{a}b}") == ""


def test_flag_fingerprint_normalizes_prefix_but_not_payload() -> None:
    assert flag_fingerprint("HTB{demo}") == flag_fingerprint("htb{demo}")
    assert flag_fingerprint("HTB{demo}") != flag_fingerprint("HTB{DEMO}")
    assert flag_fingerprint("loose text") == "loose text"


def test_flags_by_prefix_groups_in_first_use_order() -> None:
    grouped = flags_by_prefix("HTB{one} flag{two} htb{three} HTB{four}")
    assert list(grouped) == ["htb", "flag"]
    assert grouped["htb"] == ["HTB{one}", "htb{three}", "HTB{four}"]
    assert grouped["flag"] == ["flag{two}"]
