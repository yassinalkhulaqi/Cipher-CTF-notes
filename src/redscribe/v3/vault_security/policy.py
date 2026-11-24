"""Vault policy engine for secret patterns, redaction, and consent gates."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

MAX_SCAN_CHARS = 200_000
REDACTED_TOKEN = "[redacted]"


class PatternKind(str, Enum):
    """Classification of a detected secret."""

    API_KEY = "api_key"
    PRIVATE_KEY = "private_key"
    PASSWORD = "password"
    TOKEN = "token"
    CREDENTIAL = "credential"
    FLAG = "flag"
    CUSTOM = "custom"


class RedactionMode(str, Enum):
    """How a detected secret is transformed before display or export."""

    MASK = "mask"
    HASH = "hash"
    REMOVE = "remove"


class ConsentScope(str, Enum):
    """Actions that may require explicit user consent."""

    EXPORT_PLAINTEXT = "export_plaintext"
    SHARE_EXTERNAL = "share_external"
    AI_ASSIST = "ai_assist"
    LOG_CONTENT = "log_content"


class PolicyError(Exception):
    """Raised for an invalid policy definition."""


@dataclass(frozen=True, slots=True)
class SecretPattern:
    """A named regular expression that identifies one class of secret."""

    name: str
    expression: str
    kind: PatternKind = PatternKind.CUSTOM
    severity: str = "medium"
    description: str = ""
    enabled: bool = True
    default_mode: RedactionMode = RedactionMode.MASK

    def __post_init__(self) -> None:
        if not self.name or not re.fullmatch(r"[a-z][a-z0-9_]{2,47}", self.name):
            raise PolicyError("Pattern name must be 3-48 lowercase characters")
        if not self.expression:
            raise PolicyError("Pattern expression cannot be empty")
        if self.severity not in ("low", "medium", "high", "critical"):
            raise PolicyError("Invalid severity")
        try:
            re.compile(self.expression)
        except re.error as error:
            raise PolicyError(f"Invalid pattern expression: {error}") from error

    def finditer(self, text: str) -> Iterable[re.Match[str]]:
        """Yield matches of this pattern in the supplied text."""
        if not self.enabled:
            return ()
        return re.finditer(self.expression, text)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation of pattern metadata."""
        return {
            "name": self.name,
            "kind": self.kind.value,
            "severity": self.severity,
            "description": self.description,
            "enabled": self.enabled,
            "default_mode": self.default_mode.value,
        }


def builtin_patterns() -> tuple[SecretPattern, ...]:
    """Return the built-in secret detectors shipped with the vault."""
    return (
        SecretPattern(
            name="aws_access_key",
            expression=r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
            kind=PatternKind.API_KEY,
            severity="critical",
            description="AWS access key identifier",
        ),
        SecretPattern(
            name="github_token",
            expression=r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b",
            kind=PatternKind.TOKEN,
            severity="critical",
            description="GitHub personal access token",
        ),
        SecretPattern(
            name="private_key_block",
            expression=r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
            kind=PatternKind.PRIVATE_KEY,
            severity="critical",
            description="PEM private key header",
        ),
        SecretPattern(
            name="assigned_password",
            expression=r"(?i)\b(?:password|passwd|pwd|secret)\b\s*[:=]\s*\S{6,}",
            kind=PatternKind.PASSWORD,
            severity="high",
            description="Password or secret assigned in configuration text",
        ),
        SecretPattern(
            name="bearer_token",
            expression=r"(?i)\bbearer\s+[A-Za-z0-9._-]{12,}",
            kind=PatternKind.TOKEN,
            severity="high",
            description="Bearer authorization token",
        ),
        SecretPattern(
            name="jwt_token",
            expression=r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
            kind=PatternKind.TOKEN,
            severity="high",
            description="JSON web token",
        ),
        SecretPattern(
            name="ctf_flag",
            expression=r"\b(?:flag|ctf)\{[^}\s]{3,200}\}",
            kind=PatternKind.FLAG,
            severity="high",
            description="CTF flag literal",
        ),
    )


@dataclass(frozen=True, slots=True)
class SecretMatch:
    """Location and classification of a detected secret, without its value."""

    pattern_name: str
    kind: PatternKind
    severity: str
    start: int
    end: int

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without the matched text."""
        return {
            "pattern": self.pattern_name,
            "kind": self.kind.value,
            "severity": self.severity,
            "start": self.start,
            "end": self.end,
            "length": self.end - self.start,
        }


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """A precedence-ordered override for one pattern or all patterns."""

    rule_id: str
    pattern_name: str
    mode: RedactionMode
    priority: int = 0
    enabled: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id or len(self.rule_id) > 64:
            raise PolicyError("Rule id must be 1-64 characters")
        if not self.pattern_name:
            raise PolicyError("Rule pattern name cannot be empty")
        if not -1000 <= self.priority <= 1000:
            raise PolicyError("Rule priority must be between -1000 and 1000")

    def applies_to(self, pattern_name: str) -> bool:
        """Whether this rule governs the named pattern."""
        return self.enabled and self.pattern_name in ("*", pattern_name)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "rule_id": self.rule_id,
            "pattern": self.pattern_name,
            "mode": self.mode.value,
            "priority": self.priority,
            "enabled": self.enabled,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ConsentDecision:
    """Result of evaluating an action against the consent registry."""

    scope: ConsentScope
    granted: bool
    requires_prompt: bool
    granted_by: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "scope": self.scope.value,
            "granted": self.granted,
            "requires_prompt": self.requires_prompt,
            "granted_by": self.granted_by,
            "reason": self.reason,
        }


class ConsentRegistry:
    """Stores explicit, revocable consent for sensitive scopes."""

    def __init__(self) -> None:
        self._grants: dict[ConsentScope, tuple[str, float]] = {}

    def grant(self, scope: ConsentScope, *, actor: str, at: float) -> None:
        """Record consent for a scope."""
        if not actor:
            raise PolicyError("Consent actor cannot be empty")
        self._grants[scope] = (actor, at)

    def revoke(self, scope: ConsentScope) -> bool:
        """Revoke consent, returning whether it was present."""
        return self._grants.pop(scope, None) is not None

    def granted(self, scope: ConsentScope) -> bool:
        """Return whether consent is active for a scope."""
        return scope in self._grants

    def decide(self, scope: ConsentScope) -> ConsentDecision:
        """Build a decision for a scope."""
        grant = self._grants.get(scope)
        if grant is not None:
            return ConsentDecision(
                scope=scope,
                granted=True,
                requires_prompt=False,
                granted_by=grant[0],
                reason="Consent explicitly granted",
            )
        return ConsentDecision(
            scope=scope,
            granted=False,
            requires_prompt=True,
            reason="Explicit consent required",
        )

    def snapshot(self) -> dict[str, Any]:
        """Return a secret-free consent summary."""
        return {
            "granted": sorted(scope.value for scope in self._grants),
            "pending": sorted(scope.value for scope in ConsentScope if scope not in self._grants),
        }


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Text after redaction plus non-sensitive metadata about what changed."""

    text: str
    matches: tuple[SecretMatch, ...]
    applied_rules: tuple[str, ...]
    redactions: int

    @property
    def changed(self) -> bool:
        """Whether any secret was transformed."""
        return self.redactions > 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without secret values."""
        return {
            "text": self.text,
            "matches": [match.as_dict() for match in self.matches],
            "applied_rules": list(self.applied_rules),
            "redactions": self.redactions,
        }


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Outcome of combining detection, redaction, and consent."""

    allowed: bool
    scope: ConsentScope
    requires_consent: bool
    redactions: int
    matched_patterns: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "allowed": self.allowed,
            "scope": self.scope.value,
            "requires_consent": self.requires_consent,
            "redactions": self.redactions,
            "matched_patterns": list(self.matched_patterns),
            "reason": self.reason,
        }


_CONSENT_SCOPES = (
    ConsentScope.EXPORT_PLAINTEXT,
    ConsentScope.SHARE_EXTERNAL,
    ConsentScope.AI_ASSIST,
)


class PolicyEngine:
    """Mutable policy state that never retains raw secret values."""

    def __init__(
        self,
        *,
        patterns: Iterable[SecretPattern] | None = None,
        rules: Iterable[PolicyRule] | None = None,
        consents: ConsentRegistry | None = None,
    ) -> None:
        self._patterns: dict[str, SecretPattern] = {
            pattern.name: pattern
            for pattern in (patterns if patterns is not None else builtin_patterns())
        }
        self._rules: dict[str, PolicyRule] = {rule.rule_id: rule for rule in (rules or ())}
        self._consents = consents or ConsentRegistry()

    @property
    def consents(self) -> ConsentRegistry:
        """The consent registry owned by this engine."""
        return self._consents

    def patterns(self) -> tuple[SecretPattern, ...]:
        """Return patterns in stable name order."""
        return tuple(self._patterns[name] for name in sorted(self._patterns))

    def rules(self) -> tuple[PolicyRule, ...]:
        """Return rules in precedence order, highest first."""
        return tuple(sorted(self._rules.values(), key=lambda rule: (-rule.priority, rule.rule_id)))

    def add_pattern(self, pattern: SecretPattern) -> None:
        """Add or replace a named pattern."""
        self._patterns[pattern.name] = pattern

    def remove_pattern(self, name: str) -> bool:
        """Remove a custom pattern by name."""
        return self._patterns.pop(name, None) is not None

    def add_rule(self, rule: PolicyRule) -> None:
        """Add or replace a rule by identifier."""
        self._rules[rule.rule_id] = rule

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by identifier."""
        return self._rules.pop(rule_id, None) is not None

    def scan(self, text: str) -> tuple[SecretMatch, ...]:
        """Return all non-overlapping secret matches in the text."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        sample = text[:MAX_SCAN_CHARS]
        matches: list[SecretMatch] = []
        for pattern in self.patterns():
            for found in pattern.finditer(sample):
                matches.append(
                    SecretMatch(
                        pattern_name=pattern.name,
                        kind=pattern.kind,
                        severity=pattern.severity,
                        start=found.start(),
                        end=found.end(),
                    )
                )
        matches.sort(
            key=lambda match: (match.start, -(match.end - match.start), match.pattern_name)
        )
        return tuple(_without_overlaps(matches))

    def redact(self, text: str) -> RedactionResult:
        """Apply precedence-ordered redaction rules to the text."""
        matches = self.scan(text)
        if not matches:
            return RedactionResult(text=text, matches=(), applied_rules=(), redactions=0)
        pieces: list[str] = []
        cursor = 0
        applied: list[str] = []
        for match in matches:
            pieces.append(text[cursor : match.start])
            mode, rule_id = self._mode_for(match.pattern_name)
            pieces.append(_render_redaction(text[match.start : match.end], mode))
            applied.append(rule_id or f"default:{match.pattern_name}")
            cursor = match.end
        pieces.append(text[cursor:])
        return RedactionResult(
            text="".join(pieces),
            matches=matches,
            applied_rules=tuple(dict.fromkeys(applied)),
            redactions=len(matches),
        )

    def evaluate(self, text: str, scope: ConsentScope) -> PolicyDecision:
        """Evaluate an action against detection, redaction, and consent."""
        result = self.redact(text)
        names = tuple(dict.fromkeys(match.pattern_name for match in result.matches))
        if not result.changed:
            return PolicyDecision(
                allowed=True,
                scope=scope,
                requires_consent=False,
                redactions=0,
                matched_patterns=(),
                reason="No secret patterns matched",
            )
        if scope is ConsentScope.LOG_CONTENT:
            return PolicyDecision(
                allowed=True,
                scope=scope,
                requires_consent=False,
                redactions=result.redactions,
                matched_patterns=names,
                reason="Content logging always uses redacted text",
            )
        if scope in _CONSENT_SCOPES and not self._consents.granted(scope):
            return PolicyDecision(
                allowed=False,
                scope=scope,
                requires_consent=True,
                redactions=result.redactions,
                matched_patterns=names,
                reason="Secrets detected and consent has not been granted",
            )
        return PolicyDecision(
            allowed=True,
            scope=scope,
            requires_consent=False,
            redactions=result.redactions,
            matched_patterns=names,
            reason="Redaction applied and consent is active",
        )

    def assert_clean(self, text: str) -> None:
        """Raise when the text contains a configured secret pattern."""
        matches = self.scan(text)
        if matches:
            raise PolicyError(f"Secret pattern detected: {matches[0].pattern_name}")

    def replace_all(self, rules: Iterable[Mapping[str, Any]]) -> int:
        """Replace the full rule set from serialized rule mappings."""
        replacement: dict[str, PolicyRule] = {}
        for payload in rules:
            rule = PolicyRule(
                rule_id=str(payload["rule_id"]),
                pattern_name=str(payload["pattern"]),
                mode=RedactionMode(str(payload.get("mode", RedactionMode.MASK.value))),
                priority=int(payload.get("priority", 0)),
                enabled=bool(payload.get("enabled", True)),
                reason=str(payload.get("reason", "")),
            )
            replacement[rule.rule_id] = rule
        self._rules = replacement
        return len(replacement)

    def snapshot(self) -> dict[str, Any]:
        """Return a secret-free policy summary for dashboards."""
        return {
            "patterns": [pattern.as_dict() for pattern in self.patterns()],
            "rules": [rule.as_dict() for rule in self.rules()],
            "consents": self._consents.snapshot(),
            "max_scan_chars": MAX_SCAN_CHARS,
        }

    def _mode_for(self, pattern_name: str) -> tuple[RedactionMode, str]:
        pattern = self._patterns.get(pattern_name)
        default = pattern.default_mode if pattern is not None else RedactionMode.MASK
        for rule in self.rules():
            if rule.applies_to(pattern_name):
                return rule.mode, rule.rule_id
        return default, ""


def _without_overlaps(matches: list[SecretMatch]) -> list[SecretMatch]:
    selected: list[SecretMatch] = []
    occupied_until = 0
    for match in matches:
        if match.start < occupied_until:
            continue
        selected.append(match)
        occupied_until = match.end
    return selected


def _render_redaction(value: str, mode: RedactionMode) -> str:
    if mode is RedactionMode.REMOVE:
        return ""
    if mode is RedactionMode.HASH:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        return f"[hash:{digest}]"
    return REDACTED_TOKEN


def masked_preview(value: str, *, visible: int = 4) -> str:
    """Return a safe short preview that never contains the full secret."""
    if visible < 0:
        raise ValueError("visible cannot be negative")
    clean = value.strip()
    if len(clean) <= visible:
        return "*" * len(clean)
    return f"{clean[:visible]}{'*' * min(8, len(clean) - visible)}"


def policy_rules_from_dict(payload: Mapping[str, Any]) -> list[PolicyRule]:
    """Parse a serialized rule list, rejecting malformed entries."""
    raw_rules = payload.get("rules", [])
    if not isinstance(raw_rules, (list, tuple)):
        raise PolicyError("rules must be a list")
    return [
        PolicyRule(
            rule_id=str(rule["rule_id"]),
            pattern_name=str(rule["pattern"]),
            mode=RedactionMode(str(rule.get("mode", RedactionMode.MASK.value))),
            priority=int(rule.get("priority", 0)),
            enabled=bool(rule.get("enabled", True)),
            reason=str(rule.get("reason", "")),
        )
        for rule in raw_rules
        if isinstance(rule, Mapping)
    ]


_default_patterns = builtin_patterns()
DEFAULT_POLICY_RULES: tuple[PolicyRule, ...] = (
    PolicyRule(
        rule_id="default-private-key-remove",
        pattern_name="private_key_block",
        mode=RedactionMode.REMOVE,
        priority=5,
        reason="Private key blocks are removed from every export",
    ),
    PolicyRule(
        rule_id="default-ctf-flag-mask",
        pattern_name="ctf_flag",
        mode=RedactionMode.MASK,
        priority=4,
        reason="Flags are masked even inside research notes",
    ),
)


def default_policy() -> PolicyEngine:
    """Build a policy engine with the shipped patterns and safety rules."""
    return PolicyEngine(patterns=_default_patterns, rules=DEFAULT_POLICY_RULES)
