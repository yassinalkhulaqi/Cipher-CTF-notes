"""First-class finding types with CVSS v4 vectors and a governed lifecycle.

This module is a data-only contract layer: it defines the metric vocabulary,
the vector wire format, severity bands, lifecycle states with a legal transition
table, and the finding/retest records. It never executes user-supplied code and
has no dependency on I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

from redscribe.v4.contracts import new_entity_id
from redscribe.v4.events import utc_now

CVSS_VERSION = "4.0"
VECTOR_PREFIX = f"CVSS:{CVSS_VERSION}"
METRIC_ORDER: tuple[str, ...] = (
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
    "E",
    "CR",
    "IR",
    "AR",
)
BASE_METRIC_CODES: frozenset[str] = frozenset(METRIC_ORDER[:11])
THREAT_METRIC_CODES: frozenset[str] = frozenset(("E",))
ENVIRONMENTAL_METRIC_CODES: frozenset[str] = frozenset(("CR", "IR", "AR"))
OPTIONAL_METRIC_CODES: frozenset[str] = THREAT_METRIC_CODES | ENVIRONMENTAL_METRIC_CODES
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AttackVector(str, Enum):
    NETWORK = "N"
    ADJACENT = "A"
    LOCAL = "L"
    PHYSICAL = "P"

    @property
    def label(self) -> str:
        return _ATTACK_VECTOR_LABELS[self]

    @property
    def weight(self) -> float:
        return _ATTACK_VECTOR_WEIGHTS[self]


class AttackComplexity(str, Enum):
    LOW = "L"
    HIGH = "H"

    @property
    def label(self) -> str:
        return _ATTACK_COMPLEXITY_LABELS[self]

    @property
    def weight(self) -> float:
        return _ATTACK_COMPLEXITY_WEIGHTS[self]


class AttackRequirements(str, Enum):
    NONE = "N"
    PRESENT = "P"

    @property
    def label(self) -> str:
        return _ATTACK_REQUIREMENTS_LABELS[self]

    @property
    def weight(self) -> float:
        return _ATTACK_REQUIREMENTS_WEIGHTS[self]


class PrivilegesRequired(str, Enum):
    NONE = "N"
    LOW = "L"
    HIGH = "H"

    @property
    def label(self) -> str:
        return _PRIVILEGES_REQUIRED_LABELS[self]

    @property
    def weight(self) -> float:
        return _PRIVILEGES_REQUIRED_WEIGHTS[self]


class UserInteraction(str, Enum):
    NONE = "N"
    PASSIVE = "P"

    @property
    def label(self) -> str:
        return _USER_INTERACTION_LABELS[self]

    @property
    def weight(self) -> float:
        return _USER_INTERACTION_WEIGHTS[self]


class VulnConfidentiality(str, Enum):
    HIGH = "H"
    LOW = "L"
    NONE = "N"

    @property
    def label(self) -> str:
        return _IMPACT_LABELS[self]

    @property
    def weight(self) -> float:
        return _IMPACT_WEIGHTS[self]


class VulnIntegrity(str, Enum):
    HIGH = "H"
    LOW = "L"
    NONE = "N"

    @property
    def label(self) -> str:
        return _IMPACT_LABELS[self]

    @property
    def weight(self) -> float:
        return _IMPACT_WEIGHTS[self]


class VulnAvailability(str, Enum):
    HIGH = "H"
    LOW = "L"
    NONE = "N"

    @property
    def label(self) -> str:
        return _IMPACT_LABELS[self]

    @property
    def weight(self) -> float:
        return _IMPACT_WEIGHTS[self]


class SubsequentConfidentiality(str, Enum):
    HIGH = "H"
    LOW = "L"
    NONE = "N"

    @property
    def label(self) -> str:
        return _IMPACT_LABELS[self]

    @property
    def weight(self) -> float:
        return _IMPACT_WEIGHTS[self]


class SubsequentIntegrity(str, Enum):
    HIGH = "H"
    LOW = "L"
    NONE = "N"

    @property
    def label(self) -> str:
        return _IMPACT_LABELS[self]

    @property
    def weight(self) -> float:
        return _IMPACT_WEIGHTS[self]


class SubsequentAvailability(str, Enum):
    HIGH = "H"
    LOW = "L"
    NONE = "N"

    @property
    def label(self) -> str:
        return _IMPACT_LABELS[self]

    @property
    def weight(self) -> float:
        return _IMPACT_WEIGHTS[self]


class ExploitMaturity(str, Enum):
    NOT_DEFINED = "X"
    ATTACKED = "A"
    PROOF_OF_CONCEPT = "P"
    UNREPORTED = "U"

    @property
    def label(self) -> str:
        return _EXPLOIT_MATURITY_LABELS[self]

    @property
    def weight(self) -> float:
        return _EXPLOIT_MATURITY_WEIGHTS[self]


class ConfidentialityRequirement(str, Enum):
    NOT_DEFINED = "X"
    HIGH = "H"
    MEDIUM = "M"
    LOW = "L"

    @property
    def label(self) -> str:
        return _REQUIREMENT_LABELS[self]

    @property
    def weight(self) -> float:
        return _REQUIREMENT_WEIGHTS[self]


class IntegrityRequirement(str, Enum):
    NOT_DEFINED = "X"
    HIGH = "H"
    MEDIUM = "M"
    LOW = "L"

    @property
    def label(self) -> str:
        return _REQUIREMENT_LABELS[self]

    @property
    def weight(self) -> float:
        return _REQUIREMENT_WEIGHTS[self]


class AvailabilityRequirement(str, Enum):
    NOT_DEFINED = "X"
    HIGH = "H"
    MEDIUM = "M"
    LOW = "L"

    @property
    def label(self) -> str:
        return _REQUIREMENT_LABELS[self]

    @property
    def weight(self) -> float:
        return _REQUIREMENT_WEIGHTS[self]


_ATTACK_VECTOR_LABELS = {
    AttackVector.NETWORK: "Network",
    AttackVector.ADJACENT: "Adjacent",
    AttackVector.LOCAL: "Local",
    AttackVector.PHYSICAL: "Physical",
}
_ATTACK_VECTOR_WEIGHTS = {
    AttackVector.NETWORK: 0.85,
    AttackVector.ADJACENT: 0.62,
    AttackVector.LOCAL: 0.55,
    AttackVector.PHYSICAL: 0.20,
}
_ATTACK_COMPLEXITY_LABELS = {
    AttackComplexity.LOW: "Low",
    AttackComplexity.HIGH: "High",
}
_ATTACK_COMPLEXITY_WEIGHTS = {AttackComplexity.LOW: 0.77, AttackComplexity.HIGH: 0.44}
_ATTACK_REQUIREMENTS_LABELS = {
    AttackRequirements.NONE: "None",
    AttackRequirements.PRESENT: "Present",
}
_ATTACK_REQUIREMENTS_WEIGHTS = {AttackRequirements.NONE: 1.0, AttackRequirements.PRESENT: 0.90}
_PRIVILEGES_REQUIRED_LABELS = {
    PrivilegesRequired.NONE: "None",
    PrivilegesRequired.LOW: "Low",
    PrivilegesRequired.HIGH: "High",
}
_PRIVILEGES_REQUIRED_WEIGHTS = {
    PrivilegesRequired.NONE: 0.85,
    PrivilegesRequired.LOW: 0.62,
    PrivilegesRequired.HIGH: 0.27,
}
_USER_INTERACTION_LABELS = {
    UserInteraction.NONE: "None",
    UserInteraction.PASSIVE: "Passive",
}
_USER_INTERACTION_WEIGHTS = {UserInteraction.NONE: 0.85, UserInteraction.PASSIVE: 0.62}
_IMPACT_LABELS = {"H": "High", "L": "Low", "N": "None"}
_IMPACT_WEIGHTS = {"H": 0.56, "L": 0.22, "N": 0.0}
_EXPLOIT_MATURITY_LABELS = {
    ExploitMaturity.NOT_DEFINED: "Not defined",
    ExploitMaturity.ATTACKED: "Attacked",
    ExploitMaturity.PROOF_OF_CONCEPT: "Proof of concept",
    ExploitMaturity.UNREPORTED: "Unreported",
}
_EXPLOIT_MATURITY_WEIGHTS = {
    ExploitMaturity.NOT_DEFINED: 1.0,
    ExploitMaturity.ATTACKED: 1.0,
    ExploitMaturity.PROOF_OF_CONCEPT: 0.97,
    ExploitMaturity.UNREPORTED: 0.60,
}
_REQUIREMENT_LABELS = {
    "X": "Not defined",
    "H": "High",
    "M": "Medium",
    "L": "Low",
}
_REQUIREMENT_WEIGHTS = {"X": 1.0, "H": 1.5, "M": 1.0, "L": 0.5}

METRIC_ENUMS: dict[str, type[Enum]] = {
    "AV": AttackVector,
    "AC": AttackComplexity,
    "AT": AttackRequirements,
    "PR": PrivilegesRequired,
    "UI": UserInteraction,
    "VC": VulnConfidentiality,
    "VI": VulnIntegrity,
    "VA": VulnAvailability,
    "SC": SubsequentConfidentiality,
    "SI": SubsequentIntegrity,
    "SA": SubsequentAvailability,
    "E": ExploitMaturity,
    "CR": ConfidentialityRequirement,
    "IR": IntegrityRequirement,
    "AR": AvailabilityRequirement,
}

DEFAULT_VECTOR_TEXT = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:N/SI:N/SA:N"


@dataclass(frozen=True, slots=True)
class CvssV4Vector:
    """An immutable, validated CVSS v4 metric vector."""

    av: AttackVector
    ac: AttackComplexity
    at: AttackRequirements
    pr: PrivilegesRequired
    ui: UserInteraction
    vc: VulnConfidentiality
    vi: VulnIntegrity
    va: VulnAvailability
    sc: SubsequentConfidentiality = SubsequentConfidentiality.NONE
    si: SubsequentIntegrity = SubsequentIntegrity.NONE
    sa: SubsequentAvailability = SubsequentAvailability.NONE
    e: ExploitMaturity = ExploitMaturity.NOT_DEFINED
    cr: ConfidentialityRequirement = ConfidentialityRequirement.NOT_DEFINED
    ir: IntegrityRequirement = IntegrityRequirement.NOT_DEFINED
    ar: AvailabilityRequirement = AvailabilityRequirement.NOT_DEFINED

    def __post_init__(self) -> None:
        for code, enum_type in METRIC_ENUMS.items():
            value = getattr(self, code.lower())
            if not isinstance(value, enum_type):
                raise ValueError(f"metric {code} must be {enum_type.__name__}, got {value!r}")

    @classmethod
    def parse(cls, text: str) -> CvssV4Vector:
        """Parse a canonical ``CVSS:4.0/AV:N/...`` string with strict validation."""
        if not isinstance(text, str):
            raise ValueError("vector must be a string")
        parts = [part.strip() for part in text.strip().split("/")]
        if not parts or parts[0].upper() != VECTOR_PREFIX:
            raise ValueError(f"vector must start with {VECTOR_PREFIX}")
        tokens: dict[str, str] = {}
        for part in parts[1:]:
            if not part or ":" not in part:
                raise ValueError(f"malformed vector component: {part!r}")
            code, value = part.split(":", 1)
            code = code.upper()
            value = value.upper()
            if code not in METRIC_ENUMS:
                raise ValueError(f"unknown metric: {code}")
            if code in tokens:
                raise ValueError(f"duplicate metric: {code}")
            if not value:
                raise ValueError(f"empty value for metric: {code}")
            tokens[code] = value
        missing = sorted(BASE_METRIC_CODES - tokens.keys())
        if missing:
            raise ValueError(f"missing base metrics: {', '.join(missing)}")
        values: dict[str, Enum] = {}
        for code, enum_type in METRIC_ENUMS.items():
            raw = tokens.get(code)
            if raw is None:
                raw = enum_type.NOT_DEFINED.value if hasattr(enum_type, "NOT_DEFINED") else "N"
            try:
                values[code] = enum_type(raw)
            except ValueError as exc:
                valid = ", ".join(item.value for item in enum_type)
                message = f"invalid value {raw!r} for {code}; expected one of {valid}"
                raise ValueError(message) from exc
        return cls(**{code.lower(): value for code, value in values.items()})  # type: ignore[arg-type]

    def format(self) -> str:
        """Return the canonical, fully-populated vector string."""
        components = [VECTOR_PREFIX]
        for code in METRIC_ORDER:
            value = getattr(self, code.lower())
            components.append(f"{code}:{value.value}")
        return "/".join(components)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe mapping."""
        return {
            "version": CVSS_VERSION,
            "vector": self.format(),
            "metrics": {code: getattr(self, code.lower()).value for code in METRIC_ORDER},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CvssV4Vector:
        """Rebuild a vector from either a serialized vector or a metric map."""
        vector = data.get("vector")
        if isinstance(vector, str) and vector:
            return cls.parse(vector)
        metrics = data.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError("vector data must contain 'vector' or 'metrics'")
        tokens = [VECTOR_PREFIX]
        for code in METRIC_ORDER:
            raw = metrics.get(code)
            if isinstance(raw, str) and raw:
                tokens.append(f"{code}:{raw}")
        return cls.parse("/".join(tokens))


class Severity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANKS[self]

    @property
    def label(self) -> str:
        return self.value.title()

    @classmethod
    def from_score(cls, score: float) -> Severity:
        """Map a 0.0–10.0 score onto the CVSS v4 severity bands."""
        if not 0.0 <= score <= 10.0:
            raise ValueError(f"score out of range: {score}")
        for upper, band in SEVERITY_BANDS:
            if score <= upper:
                return band
        return cls.CRITICAL


_SEVERITY_RANKS = {
    Severity.NONE: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}
SEVERITY_BANDS: tuple[tuple[float, Severity], ...] = (
    (0.0, Severity.NONE),
    (3.9, Severity.LOW),
    (6.9, Severity.MEDIUM),
    (8.9, Severity.HIGH),
    (10.0, Severity.CRITICAL),
)


class LifecycleState(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    CONFIRMED = "confirmed"
    REMEDIATING = "remediating"
    RETEST = "retest"
    CLOSED = "closed"
    ACCEPTED_RISK = "accepted_risk"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()

    def legal_targets(self) -> frozenset[LifecycleState]:
        return LEGAL_TRANSITIONS[self]

    def can_transition_to(self, target: LifecycleState) -> bool:
        return target in LEGAL_TRANSITIONS[self]


LEGAL_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.DRAFT: frozenset({LifecycleState.OPEN}),
    LifecycleState.OPEN: frozenset(
        {LifecycleState.CONFIRMED, LifecycleState.CLOSED, LifecycleState.ACCEPTED_RISK}
    ),
    LifecycleState.CONFIRMED: frozenset({LifecycleState.REMEDIATING, LifecycleState.ACCEPTED_RISK}),
    LifecycleState.REMEDIATING: frozenset({LifecycleState.RETEST, LifecycleState.OPEN}),
    LifecycleState.RETEST: frozenset({LifecycleState.CLOSED, LifecycleState.REMEDIATING}),
    LifecycleState.CLOSED: frozenset({LifecycleState.OPEN}),
    LifecycleState.ACCEPTED_RISK: frozenset({LifecycleState.OPEN}),
}


class RetestVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"

    @property
    def label(self) -> str:
        return self.value.title()


@dataclass(slots=True)
class Finding:
    """A first-class finding record with score and lifecycle metadata."""

    title: str
    vector: CvssV4Vector
    id: str = field(default_factory=new_entity_id)
    description: str = ""
    severity: Severity = Severity.NONE
    lifecycle_state: LifecycleState = LifecycleState.DRAFT
    remediation_due: str | None = None
    remediation_notes: str = ""
    retest_count: int = 0
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.title or not self.title.strip():
            raise ValueError("finding title must not be empty")
        if len(self.title) > 200:
            raise ValueError("finding title must be at most 200 characters")
        if not isinstance(self.vector, CvssV4Vector):
            raise ValueError("finding vector must be a CvssV4Vector")
        if self.retest_count < 0:
            raise ValueError("retest_count must be >= 0")
        if self.remediation_due is not None:
            if not DATE_PATTERN.match(self.remediation_due):
                raise ValueError("remediation_due must be an ISO date (YYYY-MM-DD)")
            date.fromisoformat(self.remediation_due)

    @property
    def vector_text(self) -> str:
        return self.vector.format()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "vector": self.vector_text,
            "severity": self.severity.value,
            "lifecycle_state": self.lifecycle_state.value,
            "remediation_due": self.remediation_due,
            "remediation_notes": self.remediation_notes,
            "retest_count": self.retest_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Finding:
        return cls(
            id=str(data.get("id", new_entity_id())),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            vector=CvssV4Vector.parse(str(data.get("vector", DEFAULT_VECTOR_TEXT))),
            severity=Severity(str(data.get("severity", Severity.NONE.value))),
            lifecycle_state=LifecycleState(str(data.get("lifecycle_state", "draft"))),
            remediation_due=data.get("remediation_due"),
            remediation_notes=str(data.get("remediation_notes", "")),
            retest_count=int(data.get("retest_count", 0)),
            created_at=str(data.get("created_at", utc_now())),
        )


@dataclass(frozen=True, slots=True)
class RetestRecord:
    """An immutable audit entry recorded for every retest."""

    finding_id: str
    sequence: int
    verdict: RetestVerdict
    note: str
    occurred_at: str
    score: float

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("retest sequence must be >= 1")
        if not 0.0 <= self.score <= 10.0:
            raise ValueError("retest score must be between 0.0 and 10.0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "sequence": self.sequence,
            "verdict": self.verdict.value,
            "note": self.note,
            "occurred_at": self.occurred_at,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetestRecord:
        return cls(
            finding_id=str(data.get("finding_id", "")),
            sequence=int(data.get("sequence", 0)),
            verdict=RetestVerdict(str(data.get("verdict", "fail"))),
            note=str(data.get("note", "")),
            occurred_at=str(data.get("occurred_at", utc_now())),
            score=float(data.get("score", 0.0)),
        )
