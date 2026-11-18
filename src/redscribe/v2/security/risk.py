"""Risk scoring helpers for privacy and security findings."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

SEVERITY_WEIGHTS = {
    "none": 0.0,
    "info": 1.0,
    "low": 3.0,
    "medium": 6.0,
    "high": 8.5,
    "critical": 10.0,
}
RISK_LEVELS = (
    (0.0, "none"),
    (2.5, "low"),
    (5.0, "medium"),
    (7.5, "high"),
    (9.0, "critical"),
)


@dataclass(frozen=True, slots=True)
class RiskFactor:
    """An individual input contributing to an overall risk assessment."""

    name: str
    score: float
    weight: float = 1.0
    severity: str = "medium"
    details: Mapping[str, Any] = field(default_factory=dict)

    def weighted_score(self) -> float:
        return max(0.0, min(10.0, self.score)) * max(0.0, self.weight)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": round(max(0.0, min(10.0, self.score)), 3),
            "weight": round(max(0.0, self.weight), 3),
            "weighted_score": round(self.weighted_score(), 3),
            "severity": self.severity,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class RiskScore:
    """Aggregate score and level."""

    score: float
    level: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "level": self.level,
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """Overall risk assessment for a payload, export, or audit state."""

    factors: tuple[RiskFactor, ...]
    score: RiskScore
    recommendations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score.as_dict(),
            "factors": [factor.as_dict() for factor in self.factors],
            "recommendations": list(self.recommendations),
        }


def level_for_score(score: float) -> str:
    level = "none"
    for threshold, name in RISK_LEVELS:
        if score >= threshold:
            level = name
    return level


def score_factors(factors: Sequence[RiskFactor]) -> RiskScore:
    if not factors:
        return RiskScore(score=0.0, level="none", confidence=0.2)
    total_weight = sum(max(0.0, factor.weight) for factor in factors)
    if total_weight <= 0:
        return RiskScore(score=0.0, level="none", confidence=0.2)
    weighted = sum(factor.weighted_score() for factor in factors) / total_weight
    weighted = max(0.0, min(10.0, weighted))
    diversity = min(1.0, len(factors) / 6.0)
    confidence = max(0.3, min(0.99, 0.45 + diversity * 0.45))
    return RiskScore(score=weighted, level=level_for_score(weighted), confidence=confidence)


def factor_from_severity(
    name: str, severity: str, *, count: int = 1, weight: float = 1.0
) -> RiskFactor:
    base = SEVERITY_WEIGHTS.get(severity.lower(), 3.0)
    bonus = min(2.0, max(0, count - 1) * 0.4)
    score = min(10.0, base + bonus)
    return RiskFactor(
        name=name,
        score=score,
        weight=weight,
        severity=severity.lower(),
        details={"count": count},
    )


def assess_risk(
    *,
    secret_result: Mapping[str, Any] | None = None,
    audit_result: Mapping[str, Any] | None = None,
    privacy: Mapping[str, Any] | None = None,
    safety_findings: Sequence[Mapping[str, Any]] | None = None,
    consent: Mapping[str, Any] | None = None,
    factors: Sequence[RiskFactor] | None = None,
) -> RiskAssessment:
    collected: list[RiskFactor] = list(factors or [])

    if secret_result:
        count = int(secret_result.get("count", 0) or 0)
        if count:
            severity = str(secret_result.get("highest_severity", "high"))
            collected.append(
                factor_from_severity("secret_exposure", severity, count=count, weight=1.4)
            )
        else:
            collected.append(
                RiskFactor(name="secret_exposure", score=0.5, weight=0.6, severity="info")
            )

    if audit_result:
        severity = str(audit_result.get("highest_severity", "none"))
        findings = audit_result.get("findings") or []
        count = len(findings) if isinstance(findings, list) else 0
        if count:
            collected.append(
                factor_from_severity("audit_findings", severity, count=count, weight=1.1)
            )

    if privacy:
        level = str(privacy.get("level", "standard"))
        rank = int(privacy.get("rank", 1) or 1)
        if level in {"open"}:
            collected.append(
                RiskFactor(name="privacy_posture", score=6.0, weight=0.8, severity="medium")
            )
        elif rank >= 2:
            collected.append(
                RiskFactor(name="privacy_posture", score=2.0, weight=0.7, severity="low")
            )
        else:
            collected.append(
                RiskFactor(name="privacy_posture", score=4.0, weight=0.7, severity="medium")
            )
        if privacy.get("require_export_consent") and not (consent or {}).get(
            "export_sensitive", False
        ):
            collected.append(
                RiskFactor(
                    name="export_consent_gap",
                    score=5.5,
                    weight=0.9,
                    severity="medium",
                    details={"required": True},
                )
            )

    if safety_findings:
        worst = "none"
        severity_rank = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        for item in safety_findings:
            severity = str(item.get("risk", "low"))
            if severity_rank.get(severity, 0) > severity_rank.get(worst, 0):
                worst = severity
        if safety_findings:
            collected.append(
                factor_from_severity(
                    "unsafe_actions", worst, count=len(safety_findings), weight=1.0
                )
            )

    if consent:
        sensitive_denied = [
            key for key, value in consent.items() if key.startswith("consent_") and value is False
        ]
        if sensitive_denied:
            collected.append(
                RiskFactor(
                    name="consent_restrictions",
                    score=3.0,
                    weight=0.4,
                    severity="low",
                    details={"denied": sensitive_denied[:10]},
                )
            )

    score = score_factors(collected)
    recommendations = tuple(_recommendations(collected, score))
    return RiskAssessment(factors=tuple(collected), score=score, recommendations=recommendations)


def _recommendations(factors: Iterable[RiskFactor], score: RiskScore) -> list[str]:
    recs: list[str] = []
    names = {factor.name for factor in factors}
    if "secret_exposure" in names:
        recs.append("Redact or rotate exposed secrets before sharing exports.")
    if "audit_findings" in names:
        recs.append("Review audit findings and investigate repeated denied or failed actions.")
    if "unsafe_actions" in names:
        recs.append("Avoid opening unsafe URLs or copying risky commands without review.")
    if "export_consent_gap" in names:
        recs.append("Require explicit consent before exporting sensitive content.")
    if score.level in {"high", "critical"}:
        recs.append("Enable strict privacy mode until risk is reduced.")
    if not recs:
        recs.append("No immediate remediation required; continue monitoring.")
    return recs
