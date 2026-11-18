"""CVSS v3.0/v3.1 base-score calculation and vector helpers."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from redscribe.v2.engagements.models import Severity
from redscribe.v2.engagements.validation import severity_for_score

_VECTOR_PATTERN = re.compile(
    r"^CVSS:(?P<version>3\.[01])(?P<metrics>(?:/[A-Za-z]+:[A-Za-z0-9]+)+)$"
)

AV_WEIGHTS = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.20}
AC_WEIGHTS = {"L": 0.77, "H": 0.44}
PR_U_WEIGHTS = {"N": 0.85, "L": 0.62, "H": 0.27}
PR_C_WEIGHTS = {"N": 0.85, "L": 0.68, "H": 0.50}
UI_WEIGHTS = {"N": 0.85, "R": 0.62}
CIA_WEIGHTS = {"H": 0.56, "L": 0.22, "N": 0.00}

BASE_METRICS = ("AV", "AC", "PR", "UI", "S", "C", "I", "A")

METRIC_LABELS: dict[str, str] = {
    "AV": "Attack Vector",
    "AC": "Attack Complexity",
    "PR": "Privileges Required",
    "UI": "User Interaction",
    "S": "Scope",
    "C": "Confidentiality",
    "I": "Integrity",
    "A": "Availability",
}


class CvssError(ValueError):
    """Raised when a CVSS vector cannot be parsed or scored."""


@dataclass(frozen=True, slots=True)
class CvssVector:
    """Parsed representation of a CVSS v3 base vector."""

    version: str
    metrics: dict[str, str] = field(default_factory=dict)
    extras: dict[str, str] = field(default_factory=dict)

    def metric(self, name: str) -> str:
        return self.metrics.get(name, "")

    def as_dict(self) -> dict[str, str]:
        return {**self.metrics, **self.extras}

    def render(self) -> str:
        parts = [f"CVSS:{self.version}"]
        parts.extend(
            f"{name}:{self.metrics[name]}" for name in BASE_METRICS if name in self.metrics
        )
        parts.extend(f"{name}:{value}" for name, value in sorted(self.extras.items()))
        return "/".join(parts)


def parse_cvss_vector(value: str) -> CvssVector:
    """Parse a CVSS v3.x vector into base metrics and extras."""
    if not isinstance(value, str):
        raise CvssError("CVSS vector must be a string")
    match = _VECTOR_PATTERN.match(value.strip())
    if match is None:
        raise CvssError("Invalid CVSS vector syntax")
    metrics: dict[str, str] = {}
    extras: dict[str, str] = {}
    for part in match.group("metrics").split("/"):
        if not part:
            continue
        if ":" not in part:
            raise CvssError(f"Invalid CVSS metric: {part}")
        name, metric_value = part.split(":", 1)
        if not name.isupper() or not metric_value:
            raise CvssError(f"Invalid CVSS metric: {part}")
        if name in BASE_METRICS:
            metrics[name] = metric_value
        else:
            extras[name] = metric_value
    missing = [name for name in BASE_METRICS if name not in metrics]
    if missing:
        raise CvssError(f"Missing CVSS base metrics: {', '.join(missing)}")
    return CvssVector(version=match.group("version"), metrics=metrics, extras=extras)


def _roundup(value: float) -> float:
    return math.ceil(value * 100000.0) / 100000.0


def _weighted(table: Mapping[str, float], key: str, name: str) -> float:
    if key not in table:
        raise CvssError(f"Invalid value '{key}' for {name}")
    return table[key]


def score_vector(vector: CvssVector) -> float:
    """Compute the CVSS v3 base score for a parsed vector."""
    scope_changed = vector.metric("S") == "C"
    if vector.metric("S") not in {"U", "C"}:
        raise CvssError("Invalid value for S")

    av = _weighted(AV_WEIGHTS, vector.metric("AV"), "AV")
    ac = _weighted(AC_WEIGHTS, vector.metric("AC"), "AC")
    pr_table = PR_C_WEIGHTS if scope_changed else PR_U_WEIGHTS
    pr = _weighted(pr_table, vector.metric("PR"), "PR")
    ui = _weighted(UI_WEIGHTS, vector.metric("UI"), "UI")
    confidentiality = _weighted(CIA_WEIGHTS, vector.metric("C"), "C")
    integrity = _weighted(CIA_WEIGHTS, vector.metric("I"), "I")
    availability = _weighted(CIA_WEIGHTS, vector.metric("A"), "A")

    iss = 1.0 - (1.0 - confidentiality) * (1.0 - integrity) * (1.0 - availability)
    if iss <= 0.0:
        return 0.0
    impact = 7.52 * (iss - 0.029) - 3.25 * ((iss - 0.02) ** 15) if scope_changed else 6.42 * iss
    exploitability = 8.22 * av * ac * pr * ui
    if impact <= 0.0:
        return 0.0
    if scope_changed:
        return _roundup(min(1.08 * (impact + exploitability), 10.0))
    return _roundup(min(impact + exploitability, 10.0))


def cvss_base_score(value: str) -> float:
    """Parse a CVSS vector and return its base score."""
    return score_vector(parse_cvss_vector(value))


def cvss_severity(value: str | float) -> Severity:
    """Return the qualitative severity for a CVSS vector or numeric score."""
    if isinstance(value, str):
        return severity_for_score(cvss_base_score(value))
    return severity_for_score(float(value))


def cvss_breakdown(value: str) -> dict[str, object]:
    """Return a UI-friendly breakdown of a CVSS vector."""
    vector = parse_cvss_vector(value)
    score = score_vector(vector)
    return {
        "version": vector.version,
        "vector": vector.render(),
        "score": score,
        "severity": severity_for_score(score).value,
        "metrics": {
            name: {"code": vector.metric(name), "label": METRIC_LABELS[name]}
            for name in BASE_METRICS
        },
        "extras": dict(vector.extras),
    }


def severity_agreement(declared: Severity, vector: str) -> bool:
    """Return whether a declared severity agrees with the CVSS band."""
    if not vector:
        return True
    return declared is cvss_severity(vector)


def compare_severities(left: Severity, right: Severity) -> int:
    """Return a negative, zero, or positive ordering for two severities."""
    order = [
        Severity.INFO,
        Severity.LOW,
        Severity.MEDIUM,
        Severity.HIGH,
        Severity.CRITICAL,
    ]
    return order.index(left) - order.index(right)


def representative_score(severity: Severity) -> float:
    """Return the representative score used when no vector is present."""
    return severity.numeric_score()
