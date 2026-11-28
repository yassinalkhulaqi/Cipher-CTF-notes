"""Tests for the CVSS v4 type contract and lifecycle table."""

from __future__ import annotations

import pytest

from redscribe.v4.findings_v4.types import (
    BASE_METRIC_CODES,
    DEFAULT_VECTOR_TEXT,
    ENVIRONMENTAL_METRIC_CODES,
    LEGAL_TRANSITIONS,
    METRIC_ENUMS,
    METRIC_ORDER,
    OPTIONAL_METRIC_CODES,
    THREAT_METRIC_CODES,
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
    SubsequentAvailability,
    SubsequentConfidentiality,
    SubsequentIntegrity,
    UserInteraction,
    VulnAvailability,
    VulnConfidentiality,
    VulnIntegrity,
)

BASE_VECTOR = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"


def test_metric_order_covers_all_enums() -> None:
    assert len(METRIC_ORDER) == 15
    assert len(set(METRIC_ORDER)) == 15
    assert set(METRIC_ENUMS) == set(METRIC_ORDER)
    assert len(BASE_METRIC_CODES) == 11
    assert {"E"} == THREAT_METRIC_CODES
    assert {"CR", "IR", "AR"} == ENVIRONMENTAL_METRIC_CODES
    assert {"E", "CR", "IR", "AR"} == OPTIONAL_METRIC_CODES


def test_attack_metric_values_and_labels() -> None:
    assert [item.value for item in AttackVector] == ["N", "A", "L", "P"]
    assert AttackVector.NETWORK.label == "Network"
    assert AttackVector.PHYSICAL.weight == 0.20
    assert [item.value for item in AttackComplexity] == ["L", "H"]
    assert AttackComplexity.HIGH.label == "High"
    assert AttackComplexity.LOW.weight == 0.77
    assert [item.value for item in AttackRequirements] == ["N", "P"]
    assert AttackRequirements.PRESENT.label == "Present"
    assert AttackRequirements.PRESENT.weight == 0.90


def test_access_metric_values_and_labels() -> None:
    assert [item.value for item in PrivilegesRequired] == ["N", "L", "H"]
    assert PrivilegesRequired.HIGH.weight == 0.27
    assert [item.value for item in UserInteraction] == ["N", "P"]
    assert UserInteraction.PASSIVE.label == "Passive"
    assert UserInteraction.PASSIVE.weight == 0.62


def test_impact_metric_values_and_weights() -> None:
    for enum_type in (
        VulnConfidentiality,
        VulnIntegrity,
        VulnAvailability,
        SubsequentConfidentiality,
        SubsequentIntegrity,
        SubsequentAvailability,
    ):
        assert [item.value for item in enum_type] == ["H", "L", "N"]
        assert enum_type("H").weight == 0.56
        assert enum_type("L").weight == 0.22
        assert enum_type("N").weight == 0.0
        assert enum_type("H").label == "High"
        assert enum_type("N").label == "None"


def test_threat_and_environment_metric_values() -> None:
    assert [item.value for item in ExploitMaturity] == ["X", "A", "P", "U"]
    assert ExploitMaturity.PROOF_OF_CONCEPT.label == "Proof of concept"
    assert ExploitMaturity.UNREPORTED.weight == 0.60
    for enum_type in (
        ConfidentialityRequirement,
        IntegrityRequirement,
        AvailabilityRequirement,
    ):
        assert [item.value for item in enum_type] == ["X", "H", "M", "L"]
        assert enum_type("X").weight == 1.0
        assert enum_type("H").weight == 1.5
        assert enum_type("L").weight == 0.5
        assert enum_type("M").label == "Medium"


def test_parse_canonical_vector() -> None:
    vector = CvssV4Vector.parse(BASE_VECTOR)
    assert vector.av is AttackVector.NETWORK
    assert vector.ac is AttackComplexity.LOW
    assert vector.vc is VulnConfidentiality.HIGH
    assert vector.vi is VulnIntegrity.HIGH
    assert vector.va is VulnAvailability.HIGH
    assert vector.sc is SubsequentConfidentiality.NONE
    assert vector.e is ExploitMaturity.NOT_DEFINED


def test_parse_is_order_independent() -> None:
    shuffled = "CVSS:4.0/SA:N/AV:N/CR:X/VI:H/AC:L/AT:N/PR:N/UI:N/VC:H/VA:H/SC:N/SI:N"
    assert CvssV4Vector.parse(shuffled) == CvssV4Vector.parse(BASE_VECTOR)


def test_parse_defaults_optional_metrics() -> None:
    vector = CvssV4Vector.parse(DEFAULT_VECTOR_TEXT)
    assert vector.e is ExploitMaturity.NOT_DEFINED
    assert vector.cr is ConfidentialityRequirement.NOT_DEFINED
    assert vector.ir is IntegrityRequirement.NOT_DEFINED
    assert vector.ar is AvailabilityRequirement.NOT_DEFINED


def test_parse_and_format_round_trip() -> None:
    vector = CvssV4Vector.parse(BASE_VECTOR)
    canonical = vector.format()
    assert canonical == f"{BASE_VECTOR}/E:X/CR:X/IR:X/AR:X"
    assert CvssV4Vector.parse(canonical) == vector
    assert CvssV4Vector.parse(vector.format()).format() == canonical


def test_format_uses_all_metrics_in_canonical_order() -> None:
    vector = CvssV4Vector.parse(BASE_VECTOR)
    codes = [part.split(":", 1)[0] for part in vector.format().split("/")[1:]]
    assert tuple(codes) == METRIC_ORDER


def test_vector_to_dict_and_from_dict() -> None:
    vector = CvssV4Vector.parse(BASE_VECTOR)
    data = vector.to_dict()
    assert data["version"] == "4.0"
    assert data["metrics"]["AV"] == "N"
    assert data["metrics"]["VC"] == "H"
    assert CvssV4Vector.from_dict(data) == vector


def test_vector_from_dict_with_metrics_only() -> None:
    data = {
        "metrics": {
            "AV": "L",
            "AC": "H",
            "AT": "P",
            "PR": "H",
            "UI": "P",
            "VC": "L",
            "VI": "N",
            "VA": "N",
            "SC": "N",
            "SI": "N",
            "SA": "N",
        }
    }
    vector = CvssV4Vector.from_dict(data)
    assert vector.av is AttackVector.LOCAL
    assert vector.ac is AttackComplexity.HIGH
    assert vector.vc is VulnConfidentiality.LOW


def test_from_dict_requires_vector_or_metrics() -> None:
    with pytest.raises(ValueError, match=r"vector.*or.*metrics"):
        CvssV4Vector.from_dict({"version": "4.0"})


@pytest.mark.parametrize(
    "text",
    [
        "",
        "CVSS:3.1/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N",
        "AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N",
    ],
)
def test_parse_rejects_bad_prefix(text: str) -> None:
    with pytest.raises(ValueError, match=r"must start with CVSS:4.0"):
        CvssV4Vector.parse(text)


def test_parse_rejects_non_string() -> None:
    with pytest.raises(ValueError, match="vector must be a string"):
        CvssV4Vector.parse(None)  # type: ignore[arg-type]


def test_parse_rejects_duplicate_metric() -> None:
    text = BASE_VECTOR + "/AV:L"
    with pytest.raises(ValueError, match="duplicate metric: AV"):
        CvssV4Vector.parse(text)


def test_parse_rejects_unknown_metric() -> None:
    with pytest.raises(ValueError, match="unknown metric: ZZ"):
        CvssV4Vector.parse(BASE_VECTOR + "/ZZ:N")


def test_parse_rejects_missing_base_metrics() -> None:
    with pytest.raises(ValueError, match="missing base metrics"):
        CvssV4Vector.parse("CVSS:4.0/AV:N/AC:L")


def test_parse_rejects_invalid_metric_value() -> None:
    text = BASE_VECTOR.replace("AV:N", "AV:Z")
    with pytest.raises(ValueError, match="invalid value 'Z' for AV"):
        CvssV4Vector.parse(text)


def test_parse_rejects_malformed_component() -> None:
    with pytest.raises(ValueError, match="malformed vector component"):
        CvssV4Vector.parse(BASE_VECTOR + "/BROKEN")


def test_parse_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="empty value for metric: E"):
        CvssV4Vector.parse(BASE_VECTOR + "/E:")


def test_vector_type_validation() -> None:
    with pytest.raises(ValueError, match="metric AV must be AttackVector"):
        CvssV4Vector(  # type: ignore[arg-type]
            av="N",
            ac=AttackComplexity.LOW,
            at=AttackRequirements.NONE,
            pr=PrivilegesRequired.NONE,
            ui=UserInteraction.NONE,
            vc=VulnConfidentiality.HIGH,
            vi=VulnIntegrity.HIGH,
            va=VulnAvailability.HIGH,
        )


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, Severity.NONE),
        (0.1, Severity.LOW),
        (3.9, Severity.LOW),
        (4.0, Severity.MEDIUM),
        (6.9, Severity.MEDIUM),
        (7.0, Severity.HIGH),
        (8.9, Severity.HIGH),
        (9.0, Severity.CRITICAL),
        (10.0, Severity.CRITICAL),
    ],
)
def test_severity_bands(score: float, expected: Severity) -> None:
    assert Severity.from_score(score) is expected


@pytest.mark.parametrize("score", [-0.1, 10.1, 42.0])
def test_severity_rejects_out_of_range(score: float) -> None:
    with pytest.raises(ValueError, match="score out of range"):
        Severity.from_score(score)


def test_severity_metadata() -> None:
    assert [item.value for item in Severity] == [
        "none",
        "low",
        "medium",
        "high",
        "critical",
    ]
    assert [item.rank for item in Severity] == [0, 1, 2, 3, 4]
    assert Severity.CRITICAL.label == "Critical"


def test_lifecycle_table_is_complete() -> None:
    assert set(LEGAL_TRANSITIONS) == set(LifecycleState)
    for state, targets in LEGAL_TRANSITIONS.items():
        assert targets, f"{state} has no legal transitions"
        assert state not in targets, f"{state} cannot transition to itself"
        for target in targets:
            assert state.can_transition_to(target)
            assert target in state.legal_targets()


def test_lifecycle_values_and_labels() -> None:
    assert [item.value for item in LifecycleState] == [
        "draft",
        "open",
        "confirmed",
        "remediating",
        "retest",
        "closed",
        "accepted_risk",
    ]
    assert LifecycleState.ACCEPTED_RISK.label == "Accepted Risk"


def test_every_legal_transition_matches_table() -> None:
    for source, targets in LEGAL_TRANSITIONS.items():
        for candidate in LifecycleState:
            assert source.can_transition_to(candidate) is (candidate in targets)


def test_specific_lifecycle_edges() -> None:
    assert LifecycleState.DRAFT.can_transition_to(LifecycleState.OPEN)
    assert LifecycleState.OPEN.can_transition_to(LifecycleState.CONFIRMED)
    assert LifecycleState.CONFIRMED.can_transition_to(LifecycleState.REMEDIATING)
    assert LifecycleState.REMEDIATING.can_transition_to(LifecycleState.RETEST)
    assert LifecycleState.RETEST.can_transition_to(LifecycleState.CLOSED)
    assert LifecycleState.CLOSED.can_transition_to(LifecycleState.OPEN)
    assert LifecycleState.ACCEPTED_RISK.can_transition_to(LifecycleState.OPEN)
    assert not LifecycleState.DRAFT.can_transition_to(LifecycleState.CLOSED)
    assert not LifecycleState.CLOSED.can_transition_to(LifecycleState.CONFIRMED)


def test_finding_defaults_and_serialization() -> None:
    vector = CvssV4Vector.parse(BASE_VECTOR)
    finding = Finding(title="SQL injection in login", vector=vector, id="finding-1")
    assert finding.lifecycle_state is LifecycleState.DRAFT
    assert finding.severity is Severity.NONE
    assert finding.retest_count == 0
    assert finding.remediation_due is None
    assert finding.vector_text == vector.format()
    data = finding.to_dict()
    assert data["id"] == "finding-1"
    assert data["severity"] == "none"
    assert Finding.from_dict(data).vector == vector
    assert Finding.from_dict(data).title == finding.title


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_finding_rejects_bad_title(title: str) -> None:
    with pytest.raises(ValueError, match="title"):
        Finding(title=title, vector=CvssV4Vector.parse(BASE_VECTOR))


def test_finding_rejects_bad_vector_type() -> None:
    with pytest.raises(ValueError, match="vector must be a CvssV4Vector"):
        Finding(title="x", vector="CVSS:4.0/AV:N")  # type: ignore[arg-type]


def test_finding_rejects_negative_retests() -> None:
    with pytest.raises(ValueError, match="retest_count must be >= 0"):
        Finding(
            title="x",
            vector=CvssV4Vector.parse(BASE_VECTOR),
            retest_count=-1,
        )


@pytest.mark.parametrize("due", ["2026/01/01", "not-a-date", "2026-13-01", "2026-02-30"])
def test_finding_rejects_bad_due_date(due: str) -> None:
    with pytest.raises(ValueError):
        Finding(title="x", vector=CvssV4Vector.parse(BASE_VECTOR), remediation_due=due)


def test_finding_accepts_valid_due_date() -> None:
    finding = Finding(
        title="x",
        vector=CvssV4Vector.parse(BASE_VECTOR),
        remediation_due="2026-12-31",
    )
    assert finding.remediation_due == "2026-12-31"


def test_retest_record_validation_and_serialization() -> None:
    record = RetestRecord(
        finding_id="finding-1",
        sequence=2,
        verdict=RetestVerdict.PASS,
        note="fixed",
        occurred_at="2026-01-02T00:00:00Z",
        score=7.5,
    )
    assert record.to_dict()["verdict"] == "pass"
    assert RetestRecord.from_dict(record.to_dict()) == record
    assert RetestVerdict.PASS.label == "Pass"


def test_retest_record_rejects_bad_sequence_and_score() -> None:
    with pytest.raises(ValueError, match="sequence must be >= 1"):
        RetestRecord("f", 0, RetestVerdict.FAIL, "", "now", 5.0)
    with pytest.raises(ValueError, match="score must be between"):
        RetestRecord("f", 1, RetestVerdict.FAIL, "", "now", 11.0)
