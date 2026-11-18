"""Validation primitives shared by evidence services and API handlers."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, TypeVar

from redscribe.domain.utils import iso_z, parse_timestamp
from redscribe.v2.evidence.errors import ValidationError

EnumT = TypeVar("EnumT", bound=Enum)

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,79}$")
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
TAG_RE = re.compile(r"^[\w][\w ./+#-]{0,59}$", re.UNICODE)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
FILENAME_INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE_RE = re.compile(r"\s+")


def now_iso() -> str:
    """Return the current UTC time in canonical ISO form."""
    return iso_z(datetime.now(timezone.utc))


def normalize_timestamp(value: str | datetime | None, *, default: str = "") -> str:
    """Normalize a timestamp to UTC ISO form, returning ``default`` if invalid."""
    if value is None:
        return default
    if isinstance(value, datetime):
        return iso_z(value)
    parsed = parse_timestamp(value)
    return iso_z(parsed) if parsed is not None else default


def shift_timestamp(value: str, *, days: int = 0, hours: int = 0) -> str:
    """Shift a normalized timestamp by a whole number of days or hours."""
    parsed = parse_timestamp(value)
    if parsed is None:
        return ""
    return iso_z(parsed + timedelta(days=days, hours=hours))


def require_text(
    body: Mapping[str, Any],
    key: str,
    *,
    default: str | None = None,
    max_length: int = 2_000,
    min_length: int = 0,
    strip: bool = True,
    field: str | None = None,
) -> str:
    """Return a required string field, raising a validation error otherwise."""
    name = field or key
    if key not in body or body[key] is None:
        if default is not None:
            return default
        raise ValidationError(f"Missing '{name}'", details={"field": name})
    value = body[key]
    if not isinstance(value, str):
        raise ValidationError(f"'{name}' must be a string", details={"field": name})
    result = value.strip() if strip else value
    if len(result) < min_length:
        raise ValidationError(
            f"'{name}' must contain at least {min_length} characters",
            details={"field": name},
        )
    if len(result) > max_length:
        raise ValidationError(
            f"'{name}' exceeds {max_length} characters",
            details={"field": name},
        )
    if CONTROL_RE.search(result):
        raise ValidationError(f"'{name}' contains control characters", details={"field": name})
    return result


def optional_text(
    body: Mapping[str, Any],
    key: str,
    *,
    default: str = "",
    max_length: int = 2_000,
    strip: bool = True,
    field: str | None = None,
) -> str:
    """Return an optional string field, treating null as absent."""
    name = field or key
    if key not in body or body[key] is None:
        return default
    value = body[key]
    if not isinstance(value, str):
        raise ValidationError(f"'{name}' must be a string", details={"field": name})
    result = value.strip() if strip else value
    if len(result) > max_length:
        raise ValidationError(
            f"'{name}' exceeds {max_length} characters",
            details={"field": name},
        )
    if CONTROL_RE.search(result):
        raise ValidationError(f"'{name}' contains control characters", details={"field": name})
    return result


def require_int(
    body: Mapping[str, Any],
    key: str,
    *,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Return a required integer field, rejecting booleans."""
    value = body.get(key)
    if value is None and default is not None:
        value = default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"'{key}' must be an integer", details={"field": key})
    if minimum is not None and value < minimum:
        raise ValidationError(f"'{key}' must be at least {minimum}", details={"field": key})
    if maximum is not None and value > maximum:
        raise ValidationError(f"'{key}' must be at most {maximum}", details={"field": key})
    return value


def optional_int(
    body: Mapping[str, Any],
    key: str,
    *,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    """Return an optional integer field, rejecting booleans."""
    if key not in body or body[key] is None:
        return default
    return require_int(body, key, minimum=minimum, maximum=maximum)


def optional_float(
    body: Mapping[str, Any],
    key: str,
    *,
    default: float = 0.0,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    """Return an optional bounded floating point field."""
    if key not in body or body[key] is None:
        return default
    value = body[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"'{key}' must be a number", details={"field": key})
    result = float(value)
    if result < minimum or result > maximum:
        raise ValidationError(
            f"'{key}' must be between {minimum} and {maximum}",
            details={"field": key},
        )
    return round(result, 3)


def require_bool(body: Mapping[str, Any], key: str, *, default: bool | None = None) -> bool:
    """Return a required boolean field."""
    value = body.get(key)
    if value is None and default is not None:
        return default
    if not isinstance(value, bool):
        raise ValidationError(f"'{key}' must be a boolean", details={"field": key})
    return value


def coerce_bool(value: object, *, default: bool = False) -> bool:
    """Coerce common textual boolean representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def require_choice(
    body: Mapping[str, Any],
    key: str,
    enum_type: type[EnumT],
    *,
    default: EnumT | None = None,
) -> EnumT:
    """Return an enum member for a required choice field."""
    raw = body.get(key)
    if raw is None and default is not None:
        return default
    if not isinstance(raw, str):
        raise ValidationError(f"'{key}' must be a string", details={"field": key})
    candidate = raw.strip().casefold()
    for member in enum_type:
        if member.value == candidate or member.name.casefold() == candidate:
            return member
    allowed = ", ".join(str(member.value) for member in enum_type)
    raise ValidationError(
        f"Unknown {key}: {raw}",
        details={"field": key, "allowed": allowed},
    )


def validate_evidence_id(value: object, *, field: str = "id") -> str:
    """Validate a public evidence identifier."""
    if not isinstance(value, str):
        raise ValidationError(f"'{field}' must be a string", details={"field": field})
    candidate = value.strip()
    if not ID_RE.fullmatch(candidate):
        raise ValidationError(f"Invalid evidence id: {value}", details={"field": field})
    return candidate


def validate_hex_digest(value: object, *, length: int, field: str = "sha256") -> str:
    """Validate a hexadecimal digest with an exact length."""
    if not isinstance(value, str):
        raise ValidationError(f"'{field}' must be a string", details={"field": field})
    candidate = value.strip().casefold()
    if len(candidate) != length or not HEX_RE.fullmatch(candidate):
        raise ValidationError(
            f"'{field}' must be {length} hexadecimal characters",
            details={"field": field},
        )
    return candidate


def normalize_tags(value: object, *, field: str = "tags") -> tuple[str, ...]:
    """Normalize a list or comma/space separated tag string."""
    if value is None:
        return ()
    if isinstance(value, str):
        candidates: Sequence[object] = re.split(r"[,;\n]+", value)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        candidates = value
    else:
        raise ValidationError(f"'{field}' must be a list or string", details={"field": field})
    result: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if not isinstance(item, str):
            continue
        cleaned = WHITESPACE_RE.sub(" ", item).strip().strip("#")
        if not cleaned or len(cleaned) > 60 or not TAG_RE.fullmatch(cleaned):
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= 24:
            break
    return tuple(result)


def normalize_metadata(value: object) -> dict[str, Any]:
    """Return a JSON-safe metadata mapping with control characters removed."""
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()[:80]
        if not key:
            continue
        result[key] = _clean_metadata_value(raw_value)
    return result


def _clean_metadata_value(value: Any) -> Any:
    if isinstance(value, str):
        return CONTROL_RE.sub("", value)[:2_000]
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _clean_metadata_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_clean_metadata_value(item) for item in value]
    return str(value)[:2_000]


def sanitize_filename(value: object, *, fallback: str = "evidence.bin") -> str:
    """Return a safe basename without path traversal or control characters."""
    if not isinstance(value, str):
        return fallback
    replaced = value.replace("\\", "/").split("/")[-1]
    cleaned = CONTROL_RE.sub("", FILENAME_INVALID_RE.sub("-", replaced)).strip(" .")
    cleaned = unicodedata.normalize("NFC", cleaned)[:255].strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        return fallback
    return cleaned


def file_extension(filename: str) -> str:
    """Return a lowercase extension including the leading dot."""
    name = sanitize_filename(filename)
    if "." not in name:
        return ""
    suffix = name.rsplit(".", 1)[1]
    if not suffix or len(suffix) > 12 or not suffix.isalnum():
        return ""
    return f".{suffix.lower()}"


def validate_limit(value: object, *, default: int = 50, maximum: int = 200) -> int:
    """Validate a pagination limit."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("'limit' must be an integer", details={"field": "limit"})
    if value < 1 or value > maximum:
        raise ValidationError(
            f"'limit' must be between 1 and {maximum}",
            details={"field": "limit"},
        )
    return value


def validate_offset(value: object, *, field: str = "offset") -> int:
    """Validate a non-negative offset."""
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"'{field}' must be a non-negative integer", details={"field": field})
    return value


def validate_case_reference(value: object) -> str:
    """Validate an optional case reference."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError(
            "'case_reference' must be a string", details={"field": "case_reference"}
        )
    return value.strip()[:120]


def validate_retain_days(value: object, *, default: int = 365) -> int:
    """Validate a retention duration in days."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("'retain_days' must be an integer", details={"field": "retain_days"})
    if value < 0 or value > 36_500:
        raise ValidationError(
            "'retain_days' must be between 0 and 36500",
            details={"field": "retain_days"},
        )
    return value
