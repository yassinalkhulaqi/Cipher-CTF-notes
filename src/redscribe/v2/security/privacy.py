"""Privacy levels and operating modes for RedScribe security workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PrivacyLevel(str, Enum):
    OPEN = "open"
    STANDARD = "standard"
    SENSITIVE = "sensitive"
    STRICT = "strict"


@dataclass(frozen=True, slots=True)
class PrivacyMode:
    """Runtime privacy behavior derived from a privacy level."""

    level: PrivacyLevel
    redact_secrets: bool
    mask_identifiers: bool
    allow_external_links: bool
    allow_command_copy: bool
    scrub_exports: bool
    require_export_consent: bool
    retain_audit_details: bool
    share_telemetry: bool

    @property
    def key(self) -> str:
        return self.level.value

    @property
    def rank(self) -> int:
        return PRIVACY_RANK[self.level]

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "redact_secrets": self.redact_secrets,
            "mask_identifiers": self.mask_identifiers,
            "allow_external_links": self.allow_external_links,
            "allow_command_copy": self.allow_command_copy,
            "scrub_exports": self.scrub_exports,
            "require_export_consent": self.require_export_consent,
            "retain_audit_details": self.retain_audit_details,
            "share_telemetry": self.share_telemetry,
            "rank": self.rank,
        }


PRIVACY_LEVELS: dict[str, PrivacyMode] = {
    "open": PrivacyMode(
        level=PrivacyLevel.OPEN,
        redact_secrets=False,
        mask_identifiers=False,
        allow_external_links=True,
        allow_command_copy=True,
        scrub_exports=False,
        require_export_consent=False,
        retain_audit_details=True,
        share_telemetry=True,
    ),
    "standard": PrivacyMode(
        level=PrivacyLevel.STANDARD,
        redact_secrets=True,
        mask_identifiers=False,
        allow_external_links=True,
        allow_command_copy=True,
        scrub_exports=True,
        require_export_consent=False,
        retain_audit_details=True,
        share_telemetry=False,
    ),
    "sensitive": PrivacyMode(
        level=PrivacyLevel.SENSITIVE,
        redact_secrets=True,
        mask_identifiers=True,
        allow_external_links=False,
        allow_command_copy=True,
        scrub_exports=True,
        require_export_consent=True,
        retain_audit_details=False,
        share_telemetry=False,
    ),
    "strict": PrivacyMode(
        level=PrivacyLevel.STRICT,
        redact_secrets=True,
        mask_identifiers=True,
        allow_external_links=False,
        allow_command_copy=False,
        scrub_exports=True,
        require_export_consent=True,
        retain_audit_details=False,
        share_telemetry=False,
    ),
}

PRIVACY_RANK = {
    PrivacyLevel.OPEN: 0,
    PrivacyLevel.STANDARD: 1,
    PrivacyLevel.SENSITIVE: 2,
    PrivacyLevel.STRICT: 3,
}

ALIASES = {
    "default": PrivacyLevel.STANDARD,
    "normal": PrivacyLevel.STANDARD,
    "private": PrivacyLevel.SENSITIVE,
    "locked": PrivacyLevel.STRICT,
    "high": PrivacyLevel.STRICT,
}


def parse_privacy_level(value: str | PrivacyLevel | None) -> PrivacyLevel:
    """Parse a privacy level from user input."""
    if value is None:
        return PrivacyLevel.STANDARD
    if isinstance(value, PrivacyLevel):
        return value
    normalized = value.strip().lower()
    if not normalized:
        return PrivacyLevel.STANDARD
    try:
        return PrivacyLevel(normalized)
    except ValueError:
        alias = ALIASES.get(normalized)
        if alias is None:
            raise ValueError(f"Unknown privacy level: {value}") from None
        return alias


def privacy_mode_for(value: str | PrivacyLevel | None) -> PrivacyMode:
    """Return the privacy mode for a level or alias."""
    level = parse_privacy_level(value)
    return PRIVACY_LEVELS[level.value]


def apply_privacy_level(level: str | PrivacyLevel | None) -> dict[str, Any]:
    """Return a serializable privacy configuration for API/UI consumers."""
    mode = privacy_mode_for(level)
    data = mode.as_dict()
    data["label"] = mode.level.value.title()
    data["description"] = describe_privacy_level(mode.level)
    data["controls"] = privacy_controls(mode)
    return data


def describe_privacy_level(level: PrivacyLevel) -> str:
    descriptions = {
        PrivacyLevel.OPEN: "Minimal restrictions for local-only, low-sensitivity work.",
        PrivacyLevel.STANDARD: "Redacts obvious secrets and scrubs exports by default.",
        PrivacyLevel.SENSITIVE: "Masks identifiers, blocks external links, and requires consent.",
        PrivacyLevel.STRICT: "Maximum local privacy with restricted copy/export behavior.",
    }
    return descriptions[level]


def privacy_controls(mode: PrivacyMode) -> list[dict[str, Any]]:
    return [
        {
            "key": "redact_secrets",
            "label": "Redact secrets",
            "enabled": mode.redact_secrets,
            "category": "content",
        },
        {
            "key": "mask_identifiers",
            "label": "Mask identifiers",
            "enabled": mode.mask_identifiers,
            "category": "content",
        },
        {
            "key": "allow_external_links",
            "label": "Allow external links",
            "enabled": mode.allow_external_links,
            "category": "navigation",
        },
        {
            "key": "allow_command_copy",
            "label": "Allow command copy",
            "enabled": mode.allow_command_copy,
            "category": "actions",
        },
        {
            "key": "scrub_exports",
            "label": "Scrub exports",
            "enabled": mode.scrub_exports,
            "category": "export",
        },
        {
            "key": "require_export_consent",
            "label": "Require export consent",
            "enabled": mode.require_export_consent,
            "category": "export",
        },
        {
            "key": "retain_audit_details",
            "label": "Retain audit details",
            "enabled": mode.retain_audit_details,
            "category": "audit",
        },
        {
            "key": "share_telemetry",
            "label": "Share telemetry",
            "enabled": mode.share_telemetry,
            "category": "telemetry",
        },
    ]


def compare_privacy_levels(left: str | PrivacyLevel, right: str | PrivacyLevel) -> int:
    """Return -1, 0, or 1 comparing privacy strictness."""
    left_rank = privacy_mode_for(left).rank
    right_rank = privacy_mode_for(right).rank
    if left_rank == right_rank:
        return 0
    return -1 if left_rank < right_rank else 1


def merge_privacy_preferences(
    base: str | PrivacyLevel | None,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge explicit control overrides onto a base privacy level."""
    mode = apply_privacy_level(base)
    mode["customized"] = False
    if not overrides:
        return mode
    controls = {item["key"]: dict(item) for item in mode["controls"]}
    for key, value in overrides.items():
        if key in controls and isinstance(value, bool):
            controls[key]["enabled"] = value
            mode[key] = value
    mode["controls"] = [controls[key] for key in sorted(controls)]
    mode["customized"] = bool(overrides)
    return mode
