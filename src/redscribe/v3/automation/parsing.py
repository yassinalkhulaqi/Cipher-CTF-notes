"""Parse untrusted JSON payloads into strict automation domain objects.

Parsing is deliberately conservative: unknown fields are ignored, required
fields are reported as diagnostics, and any input key that could be mistaken
for a command, process, file path or network target is rejected outright.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from redscribe.v3.automation.errors import PlaybookValidationError
from redscribe.v3.automation.types import (
    ConditionOperator,
    Frequency,
    PlaybookDefinition,
    RecurrenceRule,
    StepCondition,
    StepDefinition,
    StepKind,
    ValidationIssue,
    Value,
    VariableDefinition,
    VariableKind,
)

FORBIDDEN_INPUT_KEYS: frozenset[str] = frozenset(
    {
        "command",
        "cmd",
        "shell",
        "exec",
        "execute",
        "script",
        "subprocess",
        "program",
        "binary",
        "path",
        "file_path",
        "filepath",
        "url",
        "uri",
        "endpoint",
        "host",
        "port",
        "socket",
        "network",
    }
)


def _mapping(value: Any, *, path: str) -> dict[str, Any]:
    """Return a mapping payload or raise a validation error."""
    if not isinstance(value, Mapping):
        raise PlaybookValidationError(f"Expected an object at {path}", path=path)
    return dict(value)


def _string(payload: dict[str, Any], key: str, *, path: str, required: bool = False) -> str:
    """Read a string field."""
    if key not in payload:
        if required:
            raise PlaybookValidationError(f"Missing required field '{key}' at {path}", path=path)
        return ""
    value = payload[key]
    if not isinstance(value, str):
        raise PlaybookValidationError(f"Field '{key}' at {path} must be a string", path=path)
    return value.strip()


def _string_tuple(payload: dict[str, Any], key: str, *, path: str) -> tuple[str, ...]:
    """Read a list of strings."""
    value = payload.get(key, ())
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        raise PlaybookValidationError(f"Field '{key}' at {path} must be a list", path=path)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise PlaybookValidationError(
                f"Field '{key}' at {path} must contain strings", path=path
            )
        if item and item not in result:
            result.append(item.strip())
    return tuple(result)


def _value(payload: dict[str, Any], key: str, *, path: str) -> Value:
    """Read a JSON scalar, list or mapping."""
    value = payload.get(key)
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    raise PlaybookValidationError(f"Field '{key}' at {path} is not JSON data", path=path)


def _number(payload: dict[str, Any], key: str, *, path: str) -> float | None:
    """Read an optional number."""
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlaybookValidationError(f"Field '{key}' at {path} must be a number", path=path)
    return float(value)


def parse_variable(payload: Any, *, path: str = "variables") -> VariableDefinition:
    """Parse one variable definition."""
    data = _mapping(payload, path=path)
    key = _string(data, "key", path=path, required=True)
    kind_raw = _string(data, "kind", path=path) or VariableKind.TEXT.value
    try:
        kind = VariableKind.parse(kind_raw)
    except ValueError as error:
        raise PlaybookValidationError(str(error), path=f"{path}.kind") from error
    return VariableDefinition(
        key=key,
        kind=kind,
        label=_string(data, "label", path=path),
        required=bool(data.get("required", False)),
        default=_value(data, "default", path=path) if "default" in data else "",
        choices=_string_tuple(data, "choices", path=path),
        description=_string(data, "description", path=path),
        secret=bool(data.get("secret", False)),
        pattern=_string(data, "pattern", path=path),
        minimum=_number(data, "minimum", path=path),
        maximum=_number(data, "maximum", path=path),
    )


def parse_condition(payload: Any, *, path: str = "condition") -> StepCondition:
    """Parse one step guard."""
    data = _mapping(payload, path=path)
    operator_raw = _string(data, "operator", path=path) or ConditionOperator.EXISTS.value
    try:
        operator = ConditionOperator(operator_raw)
    except ValueError as error:
        raise PlaybookValidationError(
            f"Unknown condition operator: {operator_raw}", path=path
        ) from error
    return StepCondition(
        field=_string(data, "field", path=path, required=True),
        operator=operator,
        value=_value(data, "value", path=path),
    )


def parse_step(payload: Any, *, path: str = "steps") -> StepDefinition:
    """Parse one step definition, rejecting non-data input keys."""
    data = _mapping(payload, path=path)
    step_id = _string(data, "id", path=path, required=True)
    kind_raw = _string(data, "kind", path=path) or StepKind.CREATE_NOTE.value
    try:
        kind = StepKind.parse(kind_raw)
    except ValueError as error:
        raise PlaybookValidationError(str(error), path=f"{path}.kind") from error
    raw_inputs = _mapping(data.get("inputs", {}), path=f"{path}.inputs")
    blocked = sorted(key for key in raw_inputs if key.casefold() in FORBIDDEN_INPUT_KEYS)
    if blocked:
        raise PlaybookValidationError(
            f"Automation inputs cannot contain command-like keys: {', '.join(blocked)}",
            path=f"{path}.inputs",
        )
    condition_payload = data.get("condition")
    condition = (
        parse_condition(condition_payload, path=f"{path}.condition")
        if condition_payload is not None
        else None
    )
    return StepDefinition(
        id=step_id,
        title=_string(data, "title", path=path, required=True) or step_id,
        kind=kind,
        depends_on=_string_tuple(data, "depends_on", path=path),
        inputs=raw_inputs,
        condition=condition,
        output=_string(data, "output", path=path),
        optional=bool(data.get("optional", False)),
        tags=_string_tuple(data, "tags", path=path),
    )


def parse_recurrence(payload: Any, *, path: str = "recurrence") -> RecurrenceRule:
    """Parse a recurrence rule."""
    data = _mapping(payload, path=path)
    frequency_raw = _string(data, "frequency", path=path) or Frequency.DAILY.value
    try:
        frequency = Frequency.parse(frequency_raw)
    except ValueError as error:
        raise PlaybookValidationError(str(error), path=f"{path}.frequency") from error
    weekdays = data.get("by_weekday", ())
    if not isinstance(weekdays, Sequence) or isinstance(weekdays, str):
        raise PlaybookValidationError(f"Field 'by_weekday' at {path} must be a list", path=path)
    parsed_days: list[int] = []
    for day in weekdays:
        if isinstance(day, bool) or not isinstance(day, int):
            raise PlaybookValidationError(f"Weekdays must be integers at {path}", path=path)
        parsed_days.append(day)
    month_day = data.get("by_month_day")
    if month_day is not None and (isinstance(month_day, bool) or not isinstance(month_day, int)):
        raise PlaybookValidationError(
            f"Field 'by_month_day' at {path} must be an integer", path=path
        )
    start = _number(data, "start_at", path=path) or 0.0
    end = _number(data, "end_at", path=path) or 0.0
    count_raw = data.get("count", 0)
    if isinstance(count_raw, bool) or not isinstance(count_raw, int):
        raise PlaybookValidationError(f"Field 'count' at {path} must be an integer", path=path)
    interval_raw = data.get("interval", 1)
    if isinstance(interval_raw, bool) or not isinstance(interval_raw, int):
        raise PlaybookValidationError(f"Field 'interval' at {path} must be an integer", path=path)
    hour_raw = data.get("hour", 9)
    minute_raw = data.get("minute", 0)
    if isinstance(hour_raw, bool) or not isinstance(hour_raw, int):
        raise PlaybookValidationError(f"Field 'hour' at {path} must be an integer", path=path)
    if isinstance(minute_raw, bool) or not isinstance(minute_raw, int):
        raise PlaybookValidationError(f"Field 'minute' at {path} must be an integer", path=path)
    return RecurrenceRule(
        frequency=frequency,
        interval=interval_raw,
        by_weekday=tuple(parsed_days),
        by_month_day=month_day,
        hour=hour_raw,
        minute=minute_raw,
        start_at=start,
        end_at=end,
        count=count_raw,
    )


def parse_playbook(payload: Any, *, path: str = "playbook") -> PlaybookDefinition:
    """Parse a complete playbook document from an API payload."""
    data = _mapping(payload, path=path)
    playbook_id = _string(data, "id", path=path, required=True)
    raw_steps = data.get("steps", ())
    if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, dict)):
        raise PlaybookValidationError(f"Field 'steps' at {path} must be a list", path=path)
    steps = tuple(
        parse_step(item, path=f"{path}.steps[{index}]") for index, item in enumerate(raw_steps)
    )
    raw_variables = data.get("variables", ())
    if not isinstance(raw_variables, Sequence) or isinstance(raw_variables, (str, dict)):
        raise PlaybookValidationError(f"Field 'variables' at {path} must be a list", path=path)
    variables = tuple(
        parse_variable(item, path=f"{path}.variables[{index}]")
        for index, item in enumerate(raw_variables)
    )
    recurrence_payload = data.get("recurrence")
    version_raw = data.get("version", 1)
    if isinstance(version_raw, bool) or not isinstance(version_raw, int):
        raise PlaybookValidationError(f"Field 'version' at {path} must be an integer", path=path)
    return PlaybookDefinition(
        id=playbook_id,
        title=_string(data, "title", path=path, required=True) or playbook_id,
        steps=steps,
        variables=variables,
        description=_string(data, "description", path=path),
        version=version_raw,
        tags=_string_tuple(data, "tags", path=path),
        recurrence=(
            parse_recurrence(recurrence_payload, path=f"{path}.recurrence")
            if recurrence_payload is not None
            else None
        ),
    )


def parse_values(payload: Any, *, path: str = "values") -> dict[str, Value]:
    """Parse a variable value map, rejecting non-JSON values."""
    data = _mapping(payload, path=path)
    result: dict[str, Value] = {}
    for key in data:
        result[str(key)] = _value(data, str(key), path=path)
    return result


def issue(code: str, message: str, *, path: str = "", severity: str = "error") -> ValidationIssue:
    """Build a validation diagnostic."""
    return ValidationIssue(code=code, message=message, path=path, severity=severity)
