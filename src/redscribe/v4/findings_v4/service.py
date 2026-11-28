"""Domain services for CVSS v4 scoring and governed finding operations.

The calculator implements a documented CVSS v4-style scoring pipeline: lookup
tables map each metric short code to a weight, an impact sub-score combines the
vulnerable and subsequent system impacts, and an exploitability sub-score is
built from the attack vector, complexity, requirements, privileges, user
interaction and threat maturity. Base, threat and environmental scores are
rounded up to one decimal in the closed interval 0.0–10.0.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date

from redscribe.v4.contracts import EntityKind, new_entity_id
from redscribe.v4.events import DomainEvent, EventBus, EventKind, utc_now

from .storage import FindingStore
from .types import (
    DATE_PATTERN,
    DEFAULT_VECTOR_TEXT,
    AttackComplexity,
    AttackRequirements,
    AttackVector,
    AvailabilityRequirement,
    ConfidentialityRequirement,
    CvssV4Vector,
    ExploitMaturity,
    Finding,
    IntegrityRequirement,
    LifecycleState,
    PrivilegesRequired,
    RetestRecord,
    RetestVerdict,
    Severity,
    UserInteraction,
)

AV_WEIGHTS: dict[AttackVector, float] = {
    AttackVector.NETWORK: 0.85,
    AttackVector.ADJACENT: 0.62,
    AttackVector.LOCAL: 0.55,
    AttackVector.PHYSICAL: 0.20,
}
AC_WEIGHTS: dict[AttackComplexity, float] = {
    AttackComplexity.LOW: 0.77,
    AttackComplexity.HIGH: 0.44,
}
AT_WEIGHTS: dict[AttackRequirements, float] = {
    AttackRequirements.NONE: 1.0,
    AttackRequirements.PRESENT: 0.90,
}
PR_WEIGHTS: dict[PrivilegesRequired, float] = {
    PrivilegesRequired.NONE: 0.85,
    PrivilegesRequired.LOW: 0.62,
    PrivilegesRequired.HIGH: 0.27,
}
UI_WEIGHTS: dict[UserInteraction, float] = {
    UserInteraction.NONE: 0.85,
    UserInteraction.PASSIVE: 0.62,
}
E_WEIGHTS: dict[ExploitMaturity, float] = {
    ExploitMaturity.NOT_DEFINED: 1.0,
    ExploitMaturity.ATTACKED: 1.0,
    ExploitMaturity.PROOF_OF_CONCEPT: 0.97,
    ExploitMaturity.UNREPORTED: 0.60,
}
IMPACT_WEIGHTS: dict[str, float] = {"H": 0.56, "L": 0.22, "N": 0.0}
REQUIREMENT_WEIGHTS: dict[str, float] = {"X": 1.0, "H": 1.5, "M": 1.0, "L": 0.5}
IMPACT_CAP = 0.915
EXPLOITABILITY_FACTOR = 8.22
VULN_IMPACT_FACTOR = 6.42
COMBINED_IMPACT_FACTOR = 7.52


def round_up(value: float) -> float:
    """Round a CVSS sub-score up to one decimal, clamped to 0.0–10.0."""
    if value <= 0.0:
        return 0.0
    return min(10.0, math.ceil(value * 10 - 1e-9) / 10)


@dataclass(frozen=True, slots=True)
class CvssV4Score:
    """The three CVSS v4 score flavours derived from a single vector."""

    vector: CvssV4Vector
    base: float
    threat: float
    environmental: float
    severity: Severity
    nomenclature: str

    @property
    def final(self) -> float:
        """The effective score used to assign a finding's severity."""
        return self.environmental

    def to_dict(self) -> dict[str, object]:
        return {
            "vector": self.vector.format(),
            "base": self.base,
            "threat": self.threat,
            "environmental": self.environmental,
            "final": self.final,
            "severity": self.severity.value,
            "nomenclature": self.nomenclature,
        }


class CvssV4Calculator:
    """A stateless, deterministic CVSS v4-style scorer with lookup tables."""

    def _impact(self, vector: CvssV4Vector, apply_requirements: bool) -> float:
        """Combine vulnerable-system and subsequent-system impact sub-scores.

        When no subsequent impact is defined the vulnerable-system score is used
        directly; otherwise the two sub-scores are combined with the documented
        ``v + s - v*s`` absorption formula.
        """
        cr = REQUIREMENT_WEIGHTS[vector.cr.value] if apply_requirements else 1.0
        ir = REQUIREMENT_WEIGHTS[vector.ir.value] if apply_requirements else 1.0
        ar = REQUIREMENT_WEIGHTS[vector.ar.value] if apply_requirements else 1.0
        c = min(IMPACT_CAP, IMPACT_WEIGHTS[vector.vc.value] * cr)
        i = min(IMPACT_CAP, IMPACT_WEIGHTS[vector.vi.value] * ir)
        a = min(IMPACT_CAP, IMPACT_WEIGHTS[vector.va.value] * ar)
        isc_vuln = 1.0 - (1.0 - c) * (1.0 - i) * (1.0 - a)
        sc = IMPACT_WEIGHTS[vector.sc.value]
        si = IMPACT_WEIGHTS[vector.si.value]
        sa = IMPACT_WEIGHTS[vector.sa.value]
        isc_sub = 1.0 - (1.0 - sc) * (1.0 - si) * (1.0 - sa)
        if isc_sub <= 0.0:
            impact = VULN_IMPACT_FACTOR * isc_vuln
        else:
            impact = COMBINED_IMPACT_FACTOR * (isc_vuln + isc_sub - isc_vuln * isc_sub)
        return min(impact, 10.0)

    def _exploitability(self, vector: CvssV4Vector, apply_threat: bool) -> float:
        """Build the exploitability sub-score from the attack metrics."""
        exploitability = (
            EXPLOITABILITY_FACTOR
            * AV_WEIGHTS[vector.av]
            * AC_WEIGHTS[vector.ac]
            * AT_WEIGHTS[vector.at]
            * PR_WEIGHTS[vector.pr]
            * UI_WEIGHTS[vector.ui]
        )
        if apply_threat:
            exploitability *= E_WEIGHTS[vector.e]
        return exploitability

    def base_score(self, vector: CvssV4Vector) -> float:
        """Score the vector with threat and environmental metrics ignored."""
        impact = self._impact(vector, apply_requirements=False)
        if impact <= 0.0:
            return 0.0
        return round_up(impact + self._exploitability(vector, apply_threat=False))

    def threat_score(self, vector: CvssV4Vector) -> float:
        """Score the vector with exploit maturity applied."""
        impact = self._impact(vector, apply_requirements=False)
        if impact <= 0.0:
            return 0.0
        return round_up(impact + self._exploitability(vector, apply_threat=True))

    def environmental_score(self, vector: CvssV4Vector) -> float:
        """Score the vector with both requirements and exploit maturity applied."""
        impact = self._impact(vector, apply_requirements=True)
        if impact <= 0.0:
            return 0.0
        return round_up(impact + self._exploitability(vector, apply_threat=True))

    @staticmethod
    def severity_for(score: float) -> Severity:
        """Map a numeric score onto the CVSS v4 severity bands."""
        return Severity.from_score(score)

    @staticmethod
    def nomenclature(vector: CvssV4Vector) -> str:
        """Return the CVSS v4 score nomenclature for the supplied metrics."""
        suffix = "B"
        if vector.e is not ExploitMaturity.NOT_DEFINED:
            suffix += "T"
        requirements = (vector.cr, vector.ir, vector.ar)
        if any(
            item
            not in (
                ConfidentialityRequirement.NOT_DEFINED,
                IntegrityRequirement.NOT_DEFINED,
                AvailabilityRequirement.NOT_DEFINED,
            )
            for item in requirements
        ):
            suffix += "E"
        return f"CVSS:{suffix}"

    def score(self, vector: CvssV4Vector) -> CvssV4Score:
        """Compute all three scores and the effective severity for a vector."""
        base = self.base_score(vector)
        threat = self.threat_score(vector)
        environmental = self.environmental_score(vector)
        return CvssV4Score(
            vector=vector,
            base=base,
            threat=threat,
            environmental=environmental,
            severity=self.severity_for(environmental),
            nomenclature=self.nomenclature(vector),
        )


class FindingError(Exception):
    """A domain-level finding error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message}


RETESTABLE_STATES: frozenset[LifecycleState] = frozenset(
    {
        LifecycleState.CONFIRMED,
        LifecycleState.REMEDIATING,
        LifecycleState.RETEST,
    }
)


class FindingService:
    """Create, score, transition and retest findings with event emission."""

    def __init__(
        self,
        store: FindingStore,
        bus: EventBus | None = None,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self.store = store
        self.bus = bus
        self.clock = clock
        self.calculator = CvssV4Calculator()

    def _emit(
        self,
        kind: EventKind,
        finding: Finding,
        payload: Mapping[str, object],
    ) -> None:
        if self.bus is None:
            return
        self.bus.publish(
            DomainEvent(
                kind=kind,
                aggregate_id=finding.id,
                aggregate_kind=EntityKind.FINDING,
                occurred_at=self.clock(),
                payload=dict(payload),
            )
        )

    def _require(self, finding_id: str) -> Finding:
        finding = self.store.get(finding_id)
        if finding is None:
            raise FindingError("not_found", f"finding not found: {finding_id}")
        return finding

    @staticmethod
    def _parse_vector(vector_text: str) -> CvssV4Vector:
        try:
            return CvssV4Vector.parse(vector_text)
        except (ValueError, TypeError) as exc:
            raise FindingError("invalid_vector", str(exc)) from exc

    def create(
        self,
        title: str,
        vector_text: str = DEFAULT_VECTOR_TEXT,
        description: str = "",
        finding_id: str | None = None,
        lifecycle_state: LifecycleState = LifecycleState.DRAFT,
    ) -> Finding:
        """Create and persist a finding, emitting ``FINDING_CREATED``."""
        vector = self._parse_vector(vector_text)
        finding = Finding(
            title=title,
            vector=vector,
            id=finding_id or new_entity_id(),
            description=description,
            lifecycle_state=lifecycle_state,
        )
        finding.severity = self.calculator.severity_for(self.calculator.base_score(vector))
        self.store.add(finding)
        self._emit(
            EventKind.FINDING_CREATED,
            finding,
            {
                "title": finding.title,
                "vector": finding.vector_text,
                "severity": finding.severity.value,
            },
        )
        return finding

    def score(self, finding_id: str) -> CvssV4Score:
        """Re-score a finding from its vector, emitting ``FINDING_SCORED``."""
        finding = self._require(finding_id)
        result = self.calculator.score(finding.vector)
        finding.severity = result.severity
        self.store.update(finding)
        self._emit(
            EventKind.FINDING_SCORED,
            finding,
            {
                "base": result.base,
                "threat": result.threat,
                "environmental": result.environmental,
                "severity": result.severity.value,
            },
        )
        return result

    def transition(self, finding_id: str, target: LifecycleState) -> Finding:
        """Move a finding along a legal lifecycle edge."""
        finding = self._require(finding_id)
        if not isinstance(target, LifecycleState):
            raise FindingError("invalid_state", f"unknown lifecycle state: {target!r}")
        if not finding.lifecycle_state.can_transition_to(target):
            raise FindingError(
                "illegal_transition",
                f"cannot move from {finding.lifecycle_state.value} to {target.value}",
            )
        finding.lifecycle_state = target
        self.store.update(finding)
        return finding

    def assign_remediation(
        self,
        finding_id: str,
        due: str,
        notes: str = "",
    ) -> Finding:
        """Assign an ISO remediation due date and optional notes."""
        finding = self._require(finding_id)
        if not isinstance(due, str) or not DATE_PATTERN.match(due):
            raise FindingError("invalid_due", "remediation due must be YYYY-MM-DD")
        try:
            date.fromisoformat(due)
        except ValueError as exc:
            raise FindingError("invalid_due", "remediation due is not a real date") from exc
        finding.remediation_due = due
        finding.remediation_notes = notes
        self.store.update(finding)
        return finding

    def retest(
        self,
        finding_id: str,
        verdict: RetestVerdict,
        note: str = "",
        occurred_at: str | None = None,
    ) -> RetestRecord:
        """Record a retest, increment the counter and emit ``FINDING_RETESTED``."""
        finding = self._require(finding_id)
        if not isinstance(verdict, RetestVerdict):
            raise FindingError("invalid_verdict", f"unknown retest verdict: {verdict!r}")
        if finding.lifecycle_state not in RETESTABLE_STATES:
            raise FindingError(
                "illegal_transition",
                f"cannot retest a finding in {finding.lifecycle_state.value}",
            )
        score = self.calculator.environmental_score(finding.vector)
        sequence = finding.retest_count + 1
        finding.retest_count = sequence
        target = {
            RetestVerdict.PASS: LifecycleState.CLOSED,
            RetestVerdict.FAIL: LifecycleState.REMEDIATING,
            RetestVerdict.PARTIAL: LifecycleState.REMEDIATING,
        }[verdict]
        if finding.lifecycle_state.can_transition_to(target):
            finding.lifecycle_state = target
        self.store.update(finding)
        record = RetestRecord(
            finding_id=finding.id,
            sequence=sequence,
            verdict=verdict,
            note=note,
            occurred_at=occurred_at or self.clock(),
            score=score,
        )
        self.store.add_retest(record)
        self._emit(
            EventKind.FINDING_RETESTED,
            finding,
            {
                "verdict": verdict.value,
                "sequence": sequence,
                "state": finding.lifecycle_state.value,
                "score": score,
            },
        )
        return record

    def history(self, finding_id: str) -> tuple[RetestRecord, ...]:
        """Return the retest history for a finding, oldest first."""
        self._require(finding_id)
        return self.store.retests(finding_id)

    def get(self, finding_id: str) -> Finding:
        """Return a finding or raise a domain not-found error."""
        return self._require(finding_id)

    def rescore_all(self) -> list[Finding]:
        """Re-score every stored finding and return those whose score changed."""
        changed: list[Finding] = []
        for finding in self.store.all():
            previous = finding.severity
            self.score(finding.id)
            if finding.severity is not previous:
                changed.append(finding)
        return changed
