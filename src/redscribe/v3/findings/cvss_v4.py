"""CVSS v4.0 parsing, scoring, and qualitative severity bands.

The scoring algorithm follows the published FIRST CVSS v4.0 specification:
MacroVectors are looked up in a fixed table and vectors inside a MacroVector are
scored by interpolating toward the next lower MacroVector. The reference data
lives in :mod:`redscribe.v3.findings.cvss_v4_data`; no network access or third
party package is used at runtime.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from redscribe.v3.findings.cvss_v4_data import (
    MACRO_VECTOR_SCORES,
    MAX_EQ1,
    MAX_EQ1_VECTORS,
    MAX_EQ2,
    MAX_EQ2_VECTORS,
    MAX_EQ3_EQ6,
    MAX_EQ3_VECTORS,
    MAX_EQ4,
    MAX_EQ4_VECTORS,
    MAX_EQ5,
    MAX_EQ5_VECTORS,
)

CVSS_V4_PREFIX = "CVSS:4.0"
BASE_METRICS: tuple[str, ...] = (
    "AV",
    "AC",
    "AT",
    "PR",
    "UI",
    "VC",
    "VI",
    "VA",
    "SC",
    "SI",
    "SA",
)
THREAT_METRICS: tuple[str, ...] = ("E",)
ENVIRONMENTAL_METRICS: tuple[str, ...] = (
    "CR",
    "IR",
    "AR",
    "MAV",
    "MAC",
    "MAT",
    "MPR",
    "MUI",
    "MVC",
    "MVI",
    "MVA",
    "MSC",
    "MSI",
    "MSA",
)
SUPPLEMENTAL_METRICS: tuple[str, ...] = ("S", "AU", "R", "V", "RE", "U")
MODIFIED_METRICS: tuple[str, ...] = tuple(name for name in ENVIRONMENTAL_METRICS if name[0] == "M")
REQUIREMENT_METRICS: tuple[str, ...] = ("CR", "IR", "AR")
IMPACT_METRICS: tuple[str, ...] = ("VC", "VI", "VA", "SC", "SI", "SA")

METRIC_VALUES: dict[str, frozenset[str]] = {
    "AV": frozenset({"N", "A", "L", "P"}),
    "AC": frozenset({"L", "H"}),
    "AT": frozenset({"N", "P"}),
    "PR": frozenset({"N", "L", "H"}),
    "UI": frozenset({"N", "P", "A"}),
    "VC": frozenset({"H", "L", "N"}),
    "VI": frozenset({"H", "L", "N"}),
    "VA": frozenset({"H", "L", "N"}),
    "SC": frozenset({"H", "L", "N"}),
    "SI": frozenset({"H", "L", "N"}),
    "SA": frozenset({"H", "L", "N"}),
    "E": frozenset({"X", "A", "P", "U"}),
    "CR": frozenset({"X", "H", "M", "L"}),
    "IR": frozenset({"X", "H", "M", "L"}),
    "AR": frozenset({"X", "H", "M", "L"}),
    "S": frozenset({"X", "N", "P"}),
    "AU": frozenset({"X", "Y", "N"}),
    "R": frozenset({"X", "A", "U", "I"}),
    "V": frozenset({"X", "D", "C"}),
    "RE": frozenset({"X", "L", "M", "H"}),
    "U": frozenset({"X", "Clear", "Green", "Amber", "Red"}),
}
for _modified in ("MAV", "MAC", "MAT", "MPR", "MUI", "MVC", "MVI", "MVA"):
    METRIC_VALUES[_modified] = frozenset({"X", *METRIC_VALUES[_modified[1:]]})
METRIC_VALUES["MSC"] = frozenset({"X", "H", "L", "N"})
METRIC_VALUES["MSI"] = frozenset({"X", "H", "L", "N", "S"})
METRIC_VALUES["MSA"] = frozenset({"X", "H", "L", "N", "S"})

METRIC_LABELS: dict[str, str] = {
    "AV": "Attack Vector",
    "AC": "Attack Complexity",
    "AT": "Attack Requirements",
    "PR": "Privileges Required",
    "UI": "User Interaction",
    "VC": "Vulnerable System Confidentiality",
    "VI": "Vulnerable System Integrity",
    "VA": "Vulnerable System Availability",
    "SC": "Subsequent System Confidentiality",
    "SI": "Subsequent System Integrity",
    "SA": "Subsequent System Availability",
    "E": "Exploit Maturity",
    "CR": "Confidentiality Requirement",
    "IR": "Integrity Requirement",
    "AR": "Availability Requirement",
}

LEVELS: dict[str, dict[str, float]] = {
    "AV": {"N": 0.0, "A": 0.1, "L": 0.2, "P": 0.3},
    "PR": {"N": 0.0, "L": 0.1, "H": 0.2},
    "UI": {"N": 0.0, "P": 0.1, "A": 0.2},
    "AC": {"L": 0.0, "H": 0.1},
    "AT": {"N": 0.0, "P": 0.1},
    "VC": {"H": 0.0, "L": 0.1, "N": 0.2},
    "VI": {"H": 0.0, "L": 0.1, "N": 0.2},
    "VA": {"H": 0.0, "L": 0.1, "N": 0.2},
    "SC": {"H": 0.1, "L": 0.2, "N": 0.3},
    "SI": {"S": 0.0, "H": 0.1, "L": 0.2, "N": 0.3},
    "SA": {"S": 0.0, "H": 0.1, "L": 0.2, "N": 0.3},
    "CR": {"H": 0.0, "M": 0.1, "L": 0.2},
    "IR": {"H": 0.0, "M": 0.1, "L": 0.2},
    "AR": {"H": 0.0, "M": 0.1, "L": 0.2},
    "E": {"U": 0.2, "P": 0.1, "A": 0.0},
}

_VECTOR_PATTERN = re.compile(r"^CVSS:4\.0(?:/[A-Za-z]+:[A-Za-z0-9]+)+$")
_METRIC_PATTERN = re.compile(r"^([A-Za-z]+):([A-Za-z0-9]+)$")


class CvssV4Error(ValueError):
    """Raised when a CVSS v4 vector is malformed or cannot be scored."""


class SeverityBand(str, Enum):
    """Qualitative CVSS severity bands, including the v4 None band."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @classmethod
    def for_score(cls, score: float) -> SeverityBand:
        """Return the band for a score in the 0.0..10.0 range."""
        if score <= 0.0:
            return cls.NONE
        if score < 4.0:
            return cls.LOW
        if score < 7.0:
            return cls.MEDIUM
        if score < 9.0:
            return cls.HIGH
        return cls.CRITICAL

    @property
    def rank(self) -> int:
        """Return a numeric ordering for the band."""
        return {
            SeverityBand.NONE: 0,
            SeverityBand.LOW: 1,
            SeverityBand.MEDIUM: 2,
            SeverityBand.HIGH: 3,
            SeverityBand.CRITICAL: 4,
        }[self]

    @property
    def color_token(self) -> str:
        """Return the semantic CSS token used by the finding studio."""
        return {
            SeverityBand.NONE: "var(--v3-severity-none)",
            SeverityBand.LOW: "var(--v3-severity-low)",
            SeverityBand.MEDIUM: "var(--v3-severity-medium)",
            SeverityBand.HIGH: "var(--v3-severity-high)",
            SeverityBand.CRITICAL: "var(--v3-severity-critical)",
        }[self]


@dataclass(frozen=True, slots=True)
class CvssV4Vector:
    """An immutable, validated CVSS v4.0 vector."""

    version: str
    values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.version != "4.0":
            raise CvssV4Error(f"Unsupported CVSS version: {self.version}")
        names = [name for name, _ in self.values]
        if len(names) != len(set(names)):
            raise CvssV4Error("CVSS vector contains a duplicate metric")
        missing = [name for name in BASE_METRICS if name not in names]
        if missing:
            raise CvssV4Error("Missing CVSS v4 base metrics: " + ", ".join(missing))
        for name, value in self.values:
            allowed = METRIC_VALUES.get(name)
            if allowed is not None and value not in allowed:
                raise CvssV4Error(f"Invalid value '{value}' for metric {name}")

    @property
    def metrics(self) -> dict[str, str]:
        """Return the metrics as a dictionary in declaration order."""
        return dict(self.values)

    @property
    def base(self) -> dict[str, str]:
        """Return only base-group metrics."""
        return {name: value for name, value in self.values if name in BASE_METRICS}

    @property
    def threat(self) -> dict[str, str]:
        """Return threat-group metrics."""
        return {name: value for name, value in self.values if name in THREAT_METRICS}

    @property
    def environmental(self) -> dict[str, str]:
        """Return environmental-group metrics."""
        return {name: value for name, value in self.values if name in ENVIRONMENTAL_METRICS}

    @property
    def supplemental(self) -> dict[str, str]:
        """Return supplemental metrics, which never change the score."""
        return {name: value for name, value in self.values if name in SUPPLEMENTAL_METRICS}

    def metric(self, name: str, default: str = "") -> str:
        """Return a raw metric value."""
        return dict(self.values).get(name, default)

    def effective(self, name: str) -> str:
        """Return a metric value after applying CVSS default and override rules."""
        raw = dict(self.values)
        if name in ("E", "CR", "IR", "AR"):
            value = raw.get(name, "X")
            if value == "X":
                return "A" if name == "E" else "H"
            return value
        if name not in MODIFIED_METRICS and name in BASE_METRICS:
            override = raw.get("M" + name, "X")
            if override != "X":
                return override
        return raw.get(name, "X")

    def with_metric(self, name: str, value: str) -> CvssV4Vector:
        """Return a new vector with one metric added or replaced."""
        updated = dict(self.values)
        updated[name] = value
        return parse_cvss_v4_vector(
            f"{CVSS_V4_PREFIX}/" + "/".join(f"{key}:{item}" for key, item in updated.items())
        )

    def without(self, names: tuple[str, ...]) -> CvssV4Vector:
        """Return a new vector with the named metrics removed."""
        excluded = set(names)
        ordered = [(name, value) for name, value in self.values if name not in excluded]
        return CvssV4Vector(version=self.version, values=tuple(ordered))

    def render(self) -> str:
        """Render the canonical vector string."""
        return f"{CVSS_V4_PREFIX}/" + "/".join(f"{name}:{value}" for name, value in self.values)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {"version": self.version, "metrics": self.metrics, "vector": self.render()}


@dataclass(frozen=True, slots=True)
class CvssV4Score:
    """All four CVSS v4 score nomenclatures for one vector."""

    vector: str
    base: float
    threat: float
    environmental: float
    final: float
    macro_vector: str
    severity: SeverityBand
    has_threat: bool
    has_environmental: bool

    @property
    def nomenclature(self) -> str:
        """Return the score nomenclature (CVSS-B/BT/BE/BTE)."""
        if self.has_threat and self.has_environmental:
            return "CVSS-BTE"
        if self.has_threat:
            return "CVSS-BT"
        if self.has_environmental:
            return "CVSS-BE"
        return "CVSS-B"

    @property
    def effective_score(self) -> float:
        """Return the final score after threat and environmental adjustment."""
        return self.final

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "vector": self.vector,
            "base": self.base,
            "threat": self.threat,
            "environmental": self.environmental,
            "final": self.final,
            "nomenclature": self.nomenclature,
            "macro_vector": self.macro_vector,
            "severity": self.severity.value,
        }


def parse_cvss_v4_vector(value: str) -> CvssV4Vector:
    """Parse and validate a CVSS v4.0 vector string."""
    if not isinstance(value, str):
        raise CvssV4Error("CVSS vector must be a string")
    normalized = value.strip()
    if not _VECTOR_PATTERN.match(normalized):
        raise CvssV4Error("Invalid CVSS v4 vector syntax")
    parts = normalized.split("/")[1:]
    values: list[tuple[str, str]] = []
    for part in parts:
        match = _METRIC_PATTERN.match(part)
        if match is None:
            raise CvssV4Error(f"Invalid CVSS metric: {part}")
        name, metric_value = match.groups()
        if name not in METRIC_VALUES:
            raise CvssV4Error(f"Unknown CVSS v4 metric: {name}")
        values.append((name, metric_value))
    return CvssV4Vector(version="4.0", values=tuple(values))


def _extract_metric(spec: str, name: str) -> str:
    """Extract a metric value from a highest-severity vector specification."""
    for part in spec.split("/"):
        if part.startswith(name + ":"):
            return part.split(":", 1)[1]
    raise CvssV4Error(f"Highest-severity vector is missing {name}")


def _round_tenth(value: float) -> float:
    """Round half up to one decimal place, matching the reference calculator."""
    return math.floor(value * 10.0 + 0.5) / 10.0


def _effective_metric(metrics: dict[str, str], name: str) -> str:
    """Apply CVSS v4 defaults and modified overrides to a metric mapping."""
    value = metrics.get(name, "X")
    if name in ("E", "CR", "IR", "AR"):
        if value == "X":
            return "A" if name == "E" else "H"
        return value
    if name in BASE_METRICS:
        override = metrics.get("M" + name, "X")
        if override != "X":
            return override
    return value


def _macro_vector(metrics: dict[str, str]) -> str:
    """Determine the six-level MacroVector for a set of effective metrics."""
    av = _effective_metric(metrics, "AV")
    pr = _effective_metric(metrics, "PR")
    ui = _effective_metric(metrics, "UI")
    ac = _effective_metric(metrics, "AC")
    at = _effective_metric(metrics, "AT")
    vc = _effective_metric(metrics, "VC")
    vi = _effective_metric(metrics, "VI")
    va = _effective_metric(metrics, "VA")
    sc = _effective_metric(metrics, "SC")
    si = _effective_metric(metrics, "SI")
    sa = _effective_metric(metrics, "SA")
    msi = metrics.get("MSI", "X")
    msa = metrics.get("MSA", "X")
    e = _effective_metric(metrics, "E")
    cr = _effective_metric(metrics, "CR")
    ir = _effective_metric(metrics, "IR")
    ar = _effective_metric(metrics, "AR")

    if av == "N" and pr == "N" and ui == "N":
        eq1 = 0
    elif (av == "N" or pr == "N" or ui == "N") and av != "P":
        eq1 = 1
    else:
        eq1 = 2

    eq2 = 0 if ac == "L" and at == "N" else 1

    if vc == "H" and vi == "H":
        eq3 = 0
    elif vc == "H" or vi == "H" or va == "H":
        eq3 = 1
    else:
        eq3 = 2

    if msi == "S" or msa == "S":
        eq4 = 0
    elif sc == "H" or si == "H" or sa == "H":
        eq4 = 1
    else:
        eq4 = 2

    eq5 = {"A": 0, "P": 1, "U": 2}[e]

    eq6 = (
        0
        if (cr == "H" and vc == "H") or (ir == "H" and vi == "H") or (ar == "H" and va == "H")
        else 1
    )

    return f"{eq1}{eq2}{eq3}{eq4}{eq5}{eq6}"


def _lower_macro(macro: str, eq_index: int, step: int) -> str:
    """Return the MacroVector one step lower on one equivalence class."""
    chars = list(macro)
    chars[eq_index] = str(int(chars[eq_index]) + step)
    return "".join(chars)


def _lower_scores(macro: str) -> dict[int, float]:
    """Return the scores of the next lower MacroVectors that exist."""
    eq3, eq6 = int(macro[2]), int(macro[5])
    candidates: dict[int, list[str]] = {
        0: [_lower_macro(macro, 0, 1)],
        1: [_lower_macro(macro, 1, 1)],
        3: [],
        4: [_lower_macro(macro, 3, 1)],
        5: [_lower_macro(macro, 4, 1)],
    }
    if (eq3, eq6) == (1, 1) or (eq3, eq6) == (0, 1):
        candidates[3].append(_lower_macro(macro, 2, 1))
    elif (eq3, eq6) == (1, 0):
        candidates[3].append(_lower_macro(macro, 5, 1))
    elif (eq3, eq6) == (0, 0):
        candidates[3].extend([_lower_macro(macro, 2, 1), _lower_macro(macro, 5, 1)])
    else:
        candidates[3].append(_lower_macro(macro, 2, 1))

    scores: dict[int, float] = {}
    for index, keys in candidates.items():
        existing = [MACRO_VECTOR_SCORES[key] for key in keys if key in MACRO_VECTOR_SCORES]
        if existing:
            scores[index] = max(existing)
    return scores


def _max_vectors(macro: str) -> list[str]:
    """Compose the highest-severity vectors that define a MacroVector."""
    eq1, eq2, eq3, eq4, eq5, eq6 = (int(value) for value in macro)
    eq1_options = MAX_EQ1_VECTORS[eq1]
    eq2_options = MAX_EQ2_VECTORS[eq2]
    eq3_options = MAX_EQ3_VECTORS[eq3][eq6]
    eq4_options = MAX_EQ4_VECTORS[eq4]
    eq5_options = MAX_EQ5_VECTORS[eq5]
    return [
        first + second + third + fourth + fifth
        for first in eq1_options
        for second in eq2_options
        for third in eq3_options
        for fourth in eq4_options
        for fifth in eq5_options
    ]


def _severity_distance(metrics: dict[str, str], maximum: str) -> dict[int, float]:
    """Compute per-equivalence-class distances to a highest-severity vector."""
    distances: dict[int, float] = {}
    groups: dict[int, tuple[str, ...]] = {
        0: ("AV", "PR", "UI"),
        1: ("AC", "AT"),
        3: ("VC", "VI", "VA", "CR", "IR", "AR"),
        4: ("SC", "SI", "SA"),
    }
    for index, names in groups.items():
        total = 0.0
        for name in names:
            actual = LEVELS[name][_effective_metric(metrics, name)]
            target = LEVELS[name][_extract_metric(maximum, name)]
            total += actual - target
        distances[index] = total
    distances[5] = 0.0
    return distances


def _score(metrics: dict[str, str]) -> tuple[float, str]:
    """Score a complete metric mapping and return its score and MacroVector."""
    impact_metrics = ("VC", "VI", "VA", "SC", "SI", "SA")
    if all(_effective_metric(metrics, name) == "N" for name in impact_metrics):
        return 0.0, "no-impact"

    macro = _macro_vector(metrics)
    value = MACRO_VECTOR_SCORES.get(macro)
    if value is None:
        raise CvssV4Error(f"Undefined CVSS v4 MacroVector: {macro}")

    lower = _lower_scores(macro)
    selected_maximum: str | None = None
    distances: dict[int, float] = {}
    for maximum in _max_vectors(macro):
        candidate = _severity_distance(metrics, maximum)
        if all(distance >= 0.0 for distance in candidate.values()):
            selected_maximum = maximum
            distances = candidate
            break
    if selected_maximum is None:
        raise CvssV4Error("No highest-severity vector matches the supplied metrics")

    eq3, eq6 = int(macro[2]), int(macro[5])
    maximums: dict[int, float] = {
        0: MAX_EQ1[int(macro[0])] * 0.1,
        1: MAX_EQ2[int(macro[1])] * 0.1,
        3: MAX_EQ3_EQ6[eq3][eq6] * 0.1,
        4: MAX_EQ4[int(macro[3])] * 0.1,
        5: MAX_EQ5[int(macro[4])] * 0.1,
    }
    normalized: list[float] = []
    for index in (0, 1, 3, 4, 5):
        if index not in lower:
            continue
        depth = maximums[index]
        if depth <= 0.0:
            continue
        normalized.append((value - lower[index]) * (distances[index] / depth))

    mean = sum(normalized) / len(normalized) if normalized else 0.0
    return max(0.0, min(10.0, _round_tenth(value - mean))), macro


def score_vector(vector: CvssV4Vector) -> CvssV4Score:
    """Compute base, threat, environmental, and final scores for a vector."""
    metrics = vector.metrics
    base_metrics = {
        name: value
        for name, value in metrics.items()
        if name in BASE_METRICS or name in MODIFIED_METRICS
    }
    threat_metrics = {name: value for name, value in metrics.items() if name in THREAT_METRICS}
    environmental_metrics = {
        name: value
        for name, value in metrics.items()
        if name in REQUIREMENT_METRICS or name in MODIFIED_METRICS
    }
    base_score, _ = _score(base_metrics)
    threat_score, _ = _score({**base_metrics, **threat_metrics})
    environmental_score, _ = _score({**base_metrics, **environmental_metrics})
    final_score, final_macro = _score(metrics)
    return CvssV4Score(
        vector=vector.render(),
        base=base_score,
        threat=threat_score,
        environmental=environmental_score,
        final=final_score,
        macro_vector=final_macro,
        severity=SeverityBand.for_score(final_score),
        has_threat=bool(threat_metrics and threat_metrics.get("E", "X") != "X"),
        has_environmental=bool(environmental_metrics),
    )


def cvss_v4_score(value: str | CvssV4Vector) -> float:
    """Parse a vector and return its final CVSS v4 score."""
    vector = parse_cvss_v4_vector(value) if isinstance(value, str) else value
    return score_vector(vector).final


def cvss_v4_severity(value: str | float | CvssV4Vector) -> SeverityBand:
    """Return the severity band for a vector or numeric score."""
    if isinstance(value, (int, float)):
        return SeverityBand.for_score(float(value))
    return score_vector(parse_cvss_v4_vector(value) if isinstance(value, str) else value).severity


def cvss_v4_breakdown(value: str | CvssV4Vector) -> dict[str, Any]:
    """Return a UI-friendly breakdown of a CVSS v4 vector."""
    vector = parse_cvss_v4_vector(value) if isinstance(value, str) else value
    result = score_vector(vector)
    metric_details = {
        name: {
            "code": code,
            "label": METRIC_LABELS.get(name, name),
            "effective": vector.effective(name),
        }
        for name, code in vector.metrics.items()
    }
    return {
        **result.as_dict(),
        "metrics": metric_details,
        "missing_base": [name for name in BASE_METRICS if name not in vector.metrics],
        "supplemental": vector.supplemental,
    }
