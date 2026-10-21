from __future__ import annotations

from redscribe.flags import find_flags, has_flag, merge_flags, primary_flag


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
