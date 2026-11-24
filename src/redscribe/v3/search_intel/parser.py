"""Recursive-descent parser for query language v2 with stable diagnostics."""

from __future__ import annotations

from dataclasses import replace

from redscribe.v3.search_intel.grammar import (
    field_hint,
    normalize_value,
    validate_field_value,
    validate_link_kind,
)
from redscribe.v3.search_intel.tokenizer import tokenize
from redscribe.v3.search_intel.types import (
    AndGroup,
    ClauseKind,
    FieldName,
    IssueCode,
    ParsedQuery,
    ParseIssue,
    QueryClause,
    Token,
    TokenKind,
    query_fingerprint,
)


class ParseError(ValueError):
    """Raised in strict mode when a query has error-severity issues."""

    def __init__(self, issues: tuple[ParseIssue, ...]) -> None:
        first = issues[0] if issues else None
        message = first.message if first else "Invalid query"
        super().__init__(message)
        self.issues = issues


def _issue(
    code: IssueCode,
    message: str,
    token: Token,
    *,
    field: str = "",
    severity: str = "error",
    hint: str = "",
) -> ParseIssue:
    return ParseIssue(
        code=code,
        message=message,
        start=token.start,
        end=max(token.end, token.start + 1),
        field=field,
        severity=severity,
        hint=hint,
    )


def _conjoin(
    left: tuple[AndGroup, ...],
    right: tuple[AndGroup, ...],
) -> tuple[AndGroup, ...]:
    """Distribute a logical AND across two sets of conjunction groups."""
    if not left:
        return right
    if not right:
        return left
    return tuple(
        AndGroup(tuple(first.clauses) + tuple(second.clauses)) for first in left for second in right
    )


def _negate(groups: tuple[AndGroup, ...]) -> tuple[AndGroup, ...]:
    """Apply a clause-wise negation to every group."""
    return tuple(
        AndGroup(tuple(replace(clause, negated=not clause.negated) for clause in group.clauses))
        for group in groups
    )


class QueryParser:
    """Stateful parser over a token stream."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens, self.issues = tokenize(text)
        self.position = 0

    def current(self) -> Token:
        """Return the token under the cursor."""
        return self.tokens[self.position]

    def _advance(self) -> Token:
        token = self.current()
        if self.position < len(self.tokens) - 1:
            self.position += 1
        return token

    def _at_end(self) -> bool:
        return self.current().kind is TokenKind.EOF

    def _at_or(self) -> bool:
        token = self.current()
        return token.kind is TokenKind.PIPE or (
            token.kind is TokenKind.WORD and token.value.upper() == "OR"
        )

    def _at_not(self) -> bool:
        token = self.current()
        return token.kind is TokenKind.MINUS or (
            token.kind is TokenKind.WORD and token.value.upper() == "NOT"
        )

    def _add(self, issue: ParseIssue) -> None:
        self.issues = (*self.issues, issue)

    def parse(self) -> ParsedQuery:
        """Parse the full query into disjunctive normal form."""
        groups = self._parse_or()
        if not self._at_end():
            token = self._advance()
            self._add(
                _issue(
                    IssueCode.UNEXPECTED_TOKEN,
                    f"Unexpected token '{token.value}'",
                    token,
                )
            )
        if not self.text.strip():
            self._add(
                _issue(
                    IssueCode.EMPTY_QUERY,
                    "Query is empty; add a term or field filter",
                    self.current(),
                    severity="warning",
                    hint="Try 'kind:finding' or a free-text term.",
                )
            )
        return ParsedQuery(
            text=self.text,
            groups=groups,
            tokens=self.tokens,
            issues=tuple(self.issues),
            fingerprint=query_fingerprint(self.text),
        )

    def _parse_or(self) -> tuple[AndGroup, ...]:
        groups = self._parse_and()
        while self._at_or():
            self._advance()
            right = self._parse_and()
            groups = (*groups, *right)
        return groups

    def _parse_and(self) -> tuple[AndGroup, ...]:
        groups: tuple[AndGroup, ...] = (AndGroup(),)
        while (
            not self._at_end() and not self._at_or() and self.current().kind is not TokenKind.RPAREN
        ):
            if self.current().kind is TokenKind.WORD and self.current().value.upper() == "AND":
                self._advance()
                continue
            clause_groups = self._parse_clause()
            groups = _conjoin(groups, clause_groups)
        return groups

    def _parse_clause(self) -> tuple[AndGroup, ...]:
        negated = False
        while self._at_not():
            self._advance()
            negated = not negated
        if self._at_end() or self._at_or() or self.current().kind is TokenKind.RPAREN:
            self._add(
                _issue(
                    IssueCode.DANGLING_NEGATION,
                    "Negation must be followed by a term or field",
                    self.current(),
                )
            )
            return (AndGroup(),)
        groups = self._parse_primary()
        return _negate(groups) if negated else groups

    def _parse_primary(self) -> tuple[AndGroup, ...]:
        token = self.current()
        if token.kind is TokenKind.LPAREN:
            self._advance()
            if self.current().kind is TokenKind.RPAREN:
                empty = self._advance()
                self._add(_issue(IssueCode.EMPTY_GROUP, "Group cannot be empty", empty))
                return (AndGroup(),)
            groups = self._parse_or()
            if self.current().kind is TokenKind.RPAREN:
                self._advance()
            else:
                self._add(
                    _issue(
                        IssueCode.UNCLOSED_GROUP,
                        "Group is missing a closing ')'",
                        self.current(),
                    )
                )
            return groups
        if token.kind is TokenKind.QUOTED:
            self._advance()
            value = normalize_value(token.value)
            if not value:
                return (AndGroup(),)
            clause = QueryClause(
                kind=ClauseKind.TERM,
                value=value,
                raw=f'"{token.value}"',
                phrase=True,
                start=token.start,
                end=token.end,
            )
            return (AndGroup((clause,)),)
        if token.kind is TokenKind.WORD:
            if (
                self.position + 1 < len(self.tokens)
                and self.tokens[self.position + 1].kind is TokenKind.COLON
            ):
                return self._parse_field_clause()
            self._advance()
            value = normalize_value(token.value)
            if not value:
                return (AndGroup(),)
            clause = QueryClause(
                kind=ClauseKind.TERM,
                value=value,
                raw=token.value,
                start=token.start,
                end=token.end,
            )
            return (AndGroup((clause,)),)
        self._advance()
        self._add(
            _issue(
                IssueCode.UNEXPECTED_TOKEN,
                f"Unexpected token '{token.value or token.kind.value}'",
                token,
            )
        )
        return (AndGroup(),)

    def _parse_field_clause(self) -> tuple[AndGroup, ...]:
        field_token = self._advance()
        colon = self._advance()
        field_name = normalize_value(field_token.value)
        field = FieldName.parse(field_name)
        if field is None:
            self._add(
                _issue(
                    IssueCode.UNKNOWN_FIELD,
                    f"Unknown field '{field_name}'",
                    field_token,
                    field=field_name,
                    hint=field_hint(field_name),
                )
            )
        value_token = self.current()
        if value_token.kind not in (TokenKind.WORD, TokenKind.QUOTED):
            self._add(
                _issue(
                    IssueCode.EMPTY_FIELD_VALUE,
                    f"Field '{field_name}' needs a value",
                    colon,
                    field=field_name,
                )
            )
            return (AndGroup(),)
        self._advance()
        raw_value = value_token.value
        normalized, before, _unused_link, error = validate_field_value(field_name, raw_value)
        if error and field is not None:
            self._add(
                _issue(
                    IssueCode(error),
                    f"Invalid value '{raw_value}' for field '{field_name}'",
                    value_token,
                    field=field_name,
                    hint=field_hint(field_name) if error == "unknown_field" else "",
                )
            )
            return (AndGroup(),)
        link_kind = ""
        if field is FieldName.HAS and normalized == "link":
            link_kind = self._parse_link_kind()
        clause = QueryClause(
            kind=(ClauseKind.HAS_LINK if field is FieldName.HAS else ClauseKind.FIELD),
            value=normalized,
            raw=f"{field_name}:{raw_value}",
            field=field_name,
            phrase=value_token.kind is TokenKind.QUOTED,
            start=field_token.start,
            end=value_token.end,
            link_kind=link_kind,
            before=before,
        )
        return (AndGroup((clause,)),)

    def _parse_link_kind(self) -> str:
        if self.current().kind is not TokenKind.LPAREN:
            return ""
        self._advance()
        token = self.current()
        if token.kind is TokenKind.WORD:
            self._advance()
            kind = validate_link_kind(token.value)
            if not kind:
                self._add(
                    _issue(
                        IssueCode.UNKNOWN_LINK_KIND,
                        f"Unknown link kind '{token.value}'",
                        token,
                        field=FieldName.HAS.value,
                    )
                )
        else:
            kind = ""
            self._add(
                _issue(
                    IssueCode.UNKNOWN_LINK_KIND,
                    "has:link expects a link kind in parentheses",
                    token,
                    field=FieldName.HAS.value,
                )
            )
        if self.current().kind is TokenKind.RPAREN:
            self._advance()
        else:
            self._add(
                _issue(
                    IssueCode.UNEXPECTED_TOKEN,
                    "Expected ')' after link kind",
                    self.current(),
                )
            )
        return kind


def parse_query(text: str, *, strict: bool = False) -> ParsedQuery:
    """Parse a query, optionally raising on error-severity diagnostics."""
    parsed = QueryParser(text).parse()
    if strict and not parsed.is_valid:
        errors = tuple(issue for issue in parsed.issues if issue.severity == "error")
        raise ParseError(errors)
    return parsed
