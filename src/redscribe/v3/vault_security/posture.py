"""Security posture scoring that reports gaps without revealing secrets."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from redscribe.v3.vault_security.crypto import RECOMMENDED_ITERATIONS
from redscribe.v3.vault_security.policy import PolicyEngine, PolicyError

MAX_KEY_AGE_SECONDS = 90 * 24 * 60 * 60
MAX_RECOVERY_AGE_SECONDS = 180 * 24 * 60 * 60


class PostureLevel(str, Enum):
    """Human-readable band for a posture score."""

    STRONG = "strong"
    FAIR = "fair"
    WEAK = "weak"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class PostureCheck:
    """One pass/fail posture check with static, secret-free guidance."""

    check_id: str
    label: str
    passed: bool
    severity: str
    detail: str
    remediation: str
    weight: int

    def __post_init__(self) -> None:
        if self.severity not in ("critical", "high", "medium", "low"):
            raise ValueError("Invalid check severity")
        if not self.check_id or not self.label:
            raise ValueError("Check id and label are required")

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "id": self.check_id,
            "label": self.label,
            "passed": self.passed,
            "severity": self.severity,
            "detail": self.detail,
            "remediation": self.remediation,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class PostureReport:
    """Aggregate posture result with explicit no-secret guarantees."""

    score: int
    level: PostureLevel
    checks: tuple[PostureCheck, ...]
    generated_at: float
    warnings: tuple[str, ...] = ()
    contains_secrets: bool = False

    @property
    def passed(self) -> int:
        """Number of passing checks."""
        return sum(1 for check in self.checks if check.passed)

    @property
    def total(self) -> int:
        """Number of evaluated checks."""
        return len(self.checks)

    @property
    def gaps(self) -> tuple[PostureCheck, ...]:
        """Return failing checks only."""
        return tuple(check for check in self.checks if not check.passed)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation containing no secret values."""
        return {
            "score": self.score,
            "level": self.level.value,
            "passed": self.passed,
            "total": self.total,
            "checks": [check.as_dict() for check in self.checks],
            "gap_ids": [check.check_id for check in self.gaps],
            "generated_at": self.generated_at,
            "warnings": list(self.warnings),
            "contains_secrets": self.contains_secrets,
        }


def level_for_score(score: int) -> PostureLevel:
    """Map a 0-100 score onto a posture band."""
    if not 0 <= score <= 100:
        raise ValueError("score must be between 0 and 100")
    if score >= 85:
        return PostureLevel.STRONG
    if score >= 70:
        return PostureLevel.FAIR
    if score >= 50:
        return PostureLevel.WEAK
    return PostureLevel.CRITICAL


def _weight(severity: str) -> int:
    return {"critical": 20, "high": 15, "medium": 10, "low": 5}[severity]


def _check(
    check_id: str,
    label: str,
    passed: bool,
    severity: str,
    detail: str,
    remediation: str,
) -> PostureCheck:
    return PostureCheck(
        check_id=check_id,
        label=label,
        passed=passed,
        severity=severity,
        detail=detail,
        remediation=remediation,
        weight=_weight(severity),
    )


def _active_key(snapshot: Mapping[str, Any]) -> Mapping[str, Any]:
    keys = snapshot.get("keys", ())
    for key in keys:
        if isinstance(key, Mapping) and key.get("status") == "active":
            return key
    return {}


def score_posture(
    snapshots: Mapping[str, Mapping[str, Any]],
    *,
    now: float,
    warnings: tuple[str, ...] = (),
) -> PostureReport:
    """Build a posture report from secret-free service snapshots."""
    vault = snapshots.get("vault", {})
    keyring = snapshots.get("keyring", {})
    recovery = snapshots.get("recovery", {})
    policy = snapshots.get("policy", {})
    audit = snapshots.get("audit", {})

    active = _active_key(keyring)
    iterations = int(active.get("iterations", 0))
    key_age = now - float(active.get("created_at", now))
    active_codes = int(recovery.get("active", 0))
    age_of_codes = [
        now - float(code.get("created_at", now))
        for code in recovery.get("codes", ())
        if isinstance(code, Mapping) and code.get("state") == "active"
    ]
    newest_code_age = min(age_of_codes) if age_of_codes else float("inf")
    consents = policy.get("consents", {})
    plaintext_granted = "export_plaintext" in consents.get("granted", ())
    patterns = policy.get("patterns", ())
    rules = policy.get("rules", ())
    audit_stats = audit.get("stats", {})

    checks = (
        _check(
            "vault_encrypted",
            "Vault encryption initialized",
            bool(vault.get("initialized") and keyring.get("initialized")),
            "critical",
            "Encryption keys must exist before the vault is used.",
            "Run the security setup wizard to initialize encryption.",
        ),
        _check(
            "locked_by_default",
            "Vault locked when idle",
            vault.get("state") in ("locked", "uninitialized"),
            "high",
            "An unlocked vault keeps key material in memory.",
            "Lock the vault after use.",
        ),
        _check(
            "kdf_strength",
            "Key derivation strength",
            iterations >= RECOMMENDED_ITERATIONS,
            "critical",
            "Active key meets the configured iteration floor (value hidden).",
            "Rotate the key with a higher iteration count.",
        ),
        _check(
            "key_rotation",
            "Recent key rotation",
            0 <= key_age <= MAX_KEY_AGE_SECONDS,
            "medium",
            f"Active key age must stay below {MAX_KEY_AGE_SECONDS // 86400} days.",
            "Rotate the vault key.",
        ),
        _check(
            "recovery_available",
            "Recovery codes available",
            active_codes > 0,
            "high",
            "At least one unused recovery code must be stored.",
            "Issue a fresh recovery batch.",
        ),
        _check(
            "recovery_fresh",
            "Recovery codes recent",
            newest_code_age <= MAX_RECOVERY_AGE_SECONDS,
            "low",
            f"Unused codes should be refreshed every {MAX_RECOVERY_AGE_SECONDS // 86400} days.",
            "Issue and safely store new recovery codes.",
        ),
        _check(
            "secret_patterns",
            "Secret detection enabled",
            len(patterns) >= 5,
            "high",
            "Built-in secret detectors must remain enabled.",
            "Restore the default secret patterns.",
        ),
        _check(
            "redaction_rules",
            "Redaction policy active",
            len(rules) >= 1,
            "high",
            "At least one mandatory redaction rule is required.",
            "Add a redaction rule in the policy editor.",
        ),
        _check(
            "consent_guards",
            "Plaintext export consent withheld",
            not plaintext_granted,
            "medium",
            "Plaintext export consent increases disclosure risk.",
            "Revoke plaintext export consent.",
        ),
        _check(
            "audit_present",
            "Audit trail populated",
            int(audit_stats.get("total", 0)) > 0,
            "low",
            "Security actions should be recorded for review.",
            "Perform and audit a vault action.",
        ),
    )
    earned = sum(check.weight for check in checks if check.passed)
    possible = sum(check.weight for check in checks) or 1
    score = round(100 * earned / possible)
    return PostureReport(
        score=score,
        level=level_for_score(score),
        checks=checks,
        generated_at=now,
        warnings=warnings,
    )


def report_to_json(report: PostureReport) -> str:
    """Serialize a posture report for API responses and tests."""
    return json.dumps(report.as_dict(), sort_keys=True, separators=(",", ":"))


def assert_secret_free(report: PostureReport, engine: PolicyEngine) -> None:
    """Verify that a serialized posture report matches no secret pattern."""
    try:
        engine.assert_clean(report_to_json(report))
    except PolicyError as error:
        raise PolicyError("Posture report failed the secret-free assertion") from error
