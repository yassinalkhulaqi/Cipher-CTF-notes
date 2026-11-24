"""Parser semantics, stable errors, and grammar fuzzing."""

from __future__ import annotations

import random

import pytest

from redscribe.v3.search_intel.parser import ParseError, QueryParser, parse_query
from redscribe.v3.search_intel.types import ClauseKind, IssueCode


def test_parse_free_text_terms() -> None:
    parsed = parse_query("web finding")
    assert parsed.is_valid
    assert parsed.terms == ("web", "finding")
    assert len(parsed.groups) == 1
    assert len(parsed.groups[0].clauses) == 2


def test_parse_field_clauses() -> None:
    parsed = parse_query("kind:finding tag:web status:active severity:critical")
    assert parsed.is_valid
    assert parsed.fields == ("kind", "severity", "status", "tag")
    assert {clause.value for clause in parsed.clauses} == {
        "finding",
        "web",
        "active",
        "critical",
    }


def test_parse_negation() -> None:
    parsed = parse_query("-kind:note NOT tag:draft")
    assert parsed.is_valid
    assert all(clause.negated for clause in parsed.clauses)


def test_parse_or_creates_multiple_groups() -> None:
    parsed = parse_query("kind:finding OR kind:evidence")
    assert parsed.is_valid
    assert len(parsed.groups) == 2
    assert parsed.groups[0].clauses[0].value == "finding"
    assert parsed.groups[1].clauses[0].value == "evidence"


def test_parse_pipe_is_or_alias() -> None:
    assert len(parse_query("kind:finding|kind:note").groups) == 2


def test_parse_implicit_and_binds_tighter_than_or() -> None:
    parsed = parse_query("kind:finding OR tag:web status:active")
    assert len(parsed.groups) == 2
    assert len(parsed.groups[1].clauses) == 2


def test_parse_explicit_and_is_noop() -> None:
    parsed = parse_query("kind:finding AND tag:web")
    assert len(parsed.groups[0].clauses) == 2


def test_parse_groups() -> None:
    parsed = parse_query("(kind:finding OR kind:evidence) tag:web")
    assert parsed.is_valid
    assert len(parsed.groups) == 2
    assert all(len(group.clauses) == 2 for group in parsed.groups)


def test_parse_has_link_clause() -> None:
    parsed = parse_query("has:link")
    clause = parsed.clauses[0]
    assert clause.kind is ClauseKind.HAS_LINK
    assert clause.link_kind == ""


def test_parse_has_link_with_kind() -> None:
    parsed = parse_query("has:link(evidences)")
    assert parsed.is_valid
    assert parsed.clauses[0].link_kind == "evidences"


def test_parse_quoted_phrase() -> None:
    parsed = parse_query('"weak cipher suites"')
    assert parsed.clauses[0].phrase
    assert parsed.clauses[0].value == "weak cipher suites"


def test_parse_before_sets_timestamp() -> None:
    parsed = parse_query("before:2024-01-01")
    assert parsed.clauses[0].before > 0


def test_unknown_field_has_stable_error() -> None:
    parsed = parse_query("foobar:web")
    assert not parsed.is_valid
    issue = parsed.issues[0]
    assert issue.code is IssueCode.UNKNOWN_FIELD
    assert issue.field == "foobar"
    assert "kind" in issue.hint


def test_missing_field_value_has_stable_error() -> None:
    parsed = parse_query("kind:")
    codes = parsed.error_codes
    assert IssueCode.EMPTY_FIELD_VALUE.value in codes
    assert parsed.issues[0].field == "kind"


def test_invalid_field_value_has_stable_error() -> None:
    parsed = parse_query("severity:ultra")
    assert parsed.error_codes == (IssueCode.INVALID_FIELD_VALUE.value,)


def test_unknown_link_kind_has_stable_error() -> None:
    parsed = parse_query("has:link(bogus)")
    assert IssueCode.UNKNOWN_LINK_KIND.value in parsed.error_codes


def test_unclosed_group_has_stable_error() -> None:
    parsed = parse_query("(kind:finding")
    assert IssueCode.UNCLOSED_GROUP.value in parsed.error_codes


def test_empty_group_has_stable_error() -> None:
    parsed = parse_query("()")
    assert IssueCode.EMPTY_GROUP.value in parsed.error_codes


def test_dangling_negation_has_stable_error() -> None:
    parsed = parse_query("kind:finding AND -")
    assert IssueCode.DANGLING_NEGATION.value in parsed.error_codes


def test_empty_query_is_warning_not_error() -> None:
    parsed = parse_query("   ")
    assert parsed.is_valid
    assert parsed.issues[0].code is IssueCode.EMPTY_QUERY
    assert parsed.issues[0].severity == "warning"


def test_fingerprint_is_stable_under_whitespace() -> None:
    assert (
        parse_query("kind:finding tag:web").fingerprint
        == parse_query("  kind:finding   tag:web  ").fingerprint
    )


def test_strict_mode_raises_parse_error() -> None:
    with pytest.raises(ParseError) as exc:
        parse_query("severity:bogus", strict=True)
    assert exc.value.issues[0].code is IssueCode.INVALID_FIELD_VALUE


def test_parser_class_matches_convenience() -> None:
    assert QueryParser("kind:note").parse().as_dict() == parse_query("kind:note").as_dict()


def test_as_dict_contains_all_sections() -> None:
    payload = parse_query("kind:finding").as_dict()
    assert set(payload) == {"text", "valid", "fingerprint", "groups", "tokens", "issues"}


def test_grammar_fuzzing_never_raises() -> None:
    rng = random.Random(20240517)
    alphabet = ["kind", "tag", ":", '"', "(", ")", "-", "OR", "NOT", "web", " ", "|", "has", "link"]
    for _ in range(400):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
        parsed = parse_query(text)
        assert isinstance(parsed.is_valid, bool)
        assert isinstance(parsed.groups, tuple)
        assert all(isinstance(clause.start, int) for clause in parsed.clauses)
        assert all(issue.start >= 0 and issue.end >= issue.start for issue in parsed.issues)


def test_repeated_parse_is_deterministic() -> None:
    text = "-kind:finding OR (tag:web has:link(evidences))"
    first = parse_query(text)
    second = parse_query(text)
    assert first.as_dict() == second.as_dict()
