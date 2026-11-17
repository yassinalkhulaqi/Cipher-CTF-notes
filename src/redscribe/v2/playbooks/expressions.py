"""A small, side-effect-free parser for playbook conditions.

Conditions can be supplied either as structured :class:`Condition` objects or
as short text expressions such as ``exists(target) and port >= 1024``. The
grammar is intentionally limited to local value comparisons; it never calls
Python builtins, imports modules, or executes commands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from redscribe.v2.playbooks.errors import ExpressionError
from redscribe.v2.playbooks.types import (
    Condition,
    ConditionOperator,
    Issue,
    Value,
    Values,
)

_KEYWORDS = frozenset({"and", "or", "not", "in", "is", "true", "false", "null"})
_OPERATORS = frozenset({"==", "!=", ">=", "<=", "<", ">", "&&", "||", "!", "~", "-"})
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_FUNCTIONS = frozenset(
    {
        "exists",
        "empty",
        "len",
        "lower",
        "upper",
        "contains",
        "startswith",
        "endswith",
        "matches",
        "default",
        "has_any",
    }
)


@dataclass(frozen=True, slots=True)
class Token:
    """One lexical token with its source position."""

    kind: str
    value: str
    position: int


@dataclass(frozen=True, slots=True)
class Literal:
    """A constant scalar or list literal."""

    value: Value

    def evaluate(self, values: Values) -> Value:
        del values
        return self.value

    def references(self) -> tuple[str, ...]:
        return ()

    def describe(self) -> str:
        return _display(self.value)


@dataclass(frozen=True, slots=True)
class Reference:
    """A named lookup in the active variable context."""

    name: str

    def evaluate(self, values: Values) -> Value:
        return lookup_path(values, self.name)

    def references(self) -> tuple[str, ...]:
        return (self.name,)

    def describe(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class Unary:
    """A unary boolean or numeric operation."""

    operator: str
    operand: Expression

    def evaluate(self, values: Values) -> Value:
        value = self.operand.evaluate(values)
        if self.operator in ("not", "!"):
            return not is_truthy(value)
        if self.operator == "-":
            return -_as_number(value)
        raise ExpressionError(f"Unknown unary operator: {self.operator}")

    def references(self) -> tuple[str, ...]:
        return self.operand.references()

    def describe(self) -> str:
        return f"not {self.operand.describe()}"


@dataclass(frozen=True, slots=True)
class Binary:
    """A comparison or boolean combination of two expressions."""

    operator: str
    left: Expression
    right: Expression

    def evaluate(self, values: Values) -> Value:
        left = self.left.evaluate(values)
        if self.operator in ("and", "&&"):
            return is_truthy(left) and is_truthy(self.right.evaluate(values))
        if self.operator in ("or", "||"):
            return is_truthy(left) or is_truthy(self.right.evaluate(values))
        right = self.right.evaluate(values)
        return compare(left, self.operator, right)

    def references(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.left.references(), *self.right.references())))

    def describe(self) -> str:
        symbol = {"and": "and", "or": "or", "==": "=", "!=": "!="}.get(self.operator, self.operator)
        return f"{self.left.describe()} {symbol} {self.right.describe()}"


@dataclass(frozen=True, slots=True)
class ListExpression:
    """A bracketed list of literal or computed values."""

    items: tuple[Expression, ...] = ()

    def evaluate(self, values: Values) -> Value:
        return tuple(item.evaluate(values) for item in self.items)

    def references(self) -> tuple[str, ...]:
        names: list[str] = []
        for item in self.items:
            names.extend(item.references())
        return tuple(dict.fromkeys(names))

    def describe(self) -> str:
        return "[" + ", ".join(item.describe() for item in self.items) + "]"


@dataclass(frozen=True, slots=True)
class Call:
    """A whitelisted helper function call."""

    name: str
    arguments: tuple[Expression, ...] = ()

    def evaluate(self, values: Values) -> Value:
        args = [argument.evaluate(values) for argument in self.arguments]
        if self.name in ("exists", "empty"):
            if not args:
                raise ExpressionError(f"{self.name}() needs one argument")
            references = self.arguments[0].references()
            present = is_truthy(args[0])
            if references:
                present = references[0] in values and present
            return not present if self.name == "empty" else present
        if self.name == "len":
            if not args:
                raise ExpressionError("len() needs one argument")
            return len(_as_text(args[0]))
        if self.name in ("lower", "upper"):
            if not args:
                raise ExpressionError(f"{self.name}() needs one argument")
            text = _as_text(args[0])
            return text.lower() if self.name == "lower" else text.upper()
        if self.name in ("contains", "startswith", "endswith", "matches"):
            if len(args) < 2:
                raise ExpressionError(f"{self.name}() needs two arguments")
            text, needle = _as_text(args[0]), _as_text(args[1])
            if self.name == "contains":
                return needle.casefold() in text.casefold()
            if self.name == "startswith":
                return text.casefold().startswith(needle.casefold())
            if self.name == "endswith":
                return text.casefold().endswith(needle.casefold())
            return regex_matches(text, needle)
        if self.name in ("default", "has_any"):
            if not args:
                raise ExpressionError(f"{self.name}() needs at least one argument")
            if self.name == "default":
                for arg in args:
                    if is_truthy(arg):
                        return arg
                return ""
            return any(is_truthy(arg) for arg in args)
        raise ExpressionError(f"Unknown expression function: {self.name}")

    def references(self) -> tuple[str, ...]:
        names: list[str] = []
        for argument in self.arguments:
            names.extend(argument.references())
        return tuple(dict.fromkeys(names))

    def describe(self) -> str:
        args = ", ".join(argument.describe() for argument in self.arguments)
        return f"{self.name}({args})"


Expression = Literal | Reference | Unary | Binary | ListExpression | Call


class _Parser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = tokenize(source)
        self.position = 0

    def peek(self) -> Token:
        return self.tokens[min(self.position, len(self.tokens) - 1)]

    def take(self) -> Token:
        token = self.peek()
        self.position += 1
        return token

    def accept(self, value: str) -> bool:
        if self.peek().value == value:
            self.take()
            return True
        return False

    def expect(self, value: str) -> Token:
        token = self.peek()
        if token.value != value:
            raise ExpressionError(
                f"Expected '{value}' at position {token.position}, got '{token.value}'"
            )
        return self.take()

    def parse(self) -> Expression:
        if self.peek().kind == "eof":
            raise ExpressionError("Condition expression is empty")
        expression = self.parse_or()
        remaining = self.peek()
        if remaining.kind != "eof":
            raise ExpressionError(f"Unexpected token '{remaining.value}' at {remaining.position}")
        return expression

    def parse_or(self) -> Expression:
        expression = self.parse_and()
        while self.peek().value in ("or", "||"):
            self.take()
            expression = Binary("or", expression, self.parse_and())
        return expression

    def parse_and(self) -> Expression:
        expression = self.parse_not()
        while self.peek().value in ("and", "&&"):
            self.take()
            expression = Binary("and", expression, self.parse_not())
        return expression

    def parse_not(self) -> Expression:
        if self.peek().value in ("not", "!"):
            self.take()
            return Unary("not", self.parse_not())
        if self.peek().value == "-":
            self.take()
            return self.parse_comparison_tail(Unary("-", self.parse_primary()))
        return self.parse_comparison()

    def parse_comparison(self) -> Expression:
        return self.parse_comparison_tail(self.parse_primary())

    def parse_comparison_tail(self, left: Expression) -> Expression:
        token = self.peek()
        operator = _canonical_operator(token)
        if operator is None:
            return left
        self.take()
        if operator == "is":
            operator = "!=" if self.accept("not") else "=="
        if operator == "not" and self.peek().value == "in":
            self.take()
            operator = "not in"
        return Binary(operator, left, self.parse_primary())

    def parse_primary(self) -> Expression:
        token = self.take()
        if token.value == "(":
            expression = self.parse_or()
            self.expect(")")
            return expression
        if token.value == "[":
            items: list[Expression] = []
            if self.peek().value != "]":
                items.append(self.parse_or())
                while self.accept(","):
                    if self.peek().value == "]":
                        break
                    items.append(self.parse_or())
            self.expect("]")
            return ListExpression(tuple(items))
        if token.kind == "number":
            return Literal(_parse_number(token.value))
        if token.kind == "string":
            return Literal(token.value)
        if token.kind == "name":
            if token.value == "true":
                return Literal(True)
            if token.value == "false":
                return Literal(False)
            if token.value == "null":
                return Literal("")
            if self.peek().value == "(":
                self.take()
                arguments: list[Expression] = []
                if self.peek().value != ")":
                    arguments.append(self.parse_or())
                    while self.accept(","):
                        arguments.append(self.parse_or())
                self.expect(")")
                if token.value not in _FUNCTIONS:
                    raise ExpressionError(f"Unknown expression function: {token.value}")
                return Call(token.value, tuple(arguments))
            return Reference(token.value)
        raise ExpressionError(f"Unexpected token '{token.value}' at position {token.position}")


def tokenize(source: str) -> list[Token]:
    """Split a condition expression into typed tokens."""
    tokens: list[Token] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if char in "()[],":
            kinds = {"(": "lparen", ")": "rparen", "[": "lbracket", "]": "rbracket", ",": "comma"}
            tokens.append(Token(kinds[char], char, index))
            index += 1
            continue
        if char in "\"'":
            quote = char
            index += 1
            buffer: list[str] = []
            while index < len(source) and source[index] != quote:
                if source[index] == "\\" and index + 1 < len(source):
                    index += 1
                    buffer.append(source[index])
                else:
                    buffer.append(source[index])
                index += 1
            if index >= len(source):
                raise ExpressionError("Unterminated string in condition")
            index += 1
            tokens.append(Token("string", "".join(buffer), index))
            continue
        number = _NUMBER_RE.match(source, index)
        if number is not None:
            tokens.append(Token("number", number.group(0), index))
            index = number.end()
            continue
        identifier = _IDENTIFIER_RE.match(source, index)
        if identifier is not None:
            value = identifier.group(0)
            kind = "operator" if value in _KEYWORDS else "name"
            tokens.append(Token(kind, value, index))
            index = identifier.end()
            continue
        pair = source[index : index + 2]
        if pair in ("==", "!=", ">=", "<=", "&&", "||"):
            tokens.append(Token("operator", pair, index))
            index += 2
            continue
        if char in _OPERATORS:
            tokens.append(Token("operator", char, index))
            index += 1
            continue
        raise ExpressionError(f"Unexpected character '{char}' at position {index}")
    tokens.append(Token("eof", "", len(source)))
    return tokens


def parse_expression(source: str) -> Expression:
    """Parse an expression, raising :class:`ExpressionError` when invalid."""
    return _Parser(source).parse()


def evaluate_expression(source: str, values: Values | None = None) -> bool:
    """Evaluate an expression to a boolean in the supplied context."""
    expression = parse_expression(source)
    return is_truthy(expression.evaluate(values or {}))


def expression_references(source: str) -> tuple[str, ...]:
    """Return variable references used by an expression."""
    return parse_expression(source).references()


def describe_expression(source: str) -> str:
    """Return a normalized human-readable form of an expression."""
    return parse_expression(source).describe()


def validate_expression(source: str) -> tuple[Issue, ...]:
    """Validate an expression without evaluating it."""
    try:
        expression = parse_expression(source)
    except ExpressionError as exc:
        return (Issue(code="invalid-expression", message=str(exc)),)
    issues: list[Issue] = []
    for name in expression.references():
        if "." in name and not name.split(".", 1)[1]:
            issues.append(Issue("invalid-reference", f"Reference has an empty path: {name}"))
    return tuple(issues)


def evaluate_condition(condition: Condition, values: Values) -> bool:
    """Evaluate one structured condition against resolved values."""
    field_name = condition.field.strip()
    if not field_name:
        raise ExpressionError("Condition has no field")
    present = field_name in values
    value = lookup_path(values, field_name)
    operator = condition.operator
    if isinstance(operator, str):
        operator = ConditionOperator(operator)
    if operator == ConditionOperator.EXISTS:
        return present and is_truthy(value)
    if operator == ConditionOperator.NOT_EXISTS:
        return not present or not is_truthy(value)
    if operator == ConditionOperator.MATCHES:
        return regex_matches(_as_text(value), _as_text(condition.value))
    comparison = {
        ConditionOperator.EQ: "==",
        ConditionOperator.NE: "!=",
        ConditionOperator.GT: ">",
        ConditionOperator.GTE: ">=",
        ConditionOperator.LT: "<",
        ConditionOperator.LTE: "<=",
        ConditionOperator.CONTAINS: "contains",
        ConditionOperator.NOT_CONTAINS: "not contains",
        ConditionOperator.IN: "in",
        ConditionOperator.NOT_IN: "not in",
    }[operator]
    return bool(compare(value, comparison, condition.value))


def lookup_path(values: Values, path: str) -> Value:
    """Resolve a dotted lookup path over the flat variable context."""
    if path in values:
        return values[path]
    head, _, tail = path.partition(".")
    if not tail:
        return ""
    value = values.get(head)
    if isinstance(value, tuple):
        index = _as_number(tail)
        if 0 <= index < len(value):
            item = value[int(index)]
            if isinstance(item, (str, int, float, bool, tuple)):
                return item
    return ""


def compare(left: Value, operator: str, right: Value) -> bool:
    """Compare two resolved values using a whitelisted operator."""
    if operator in ("==", "!="):
        equal = _equal(left, right)
        return equal if operator == "==" else not equal
    if operator in ("contains", "not contains"):
        contained = _contains(left, right)
        return contained if operator == "contains" else not contained
    if operator in ("in", "not in"):
        contained = _contains(right, left)
        return contained if operator == "in" else not contained
    if operator == "~":
        return regex_matches(_as_text(left), _as_text(right))
    left_numeric = _is_numeric(left)
    right_numeric = _is_numeric(right)
    if left_numeric != right_numeric:
        return False
    try:
        if left_numeric:
            return _ordered(_as_number(left), operator, _as_number(right))
        return _ordered_text(_as_text(left), operator, _as_text(right))
    except (TypeError, ValueError):
        return False


def is_truthy(value: object) -> bool:
    """Return the boolean interpretation used by conditions."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, tuple):
        return bool(value)
    if isinstance(value, str):
        return value.strip().casefold() not in ("", "false", "0", "no", "none", "null")
    return bool(value)


def regex_matches(text: str, pattern: str) -> bool:
    """Run a bounded regular-expression match."""
    if not pattern:
        return False
    try:
        return re.search(pattern, text) is not None
    except re.error as exc:
        raise ExpressionError(f"Invalid regular expression: {exc}") from exc


def _ordered(left: float, operator: str, right: float) -> bool:
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    raise ExpressionError(f"Unknown comparison operator: {operator}")


def _ordered_text(left: str, operator: str, right: str) -> bool:
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    raise ExpressionError(f"Unknown comparison operator: {operator}")


def _canonical_operator(token: Token) -> str | None:
    if token.kind != "operator":
        return None
    if token.value not in ("==", "!=", ">", ">=", "<", "<=", "is", "not", "in", "~"):
        return None
    return token.value


def _parse_number(value: str) -> float | int:
    return float(value) if "." in value else int(value)


def _as_text(value: object) -> str:
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None or isinstance(value, dict):
        return ""
    return str(value)


def _as_number(value: object) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(_as_text(value))
    except ValueError as exc:
        raise ExpressionError(f"Value is not numeric: {_as_text(value)}") from exc


def _is_numeric(value: object) -> bool:
    if isinstance(value, (bool, list, tuple, dict)):
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(_as_text(value))
    except ValueError:
        return False
    return True


def _both_numeric(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return False
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return True
    try:
        float(_as_text(left))
        float(_as_text(right))
    except ValueError:
        return False
    return True


def _equal(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return is_truthy(left) is is_truthy(right)
    if _both_numeric(left, right) and not isinstance(left, tuple) and not isinstance(right, tuple):
        return _as_number(left) == _as_number(right)
    if isinstance(left, tuple) or isinstance(right, tuple):
        return left == right
    return _as_text(left).casefold() == _as_text(right).casefold()


def _contains(container: object, needle: object) -> bool:
    if isinstance(container, (tuple, list)):
        return any(_equal(item, needle) for item in container)
    if isinstance(container, str):
        return _as_text(needle).casefold() in container.casefold()
    return False


def _display(value: Value) -> str:
    if isinstance(value, tuple):
        return "[" + ", ".join(_as_text(item) for item in value) + "]"
    return _as_text(value)


__all__ = [
    "Expression",
    "ExpressionError",
    "build_condition_from_text",
    "compare",
    "describe_expression",
    "evaluate_condition",
    "evaluate_expression",
    "expression_references",
    "is_truthy",
    "lookup_path",
    "parse_expression",
    "tokenize",
    "validate_expression",
]


def build_condition_from_text(field_name: str, source: str, *, negate: bool = False) -> Condition:
    """Wrap a text expression in a structured condition for the given field."""
    issues = validate_expression(source)
    if issues:
        raise ExpressionError(issues[0].message)
    if negate:
        source = f"not ({source})"
    return Condition(field=field_name, operator=ConditionOperator.EQ, value=source)
