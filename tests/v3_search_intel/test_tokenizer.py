"""Tokenizer behavior and lexical diagnostics."""

from __future__ import annotations

from redscribe.v3.search_intel.tokenizer import tokenize
from redscribe.v3.search_intel.types import IssueCode, TokenKind


def test_tokenize_simple_words() -> None:
    tokens, issues = tokenize("web finding")
    assert issues == ()
    assert [(token.kind, token.value) for token in tokens[:-1]] == [
        (TokenKind.WORD, "web"),
        (TokenKind.WORD, "finding"),
    ]
    assert tokens[-1].kind is TokenKind.EOF
    assert tokens[-1].start == len("web finding")


def test_tokenize_field_expression_has_offsets() -> None:
    text = '-kind:finding "weak cipher"'
    tokens, issues = tokenize(text)
    assert issues == ()
    kinds = [token.kind for token in tokens[:-1]]
    assert kinds == [
        TokenKind.MINUS,
        TokenKind.WORD,
        TokenKind.COLON,
        TokenKind.WORD,
        TokenKind.QUOTED,
    ]
    assert tokens[1].value == "kind"
    assert tokens[3].value == "finding"
    assert tokens[4].value == "weak cipher"
    assert text[tokens[4].start : tokens[4].end] == '"weak cipher"'


def test_tokenize_escaped_quote() -> None:
    tokens, issues = tokenize('"say \\"hello\\""')
    assert issues == ()
    assert tokens[0].kind is TokenKind.QUOTED
    assert tokens[0].value == 'say "hello"'


def test_tokenize_unterminated_quote_is_stable() -> None:
    tokens, issues = tokenize('kind:finding "unfinished')
    assert tokens[0].kind is TokenKind.WORD
    assert tokens[-2].kind is TokenKind.QUOTED
    assert len(issues) == 1
    assert issues[0].code is IssueCode.UNTERMINATED_QUOTE
    assert issues[0].start == len("kind:finding ")
    assert issues[0].end == len('kind:finding "unfinished')


def test_tokenize_special_characters() -> None:
    tokens, issues = tokenize("(a|b) -c")
    assert issues == ()
    assert [token.kind for token in tokens[:-1]] == [
        TokenKind.LPAREN,
        TokenKind.WORD,
        TokenKind.PIPE,
        TokenKind.WORD,
        TokenKind.RPAREN,
        TokenKind.MINUS,
        TokenKind.WORD,
    ]


def test_tokenize_hyphen_within_word() -> None:
    tokens, _issues = tokenize("high-priority")
    assert len(tokens) == 2
    assert tokens[0].kind is TokenKind.WORD
    assert tokens[0].value == "high-priority"


def test_tokenize_long_query_reports_issue() -> None:
    tokens, issues = tokenize("a" * 501)
    assert any(issue.code is IssueCode.QUERY_TOO_LONG for issue in issues)
    assert len(tokens) == 2


def test_tokenize_empty_query() -> None:
    tokens, issues = tokenize("")
    assert issues == ()
    assert len(tokens) == 1
    assert tokens[0].kind is TokenKind.EOF
