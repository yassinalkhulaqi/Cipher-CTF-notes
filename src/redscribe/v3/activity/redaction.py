"""Privacy-aware redaction of activity event payloads.

This module builds on the B00 :class:`RedactionPolicy` and text scrubbers. It
adds named rules, an allowlist for display-safe metadata, and a report that the
activity UI can show next to a redacted entry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from redscribe.v3.activity.models import RedactionReport
from redscribe.v3.events.redaction import (
    RedactionPolicy,
    is_sensitive_key,
    redact_text,
)
from redscribe.v3.events.types import EventRecord

DEFAULT_ALLOWED_KEYS: tuple[str, ...] = (
    "title",
    "name",
    "label",
    "status",
    "stage",
    "kind",
    "count",
    "total",
    "severity",
    "entity",
    "ref",
    "progress",
)


@dataclass(frozen=True, slots=True)
class RedactionRule:
    """A named rule that redacts values stored under matching keys."""

    name: str
    keys: tuple[str, ...]
    replacement: str = "[redacted]"
    enabled: bool = True

    def matches(self, key: str) -> bool:
        """Return whether the rule applies to a payload key."""
        if not self.enabled or not self.name:
            return False
        normalized = key.casefold()
        return any(fragment and fragment.casefold() in normalized for fragment in self.keys)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "name": self.name,
            "keys": list(self.keys),
            "replacement": self.replacement,
            "enabled": self.enabled,
        }


class ActivityRedactor:
    """Redacts payloads and records what was changed."""

    def __init__(
        self,
        *,
        extra_keys: tuple[str, ...] = (),
        allowed_keys: tuple[str, ...] = DEFAULT_ALLOWED_KEYS,
        rules: tuple[RedactionRule, ...] = (),
        enabled: bool = True,
        depth_limit: int = 12,
    ) -> None:
        if depth_limit < 1:
            raise ValueError("depth_limit must be positive")
        self._policy = RedactionPolicy(extra_keys=extra_keys, enabled=enabled)
        self._rules = tuple(rules)
        self._extra = frozenset(key.casefold() for key in extra_keys)
        self._allowed = frozenset(key.casefold() for key in allowed_keys)
        self._depth_limit = depth_limit
        self._last_report = RedactionReport()

    @property
    def enabled(self) -> bool:
        """Whether redaction is active."""
        return self._policy.enabled

    @property
    def rules(self) -> tuple[RedactionRule, ...]:
        """Configured named rules."""
        return self._rules

    @property
    def last_report(self) -> RedactionReport:
        """Report produced by the most recent redaction."""
        return self._last_report

    def redact(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Redact a payload, updating ``last_report``."""
        cleaned, report = self.redact_with_report(payload)
        self._last_report = report
        return cleaned

    def redact_with_report(
        self, payload: Mapping[str, Any]
    ) -> tuple[dict[str, Any], RedactionReport]:
        """Redact a payload and return the value together with its report."""
        if not self.enabled:
            return dict(payload), RedactionReport(keys_inspected=len(payload))
        cleaned, report = self._redact_mapping(payload, depth=0)
        return cleaned, report

    def redact_record(self, record: EventRecord) -> tuple[dict[str, Any], RedactionReport]:
        """Redact the payload of a recorded event."""
        return self.redact_with_report(record.event.payload)

    def _redact_mapping(
        self, payload: Mapping[str, Any], *, depth: int
    ) -> tuple[dict[str, Any], RedactionReport]:
        if depth > self._depth_limit:
            return {"_truncated": True}, RedactionReport(dropped_depth=1)
        cleaned: dict[str, Any] = {}
        report = RedactionReport(keys_inspected=len(payload))
        for key, value in payload.items():
            normalized = key.casefold()
            if (
                is_sensitive_key(key)
                or normalized in self._extra
                or self._rule_for(key) is not None
            ):
                rule = self._rule_for(key)
                cleaned[key] = rule.replacement if rule else "[redacted]"
                report = report.merge(RedactionReport(redacted_keys=(key,)))
                continue
            if normalized in self._allowed:
                cleaned[key] = value
                continue
            if isinstance(value, str):
                rewritten = redact_text(value)
                cleaned[key] = rewritten
                if rewritten != value:
                    report = report.merge(RedactionReport(rewritten_values=1))
            elif isinstance(value, Mapping):
                nested, nested_report = self._redact_mapping(value, depth=depth + 1)
                cleaned[key] = nested
                report = report.merge(nested_report)
            elif isinstance(value, (list, tuple)):
                items: list[Any] = []
                for item in value:
                    if isinstance(item, Mapping):
                        nested, nested_report = self._redact_mapping(item, depth=depth + 1)
                        items.append(nested)
                        report = report.merge(nested_report)
                    elif isinstance(item, str):
                        rewritten = redact_text(item)
                        items.append(rewritten)
                        if rewritten != item:
                            report = report.merge(RedactionReport(rewritten_values=1))
                    else:
                        items.append(item)
                cleaned[key] = items
            else:
                cleaned[key] = value
        return cleaned, report

    def _rule_for(self, key: str) -> RedactionRule | None:
        """Return the first rule matching a key."""
        for rule in self._rules:
            if rule.matches(key):
                return rule
        return None


def redact_for_display(
    payload: Mapping[str, Any],
    *,
    extra_keys: tuple[str, ...] = (),
    rules: tuple[RedactionRule, ...] = (),
) -> tuple[dict[str, Any], RedactionReport]:
    """Convenience wrapper for one-shot display redaction."""
    return ActivityRedactor(extra_keys=extra_keys, rules=rules).redact_with_report(payload)


def summarize_redactions(reports: tuple[RedactionReport, ...]) -> RedactionReport:
    """Merge a sequence of redaction reports."""
    total = RedactionReport()
    for report in reports:
        total = total.merge(report)
    return total
