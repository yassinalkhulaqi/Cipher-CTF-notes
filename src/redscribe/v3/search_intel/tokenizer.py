"""Position-aware tokenizer for query language v2."""

from __future__ import annotations

from redscribe.v3.search_intel.types import (
    MAX_QUERY_LENGTH,
    IssueCode,
    ParseIssue,
    Token,
    TokenKind,
)

_SPECIALS: frozenset[str] = frozenset('":()|\n\r\t ')


def _issue(
    code: IssueCode,
    message: str,
    start: int,
    end: int,
    *,
    severity: str = "error",
    hint: str = "",
) -> ParseIssue:
    return ParseIssue(
        code=code,
        message=message,
        start=start,
        end=end,
        severity=severity,
        hint=hint,
    )


def tokenize(text: str) -> tuple[tuple[Token, ...], tuple[ParseIssue, ...]]:
    """Lex a query into tokens and lexical diagnostics.

    The tokenizer never raises on malformed input: it emits a best-effort token
    stream plus stable issues so callers can render inline editor errors while
    the user is still typing.
    """
    tokens: list[Token] = []
    issues: list[ParseIssue] = []
    if len(text) > MAX_QUERY_LENGTH:
        issues.append(
            _issue(
                IssueCode.QUERY_TOO_LONG,
                f"Query exceeds {MAX_QUERY_LENGTH} characters",
                0,
                len(text),
                hint="Shorten the query or split it into a saved search.",
            )
        )
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in " \t\n\r":
            index += 1
            continue
        if char == '"':
            start = index
            index += 1
            pieces: list[str] = []
            closed = False
            while index < length:
                current = text[index]
                if current == "\\" and index + 1 < length:
                    following = text[index + 1]
                    if following in ('"', "\\"):
                        pieces.append(following)
                        index += 2
                        continue
                    pieces.append(current)
                    index += 1
                    continue
                if current == '"':
                    closed = True
                    index += 1
                    break
                pieces.append(current)
                index += 1
            if not closed:
                issues.append(
                    _issue(
                        IssueCode.UNTERMINATED_QUOTE,
                        "Unterminated quoted phrase",
                        start,
                        length,
                        hint="Close the phrase with a trailing quote.",
                    )
                )
            tokens.append(Token(TokenKind.QUOTED, "".join(pieces), start, index))
            continue
        if char == "(":
            tokens.append(Token(TokenKind.LPAREN, char, index, index + 1))
            index += 1
            continue
        if char == ")":
            tokens.append(Token(TokenKind.RPAREN, char, index, index + 1))
            index += 1
            continue
        if char == ":":
            tokens.append(Token(TokenKind.COLON, char, index, index + 1))
            index += 1
            continue
        if char == "|":
            tokens.append(Token(TokenKind.PIPE, char, index, index + 1))
            index += 1
            continue
        if char == "-":
            tokens.append(Token(TokenKind.MINUS, char, index, index + 1))
            index += 1
            continue
        start = index
        while index < length and text[index] not in _SPECIALS:
            index += 1
        tokens.append(Token(TokenKind.WORD, text[start:index], start, index))
    tokens.append(Token(TokenKind.EOF, "", length, length))
    return tuple(tokens), tuple(issues)
