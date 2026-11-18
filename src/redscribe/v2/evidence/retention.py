"""Retention policies, legal holds, and disposition planning."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from redscribe.domain.utils import iso_z, parse_timestamp
from redscribe.v2.evidence.errors import ValidationError
from redscribe.v2.evidence.models import (
    DispositionAction,
    RetentionBasis,
    RetentionDecision,
    RetentionPolicy,
)
from redscribe.v2.evidence.validation import (
    normalize_timestamp,
    now_iso,
    validate_evidence_id,
    validate_retain_days,
)

DEFAULT_RETAIN_DAYS = 365
MAX_RETAIN_DAYS = 36_500


def default_policy(
    evidence_id: str,
    *,
    basis: RetentionBasis = RetentionBasis.CASE,
    retain_days: int = DEFAULT_RETAIN_DAYS,
    reason: str = "",
    updated_at: str = "",
) -> RetentionPolicy:
    """Create a default retention policy for a newly acquired item."""
    return build_policy(
        evidence_id,
        basis=basis,
        retain_days=retain_days,
        reason=reason,
        updated_at=updated_at,
    )


def build_policy(
    evidence_id: str,
    *,
    basis: RetentionBasis = RetentionBasis.CASE,
    retain_days: int = DEFAULT_RETAIN_DAYS,
    retain_until: str = "",
    legal_hold: bool = False,
    review_at: str = "",
    disposition: DispositionAction = DispositionAction.KEEP,
    reason: str = "",
    updated_at: str = "",
) -> RetentionPolicy:
    """Build and validate a retention policy."""
    record_id = validate_evidence_id(evidence_id, field="evidence_id")
    days = validate_retain_days(retain_days)
    stamp = normalize_timestamp(updated_at, default=now_iso())
    expiry = normalize_timestamp(retain_until)
    if not expiry and days:
        expiry = shift_days(stamp, days)
    return RetentionPolicy(
        evidence_id=record_id,
        basis=basis,
        retain_days=days,
        retain_until=expiry,
        legal_hold=legal_hold,
        review_at=normalize_timestamp(review_at),
        disposition=disposition,
        updated_at=stamp,
        reason=reason.strip()[:1_000],
    )


def shift_days(timestamp: str, days: int) -> str:
    """Shift an ISO timestamp by whole days."""
    parsed = parse_timestamp(timestamp)
    if parsed is None:
        return ""
    return iso_z(parsed + timedelta(days=days))


def update_policy(
    policy: RetentionPolicy,
    *,
    basis: RetentionBasis | None = None,
    retain_days: int | None = None,
    retain_until: str | None = None,
    legal_hold: bool | None = None,
    review_at: str | None = None,
    disposition: DispositionAction | None = None,
    reason: str | None = None,
    updated_at: str = "",
) -> RetentionPolicy:
    """Return a policy with bounded updates applied."""
    payload = policy.as_dict()
    if basis is not None:
        payload["basis"] = basis.value
    if retain_days is not None:
        payload["retain_days"] = validate_retain_days(retain_days)
        payload["retain_until"] = shift_days(now_iso(), payload["retain_days"])
    if retain_until is not None:
        normalized = normalize_timestamp(retain_until)
        if not normalized:
            raise ValidationError(
                "Invalid retain_until timestamp", details={"field": "retain_until"}
            )
        payload["retain_until"] = normalized
    if legal_hold is not None:
        payload["legal_hold"] = bool(legal_hold)
        if legal_hold:
            payload["basis"] = RetentionBasis.LEGAL_HOLD.value
    if review_at is not None:
        payload["review_at"] = normalize_timestamp(review_at)
    if disposition is not None:
        payload["disposition"] = disposition.value
    if reason is not None:
        payload["reason"] = reason.strip()[:1_000]
    payload["updated_at"] = normalize_timestamp(updated_at, default=now_iso())
    return RetentionPolicy.from_dict(payload)


def set_legal_hold(
    policy: RetentionPolicy,
    *,
    held: bool,
    reason: str = "",
    updated_at: str = "",
) -> RetentionPolicy:
    """Apply or release a legal hold on a policy."""
    basis = RetentionBasis.LEGAL_HOLD if held else RetentionBasis.CASE
    return update_policy(
        policy,
        legal_hold=held,
        basis=basis,
        reason=reason or policy.reason,
        updated_at=updated_at,
    )


def extend_policy(policy: RetentionPolicy, *, days: int) -> RetentionPolicy:
    """Extend a policy expiry by a number of days."""
    duration = validate_retain_days(days, default=0)
    expiry = policy.retain_until or now_iso()
    return update_policy(
        policy,
        retain_until=shift_days(expiry, duration),
        retain_days=policy.retain_days + duration,
        reason=policy.reason or f"Extended by {duration} days",
    )


def days_remaining(policy: RetentionPolicy, *, now: str = "") -> int:
    """Return whole days until expiry; negative values are overdue."""
    if not policy.retain_until:
        return policy.retain_days
    reference = parse_timestamp(now) if now else datetime.now(timezone.utc)
    expiry = parse_timestamp(policy.retain_until)
    if reference is None or expiry is None:
        return policy.retain_days
    return int((expiry - reference).total_seconds() // 86_400)


def evaluate_policy(policy: RetentionPolicy, *, now: str = "") -> RetentionDecision:
    """Recommend a disposition action for one policy."""
    remaining = days_remaining(policy, now=now)
    if policy.legal_hold:
        return RetentionDecision(
            evidence_id=policy.evidence_id,
            action=DispositionAction.KEEP,
            reason="Legal hold prevents disposition",
            days_remaining=remaining,
            legal_hold=True,
        )
    if policy.basis is RetentionBasis.INDEFINITE:
        return RetentionDecision(
            evidence_id=policy.evidence_id,
            action=DispositionAction.KEEP,
            reason="Indefinite retention basis",
            days_remaining=remaining,
            legal_hold=False,
        )
    if remaining < 0:
        return RetentionDecision(
            evidence_id=policy.evidence_id,
            action=DispositionAction.DESTROY,
            reason="Retention period has expired",
            days_remaining=remaining,
            legal_hold=False,
        )
    if remaining <= 30:
        return RetentionDecision(
            evidence_id=policy.evidence_id,
            action=DispositionAction.REVIEW,
            reason="Retention period ends within 30 days",
            days_remaining=remaining,
            legal_hold=False,
        )
    if policy.disposition is DispositionAction.ARCHIVE:
        return RetentionDecision(
            evidence_id=policy.evidence_id,
            action=DispositionAction.ARCHIVE,
            reason="Policy requests archival",
            days_remaining=remaining,
            legal_hold=False,
        )
    return RetentionDecision(
        evidence_id=policy.evidence_id,
        action=DispositionAction.KEEP,
        reason="Retention period is active",
        days_remaining=remaining,
        legal_hold=False,
    )


class RetentionManager:
    """Stateful helper for evaluating retention across many items."""

    def __init__(self, policies: Iterable[RetentionPolicy] = ()) -> None:
        self._policies = {policy.evidence_id: policy for policy in policies}

    def set(self, policy: RetentionPolicy) -> RetentionPolicy:
        """Store one policy."""
        self._policies[policy.evidence_id] = policy
        return policy

    def get(self, evidence_id: str) -> RetentionPolicy | None:
        """Return the policy for one item, if present."""
        return self._policies.get(evidence_id)

    def all(self) -> tuple[RetentionPolicy, ...]:
        """Return all stored policies in stable order."""
        return tuple(self._policies[key] for key in sorted(self._policies))

    def replace(self, policies: Iterable[RetentionPolicy]) -> None:
        """Replace the complete policy set."""
        self._policies = {policy.evidence_id: policy for policy in policies}

    def evaluate(self, evidence_id: str, *, now: str = "") -> RetentionDecision | None:
        """Evaluate one item's retention policy."""
        policy = self.get(evidence_id)
        return evaluate_policy(policy, now=now) if policy is not None else None

    def plan(self, *, now: str = "") -> list[RetentionDecision]:
        """Return decisions for all stored policies."""
        return [evaluate_policy(policy, now=now) for policy in self.all()]

    def due_for_destroy(self, *, now: str = "") -> tuple[str, ...]:
        """Return ids whose policies recommend destruction."""
        return tuple(
            decision.evidence_id
            for decision in self.plan(now=now)
            if decision.action is DispositionAction.DESTROY
        )

    def holds(self) -> tuple[str, ...]:
        """Return ids currently under legal hold."""
        return tuple(policy.evidence_id for policy in self.all() if policy.legal_hold)


def retention_summary(
    policies: Sequence[RetentionPolicy],
    *,
    now: str = "",
) -> dict[str, Any]:
    """Aggregate retention counters for dashboards."""
    decisions = [evaluate_policy(policy, now=now) for policy in policies]
    return {
        "total": len(policies),
        "legal_holds": sum(1 for policy in policies if policy.legal_hold),
        "destroy": sum(1 for item in decisions if item.action is DispositionAction.DESTROY),
        "review": sum(1 for item in decisions if item.action is DispositionAction.REVIEW),
        "archive": sum(1 for item in decisions if item.action is DispositionAction.ARCHIVE),
        "keep": sum(1 for item in decisions if item.action is DispositionAction.KEEP),
        "earliest_expiry": min(
            (policy.retain_until for policy in policies if policy.retain_until),
            default="",
        ),
    }


def describe_policy(policy: RetentionPolicy, *, now: str = "") -> dict[str, Any]:
    """Return a detailed policy view including its current decision."""
    payload = policy.as_dict()
    payload["days_remaining"] = days_remaining(policy, now=now)
    payload["decision"] = evaluate_policy(policy, now=now).as_dict()
    return payload


def validate_policy(policy: RetentionPolicy) -> None:
    """Raise when a retention policy contains invalid values."""
    validate_evidence_id(policy.evidence_id, field="evidence_id")
    if policy.retain_days < 0 or policy.retain_days > MAX_RETAIN_DAYS:
        raise ValidationError("Invalid retain_days", details={"field": "retain_days"})
    if policy.retain_until and not parse_timestamp(policy.retain_until):
        raise ValidationError("Invalid retain_until", details={"field": "retain_until"})
    if policy.review_at and not parse_timestamp(policy.review_at):
        raise ValidationError("Invalid review_at", details={"field": "review_at"})


def policy_from_manifest(value: Mapping[str, Any]) -> RetentionPolicy:
    """Parse a retention policy from a manifest mapping."""
    return RetentionPolicy.from_dict(value)
