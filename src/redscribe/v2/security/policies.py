"""Access policy evaluation for security-sensitive RedScribe operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class AccessDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """A single access rule matched against a request context."""

    name: str
    effect: PolicyEffect = PolicyEffect.DENY
    actions: tuple[str, ...] = ("*",)
    roles: tuple[str, ...] = ("*",)
    resources: tuple[str, ...] = ("*",)
    conditions: Mapping[str, Any] = field(default_factory=dict)
    priority: int = 100
    reason: str = ""

    def matches(self, action: str, *, role: str, resource: str, context: Mapping[str, Any]) -> bool:
        if not _matches_any(action, self.actions):
            return False
        if not _matches_any(role, self.roles):
            return False
        if not _matches_any(resource, self.resources):
            return False
        return _conditions_match(self.conditions, context)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "effect": self.effect.value,
            "actions": list(self.actions),
            "roles": list(self.roles),
            "resources": list(self.resources),
            "conditions": dict(self.conditions),
            "priority": self.priority,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    """Result of evaluating a request against a policy set."""

    decision: AccessDecision
    matched_rules: tuple[str, ...]
    reasons: tuple[str, ...]
    action: str
    role: str
    resource: str

    @property
    def allowed(self) -> bool:
        return self.decision == AccessDecision.ALLOW

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "allowed": self.allowed,
            "matched_rules": list(self.matched_rules),
            "reasons": list(self.reasons),
            "action": self.action,
            "role": self.role,
            "resource": self.resource,
        }


@dataclass(frozen=True, slots=True)
class AccessPolicy:
    """A named collection of ordered access rules."""

    name: str
    rules: tuple[PolicyRule, ...] = ()
    default_decision: AccessDecision = AccessDecision.DENY
    description: str = ""

    def evaluate(
        self,
        action: str,
        *,
        role: str = "anonymous",
        resource: str = "*",
        context: Mapping[str, Any] | None = None,
    ) -> PolicyEvaluation:
        ctx = context or {}
        matched: list[PolicyRule] = []
        for rule in sorted(self.rules, key=lambda item: (item.priority, item.name)):
            if rule.matches(action, role=role, resource=resource, context=ctx):
                matched.append(rule)
        if not matched:
            return PolicyEvaluation(
                decision=self.default_decision,
                matched_rules=(),
                reasons=(f"default:{self.default_decision.value}",),
                action=action,
                role=role,
                resource=resource,
            )
        deny_rules = [rule for rule in matched if rule.effect == PolicyEffect.DENY]
        allow_rules = [rule for rule in matched if rule.effect == PolicyEffect.ALLOW]
        if deny_rules:
            reasons = tuple(rule.reason or f"denied:{rule.name}" for rule in deny_rules)
            return PolicyEvaluation(
                decision=AccessDecision.DENY,
                matched_rules=tuple(rule.name for rule in matched),
                reasons=reasons,
                action=action,
                role=role,
                resource=resource,
            )
        reasons = tuple(rule.reason or f"allowed:{rule.name}" for rule in allow_rules)
        return PolicyEvaluation(
            decision=AccessDecision.ALLOW,
            matched_rules=tuple(rule.name for rule in matched),
            reasons=reasons,
            action=action,
            role=role,
            resource=resource,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "default_decision": self.default_decision.value,
            "rules": [rule.as_dict() for rule in self.rules],
        }


class PolicyEngine:
    """Evaluate requests across multiple named policies."""

    def __init__(self, policies: Sequence[AccessPolicy] | None = None) -> None:
        self._policies: dict[str, AccessPolicy] = {}
        for policy in policies or ():
            self.add_policy(policy)

    @property
    def policies(self) -> tuple[AccessPolicy, ...]:
        return tuple(self._policies[name] for name in sorted(self._policies))

    def add_policy(self, policy: AccessPolicy) -> None:
        self._policies[policy.name] = policy

    def get_policy(self, name: str) -> AccessPolicy | None:
        return self._policies.get(name)

    def evaluate(
        self,
        action: str,
        *,
        role: str = "anonymous",
        resource: str = "*",
        context: Mapping[str, Any] | None = None,
        policy_names: Sequence[str] | None = None,
    ) -> PolicyEvaluation:
        selected = self._select_policies(policy_names)
        if not selected:
            return PolicyEvaluation(
                decision=AccessDecision.REVIEW,
                matched_rules=(),
                reasons=("no_policy",),
                action=action,
                role=role,
                resource=resource,
            )
        matched_rules: list[str] = []
        reasons: list[str] = []
        for policy in selected:
            result = policy.evaluate(action, role=role, resource=resource, context=context)
            matched_rules.extend(f"{policy.name}:{name}" for name in result.matched_rules)
            reasons.extend(result.reasons)
            if result.decision == AccessDecision.DENY:
                return PolicyEvaluation(
                    decision=AccessDecision.DENY,
                    matched_rules=tuple(matched_rules),
                    reasons=tuple(reasons),
                    action=action,
                    role=role,
                    resource=resource,
                )
        if any(reason.startswith("allowed:") for reason in reasons):
            return PolicyEvaluation(
                decision=AccessDecision.ALLOW,
                matched_rules=tuple(matched_rules),
                reasons=tuple(reasons),
                action=action,
                role=role,
                resource=resource,
            )
        return PolicyEvaluation(
            decision=AccessDecision.REVIEW,
            matched_rules=tuple(matched_rules),
            reasons=tuple(reasons or ("review_required",)),
            action=action,
            role=role,
            resource=resource,
        )

    def _select_policies(self, names: Sequence[str] | None) -> tuple[AccessPolicy, ...]:
        if names is None:
            return self.policies
        selected: list[AccessPolicy] = []
        for name in names:
            policy = self._policies.get(name)
            if policy is not None:
                selected.append(policy)
        return tuple(selected)


def _matches_any(value: str, patterns: Iterable[str]) -> bool:
    normalized = value.strip().lower()
    for pattern in patterns:
        candidate = pattern.strip().lower()
        if candidate == "*":
            return True
        if candidate.endswith("*") and normalized.startswith(candidate[:-1]):
            return True
        if candidate.startswith("*") and normalized.endswith(candidate[1:]):
            return True
        if normalized == candidate:
            return True
    return False


def _conditions_match(conditions: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    for key, expected in conditions.items():
        actual = context.get(key)
        if isinstance(expected, (list, tuple, set, frozenset)):
            if actual not in expected:
                return False
            continue
        if callable(expected):
            try:
                if not bool(expected(actual)):
                    return False
            except Exception:
                return False
            continue
        if actual != expected:
            return False
    return True


def default_access_policy() -> AccessPolicy:
    """Return a conservative default policy for local-first workflows."""
    return AccessPolicy(
        name="default",
        description="Conservative defaults for note, export, and security operations.",
        default_decision=AccessDecision.REVIEW,
        rules=(
            PolicyRule(
                name="allow_read",
                effect=PolicyEffect.ALLOW,
                actions=("read", "view", "scan", "preview"),
                roles=("owner", "editor", "viewer", "operator", "*"),
                resources=("note", "export", "report", "security", "*"),
                priority=50,
                reason="read operations are allowed by default",
            ),
            PolicyRule(
                name="allow_security_tools",
                effect=PolicyEffect.ALLOW,
                actions=("security.*", "redact", "scrub", "audit"),
                roles=("owner", "editor", "operator", "*"),
                priority=40,
                reason="security analysis actions are locally permitted",
            ),
            PolicyRule(
                name="deny_sensitive_export_without_consent",
                effect=PolicyEffect.DENY,
                actions=("export", "share", "sync"),
                roles=("*",),
                resources=("export", "report", "note", "*"),
                conditions={"contains_secrets": True, "consent_export_sensitive": False},
                priority=10,
                reason="sensitive export requires explicit consent",
            ),
            PolicyRule(
                name="allow_export_with_consent",
                effect=PolicyEffect.ALLOW,
                actions=("export", "share"),
                roles=("owner", "editor", "operator", "*"),
                resources=("export", "report", "note", "*"),
                conditions={"consent_export_sensitive": True},
                priority=20,
                reason="export allowed with consent",
            ),
        ),
    )


def evaluate_access(
    action: str,
    *,
    role: str = "anonymous",
    resource: str = "*",
    context: Mapping[str, Any] | None = None,
    policy: AccessPolicy | None = None,
) -> PolicyEvaluation:
    """Evaluate one request against a policy or the default policy."""
    active = policy or default_access_policy()
    return active.evaluate(action, role=role, resource=resource, context=context)
