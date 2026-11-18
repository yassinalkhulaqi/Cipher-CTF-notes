"""Safe export scrubbing helpers for reports and structured payloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redscribe.v2.security.redaction import (
    RedactionRule,
    RedactionSummary,
    apply_redactions,
    builtin_redaction_rules,
)


@dataclass(frozen=True, slots=True)
class ScrubPolicy:
    """Policy describing how export payloads should be sanitized."""

    redact_text: bool = True
    remove_keys: tuple[str, ...] = ("password", "secret", "token", "api_key", "authorization")
    mask_keys: tuple[str, ...] = ("email", "ip", "host", "username")
    drop_empty: bool = False
    replacement: str = "[SCRUBBED]"

    def as_dict(self) -> dict[str, Any]:
        return {
            "redact_text": self.redact_text,
            "remove_keys": list(self.remove_keys),
            "mask_keys": list(self.mask_keys),
            "drop_empty": self.drop_empty,
            "replacement": self.replacement,
        }


@dataclass(frozen=True, slots=True)
class ScrubReport:
    """Summary of scrub operations applied to a payload."""

    removed_keys: tuple[str, ...] = ()
    masked_keys: tuple[str, ...] = ()
    redacted_fields: tuple[str, ...] = ()
    redaction_counts: Mapping[str, int] = field(default_factory=dict)
    total_redactions: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "removed_keys": list(self.removed_keys),
            "masked_keys": list(self.masked_keys),
            "redacted_fields": list(self.redacted_fields),
            "redaction_counts": dict(self.redaction_counts),
            "total_redactions": self.total_redactions,
        }


def scrub_text(
    text: str,
    *,
    rules: Sequence[RedactionRule] | None = None,
    policy: ScrubPolicy | None = None,
) -> tuple[str, RedactionSummary]:
    active_policy = policy or ScrubPolicy()
    if not active_policy.redact_text:
        summary = RedactionSummary(text=text, applied=(), counts={}, total_replacements=0)
        return text, summary
    summary = apply_redactions(text, rules=rules or builtin_redaction_rules())
    return summary.text, summary


def _should_remove(key: str, policy: ScrubPolicy) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in policy.remove_keys)


def _should_mask(key: str, policy: ScrubPolicy) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in policy.mask_keys)


def _mask_scalar(value: Any, replacement: str) -> Any:
    if isinstance(value, str):
        if not value:
            return value
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:2]}***{value[-2:]}"
    if isinstance(value, (int, float)):
        return replacement
    return replacement


def _scrub_value(
    key: str,
    value: Any,
    policy: ScrubPolicy,
    rules: Sequence[RedactionRule],
    removed: list[str],
    masked: list[str],
    redacted_fields: list[str],
    redaction_counts: dict[str, int],
    path: str,
) -> Any:
    field_path = f"{path}.{key}" if path else key
    if _should_remove(key, policy):
        removed.append(field_path)
        return policy.replacement
    if _should_mask(key, policy):
        masked.append(field_path)
        return _mask_scalar(value, policy.replacement)

    if isinstance(value, str):
        scrubbed, summary = scrub_text(value, rules=rules, policy=policy)
        if summary.total_replacements:
            redacted_fields.append(field_path)
            for rule_name, count in summary.counts.items():
                redaction_counts[rule_name] = redaction_counts.get(rule_name, 0) + count
        if policy.drop_empty and not scrubbed.strip():
            return ""
        return scrubbed
    if isinstance(value, list):
        return [
            _scrub_value(
                key,
                item,
                policy,
                rules,
                removed,
                masked,
                redacted_fields,
                redaction_counts,
                field_path,
            )
            for item in value
        ]
    if isinstance(value, Mapping):
        return _scrub_mapping(
            value, policy, rules, removed, masked, redacted_fields, redaction_counts, field_path
        )
    return value


def _scrub_mapping(
    payload: Mapping[str, Any],
    policy: ScrubPolicy,
    rules: Sequence[RedactionRule],
    removed: list[str],
    masked: list[str],
    redacted_fields: list[str],
    redaction_counts: dict[str, int],
    path: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in payload.items():
        key_str = str(key)
        scrubbed = _scrub_value(
            key_str,
            value,
            policy,
            rules,
            removed,
            masked,
            redacted_fields,
            redaction_counts,
            path,
        )
        if policy.drop_empty and scrubbed in ("", None, [], {}):
            continue
        result[key_str] = scrubbed
    return result


def scrub_export_payload(
    payload: Mapping[str, Any],
    *,
    policy: ScrubPolicy | None = None,
    rules: Sequence[RedactionRule] | None = None,
) -> tuple[dict[str, Any], ScrubReport]:
    """Scrub a structured export payload and return the cleaned result plus report."""
    active_policy = policy or ScrubPolicy()
    active_rules = tuple(rules or builtin_redaction_rules())
    removed: list[str] = []
    masked: list[str] = []
    redacted_fields: list[str] = []
    redaction_counts: dict[str, int] = {}
    cleaned = _scrub_mapping(
        payload, active_policy, active_rules, removed, masked, redacted_fields, redaction_counts, ""
    )
    report = ScrubReport(
        removed_keys=tuple(sorted(set(removed))),
        masked_keys=tuple(sorted(set(masked))),
        redacted_fields=tuple(sorted(set(redacted_fields))),
        redaction_counts=redaction_counts,
        total_redactions=sum(redaction_counts.values()),
    )
    return cleaned, report
