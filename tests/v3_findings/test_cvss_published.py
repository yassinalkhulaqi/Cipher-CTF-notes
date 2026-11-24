"""Published CVSS v4.0 example vectors from the FIRST specification."""

from __future__ import annotations

import pytest

from redscribe.v3.findings.cvss_v4 import (
    SeverityBand,
    cvss_v4_breakdown,
    cvss_v4_score,
    cvss_v4_severity,
    parse_cvss_v4_vector,
    score_vector,
)
from redscribe.v3.findings.cvss_v4_data import MACRO_VECTOR_SCORES

PUBLISHED_BASE = (
    ("CVSS:4.0/AV:L/AC:L/AT:P/PR:L/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N", 7.3),
    ("CVSS:4.0/AV:L/AC:L/AT:N/PR:N/UI:A/VC:L/VI:N/VA:N/SC:N/SI:N/SA:N", 4.6),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:A/VC:N/VI:N/VA:N/SC:L/SI:L/SA:N", 5.1),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:L/SI:L/SA:N", 6.9),
    ("CVSS:4.0/AV:L/AC:L/AT:N/PR:H/UI:N/VC:N/VI:N/VA:N/SC:H/SI:N/SA:N", 5.9),
    ("CVSS:4.0/AV:L/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H", 9.4),
    ("CVSS:4.0/AV:P/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:H/SA:N/S:P/V:D", 8.3),
    ("CVSS:4.0/AV:A/AC:L/AT:N/PR:N/UI:N/VC:N/VI:L/VA:N/SC:H/SI:N/SA:H", 6.4),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N", 7.1),
    ("CVSS:4.0/AV:N/AC:L/AT:P/PR:N/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N", 8.2),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:A/VC:H/VI:H/VA:H/SC:L/SI:L/SA:N", 8.5),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:N/SI:L/SA:N", 6.9),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:N/VC:H/VI:H/VA:H/SC:H/SI:H/SA:H", 9.4),
)

PUBLISHED_THREAT = (
    ("CVSS:4.0/AV:N/AC:L/AT:P/PR:N/UI:P/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N/E:U", 5.2),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:H/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N/E:A", 8.6),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N/E:A", 8.7),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N/E:A", 9.3),
    ("CVSS:4.0/AV:N/AC:H/AT:P/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N/E:P", 8.2),
    ("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:H/SC:N/SI:N/SA:L/E:U", 6.6),
    ("CVSS:4.0/AV:L/AC:L/AT:N/PR:H/UI:N/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N/E:U", 5.6),
    ("CVSS:4.0/AV:L/AC:L/AT:N/PR:N/UI:P/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N/E:U/MUI:A", 5.7),
)

PUBLISHED_ENVIRONMENTAL = (
    (
        "CVSS:4.0/AV:N/AC:L/AT:P/PR:N/UI:N/VC:H/VI:L/VA:L/SC:N/SI:N/SA:N"
        "/CR:H/IR:L/AR:L/MAV:N/MAC:H/MVC:H/MVI:L/MVA:L",
        8.1,
    ),
    (
        "CVSS:4.0/AV:A/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N/MSI:S/S:P",
        9.7,
    ),
)


@pytest.mark.parametrize(("vector", "expected"), PUBLISHED_BASE)
def test_published_base_examples(vector: str, expected: float) -> None:
    """Published CVSS-B examples must be reproduced exactly."""
    result = score_vector(parse_cvss_v4_vector(vector))
    assert result.base == pytest.approx(expected)
    assert result.final == pytest.approx(expected)
    assert result.nomenclature == "CVSS-B"


@pytest.mark.parametrize(("vector", "expected"), PUBLISHED_THREAT)
def test_published_threat_examples(vector: str, expected: float) -> None:
    """Published CVSS-BT examples must be reproduced exactly."""
    result = score_vector(parse_cvss_v4_vector(vector))
    assert result.threat == pytest.approx(expected)
    assert result.final == pytest.approx(expected)
    assert result.nomenclature in {"CVSS-BT", "CVSS-BTE"}


@pytest.mark.parametrize(("vector", "expected"), PUBLISHED_ENVIRONMENTAL)
def test_published_environmental_examples(vector: str, expected: float) -> None:
    """Published CVSS-BE/BTE examples must be reproduced exactly."""
    result = score_vector(parse_cvss_v4_vector(vector))
    assert result.final == pytest.approx(expected)


def test_lookup_table_has_published_macrovector_scores() -> None:
    """The reference MacroVector table is complete and correctly scaled."""
    assert len(MACRO_VECTOR_SCORES) == 270
    assert MACRO_VECTOR_SCORES["000000"] == 10.0
    assert MACRO_VECTOR_SCORES["112221"] == 0.6
    assert MACRO_VECTOR_SCORES["212221"] == 0.1
    assert all(0.0 <= value <= 10.0 for value in MACRO_VECTOR_SCORES.values())


def test_no_impact_vector_scores_zero() -> None:
    """A vector with no impact on any system has a zero score."""
    vector = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:N/SI:N/SA:N"
    assert cvss_v4_score(vector) == 0.0
    assert score_vector(parse_cvss_v4_vector(vector)).macro_vector == "no-impact"
    assert cvss_v4_severity(vector) is SeverityBand.NONE


def test_severity_bands_match_v4_ranges() -> None:
    """Band boundaries follow the CVSS v4 qualitative rating scale."""
    assert cvss_v4_severity(0.0) is SeverityBand.NONE
    assert cvss_v4_severity(0.1) is SeverityBand.LOW
    assert cvss_v4_severity(3.9) is SeverityBand.LOW
    assert cvss_v4_severity(4.0) is SeverityBand.MEDIUM
    assert cvss_v4_severity(6.9) is SeverityBand.MEDIUM
    assert cvss_v4_severity(7.0) is SeverityBand.HIGH
    assert cvss_v4_severity(8.9) is SeverityBand.HIGH
    assert cvss_v4_severity(9.0) is SeverityBand.CRITICAL
    assert cvss_v4_severity(10.0) is SeverityBand.CRITICAL


def test_breakdown_contains_all_base_metrics() -> None:
    """Breakdown output drives the calculator UI without extra queries."""
    vector = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"
    breakdown = cvss_v4_breakdown(vector)
    assert breakdown["vector"] == vector
    assert breakdown["base"] == 9.3
    assert breakdown["severity"] == "critical"
    assert breakdown["nomenclature"] == "CVSS-B"
    assert breakdown["missing_base"] == []
    assert set(breakdown["metrics"]) >= {
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
    }
    assert breakdown["metrics"]["AV"]["label"] == "Attack Vector"


def test_scores_are_monotonic_when_impact_is_reduced() -> None:
    """Lowering an impact metric must not increase the final score."""
    parts = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/SC:N/SI:N/SA:N"
    high = cvss_v4_score(parts + "/VC:H/VI:H/VA:H")
    low = cvss_v4_score(parts + "/VC:H/VI:H/VA:L")
    none = cvss_v4_score(parts + "/VC:H/VI:H/VA:N")
    assert high >= low >= none


def test_threat_defaults_to_worst_case() -> None:
    """An undefined E metric is equivalent to Attacked in scoring."""
    base = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N"
    assert cvss_v4_score(base + "/E:X") == cvss_v4_score(base + "/E:A")
