"""Consent flags and records for privacy-sensitive operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class ConsentFlag:
    """Definition of a consent choice available to the user."""

    key: str
    label: str
    description: str
    required_for: tuple[str, ...] = ()
    default: bool = False
    sensitive: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "required_for": list(self.required_for),
            "default": self.default,
            "sensitive": self.sensitive,
        }


@dataclass(frozen=True, slots=True)
class ConsentDecision:
    """A recorded consent decision for one flag."""

    key: str
    granted: bool
    source: str = "user"
    recorded_at: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "granted": self.granted,
            "source": self.source,
            "recorded_at": self.recorded_at,
            "note": self.note,
        }


DEFAULT_FLAGS: tuple[ConsentFlag, ...] = (
    ConsentFlag(
        key="export_sensitive",
        label="Export sensitive data",
        description="Allow exports that may contain secrets or identifiers after review.",
        required_for=("export", "share", "report"),
        default=False,
    ),
    ConsentFlag(
        key="retain_audit_details",
        label="Retain detailed audit metadata",
        description="Store richer audit details for local troubleshooting and review.",
        required_for=("audit",),
        default=True,
        sensitive=False,
    ),
    ConsentFlag(
        key="open_external_links",
        label="Open external links",
        description="Allow opening external URLs from notes and findings.",
        required_for=("open_link",),
        default=False,
        sensitive=False,
    ),
    ConsentFlag(
        key="copy_commands",
        label="Copy potentially dangerous commands",
        description="Allow copying commands that may be destructive or unsafe.",
        required_for=("copy_command",),
        default=True,
        sensitive=False,
    ),
    ConsentFlag(
        key="store_encrypted_exports",
        label="Store encrypted exports",
        description="Permit writing encrypted export artifacts to disk.",
        required_for=("export",),
        default=True,
        sensitive=False,
    ),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ConsentRegistry:
    """Track consent flags and current decisions."""

    flags: dict[str, ConsentFlag] = field(default_factory=dict)
    decisions: dict[str, ConsentDecision] = field(default_factory=dict)

    @classmethod
    def with_defaults(cls) -> ConsentRegistry:
        registry = cls()
        for flag in DEFAULT_FLAGS:
            registry.register_flag(flag)
            registry.decisions[flag.key] = ConsentDecision(
                key=flag.key,
                granted=flag.default,
                source="default",
                recorded_at=_now_iso(),
                note="default",
            )
        return registry

    def register_flag(self, flag: ConsentFlag) -> None:
        self.flags[flag.key] = flag

    def set_decision(
        self,
        key: str,
        granted: bool,
        *,
        source: str = "user",
        note: str = "",
    ) -> ConsentDecision:
        if key not in self.flags:
            raise KeyError(f"Unknown consent flag: {key}")
        decision = ConsentDecision(
            key=key,
            granted=bool(granted),
            source=source,
            recorded_at=_now_iso(),
            note=note,
        )
        self.decisions[key] = decision
        return decision

    def is_granted(self, key: str) -> bool:
        decision = self.decisions.get(key)
        if decision is not None:
            return decision.granted
        flag = self.flags.get(key)
        return bool(flag.default) if flag else False

    def required_for(self, action: str) -> tuple[ConsentFlag, ...]:
        normalized = action.strip().lower()
        required = []
        for flag in self.flags.values():
            targets = {item.strip().lower() for item in flag.required_for}
            if normalized in targets:
                required.append(flag)
        return tuple(sorted(required, key=lambda item: item.key))

    def missing_for(self, action: str) -> tuple[ConsentFlag, ...]:
        missing = [flag for flag in self.required_for(action) if not self.is_granted(flag.key)]
        return tuple(missing)

    def context(self) -> dict[str, bool]:
        return {
            f"consent_{flag.key}": self.is_granted(flag.key)
            for flag in sorted(self.flags.values(), key=lambda item: item.key)
        }

    def summary(self) -> dict[str, Any]:
        return consent_summary(self.flags.values(), self.decisions.values())

    def apply_bulk(
        self, updates: Mapping[str, Any], *, source: str = "user"
    ) -> list[dict[str, Any]]:
        changed: list[dict[str, Any]] = []
        for key, value in updates.items():
            if key not in self.flags or not isinstance(value, bool):
                continue
            decision = self.set_decision(key, value, source=source)
            changed.append(decision.as_dict())
        return changed


def consent_summary(
    flags: Iterable[ConsentFlag], decisions: Iterable[ConsentDecision]
) -> dict[str, Any]:
    flag_map = {flag.key: flag for flag in flags}
    decision_map = {decision.key: decision for decision in decisions}
    items: list[dict[str, Any]] = []
    granted = 0
    for key in sorted(flag_map):
        flag = flag_map[key]
        decision = decision_map.get(key)
        is_granted = decision.granted if decision else flag.default
        if is_granted:
            granted += 1
        items.append(
            {
                "flag": flag.as_dict(),
                "decision": (
                    decision.as_dict()
                    if decision
                    else ConsentDecision(
                        key=key,
                        granted=flag.default,
                        source="default",
                        recorded_at="",
                        note="implicit default",
                    ).as_dict()
                ),
                "granted": is_granted,
            }
        )
    total = len(items)
    return {
        "total": total,
        "granted": granted,
        "denied": total - granted,
        "items": items,
    }
