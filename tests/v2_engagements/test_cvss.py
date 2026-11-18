from __future__ import annotations

import pytest

from redscribe.v2.engagements.cvss import (
    BASE_METRICS,
    METRIC_LABELS,
    CvssError,
    compare_severities,
    cvss_base_score,
    cvss_breakdown,
    cvss_severity,
    parse_cvss_vector,
    representative_score,
    score_vector,
    severity_agreement,
)
from redscribe.v2.engagements.models import Severity

CRITICAL_VECTOR = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
LOW_VECTOR = "CVSS:3.1/AV:P/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N"


def test_parse_cvss_vector_extracts_base_metrics() -> None:
    vector = parse_cvss_vector(CRITICAL_VECTOR)
    assert vector.version == "3.1"
    assert vector.metric("AV") == "N"
    assert vector.metric("A") == "H"
    assert vector.extras == {}
    assert list(vector.metrics) == list(BASE_METRICS)


def test_parse_cvss_vector_separates_and_sorts_extras() -> None:
    vector = parse_cvss_vector(f"{CRITICAL_VECTOR}/E:F/RL:O/RC:C")
    assert vector.extras == {"E": "F", "RL": "O", "RC": "C"}
    assert vector.render().endswith("/E:F/RC:C/RL:O")
    assert set(vector.as_dict()) >= set(BASE_METRICS)


def test_parse_cvss_vector_accepts_v30_and_whitespace() -> None:
    vector = parse_cvss_vector(f"  {CRITICAL_VECTOR.replace('3.1', '3.0')}  ")
    assert vector.version == "3.0"
    assert vector.render().startswith("CVSS:3.0/")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "CVSS:2.0/AV:N",
        "CVSS:4.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "CVSS:3.1/AV:N/AC:L",
        "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H/extra",
        "not a vector",
    ],
)
def test_parse_cvss_vector_rejects_invalid_input(value: str) -> None:
    with pytest.raises(CvssError):
        parse_cvss_vector(value)


def test_parse_cvss_vector_rejects_non_string() -> None:
    with pytest.raises(CvssError, match="must be a string"):
        parse_cvss_vector(None)


@pytest.mark.parametrize(
    ("vector", "expected"),
    [
        (CRITICAL_VECTOR, 9.8),
        ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0.0),
        ("CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:U/C:L/I:L/A:L", 3.7),
    ],
)
def test_cvss_base_score_uses_standard_values(vector: str, expected: float) -> None:
    assert cvss_base_score(vector) == pytest.approx(expected, abs=0.1)


def test_low_vector_scores_below_four() -> None:
    score = cvss_base_score(LOW_VECTOR)
    assert 0.0 < score < 4.0


def test_scope_changed_increases_impact() -> None:
    unchanged = cvss_base_score(CRITICAL_VECTOR)
    changed = cvss_base_score(CRITICAL_VECTOR.replace("S:U", "S:C"))
    assert changed >= unchanged
    assert changed <= 10.0


def test_score_vector_rejects_invalid_scope() -> None:
    vector = parse_cvss_vector(CRITICAL_VECTOR.replace("S:U", "S:X"))
    with pytest.raises(CvssError, match="Invalid value for S"):
        score_vector(vector)


@pytest.mark.parametrize(
    ("metric", "value"),
    [("AV", "X"), ("AC", "M"), ("PR", "Z"), ("UI", "X"), ("C", "Q")],
)
def test_score_vector_rejects_invalid_metric_values(metric: str, value: str) -> None:
    parts = CRITICAL_VECTOR.split("/")
    parts = [part for part in parts if not part.startswith(f"{metric}:")]
    parts.append(f"{metric}:{value}")
    vector = parse_cvss_vector("/".join(parts))
    with pytest.raises(CvssError):
        score_vector(vector)


def test_cvss_severity_accepts_vectors_and_numbers() -> None:
    assert cvss_severity(CRITICAL_VECTOR) is Severity.CRITICAL
    assert cvss_severity(9.8) is Severity.CRITICAL
    assert cvss_severity(5.0) is Severity.MEDIUM
    assert cvss_severity(0.0) is Severity.INFO


def test_cvss_breakdown_contains_labels_and_extras() -> None:
    result = cvss_breakdown(f"{CRITICAL_VECTOR}/E:F")
    assert result["version"] == "3.1"
    assert result["score"] == pytest.approx(9.8, abs=0.1)
    assert result["severity"] == "critical"
    assert result["metrics"]["AV"] == {"code": "N", "label": "Attack Vector"}
    assert result["extras"] == {"E": "F"}
    assert set(METRIC_LABELS) == set(BASE_METRICS)


def test_severity_agreement_handles_empty_and_matching_vectors() -> None:
    assert severity_agreement(Severity.LOW, "") is True
    assert severity_agreement(Severity.CRITICAL, CRITICAL_VECTOR) is True
    assert severity_agreement(Severity.HIGH, CRITICAL_VECTOR) is False


def test_compare_severities_orders_from_info_to_critical() -> None:
    assert compare_severities(Severity.LOW, Severity.HIGH) < 0
    assert compare_severities(Severity.HIGH, Severity.LOW) > 0
    assert compare_severities(Severity.MEDIUM, Severity.MEDIUM) == 0
    assert sorted(
        [Severity.CRITICAL, Severity.INFO, Severity.HIGH], key=lambda item: item.value
    ) == [Severity.CRITICAL, Severity.HIGH, Severity.INFO]


def test_representative_score_matches_severity_helpers() -> None:
    assert representative_score(Severity.INFO) == 0.0
    assert representative_score(Severity.CRITICAL) == 10.0
    assert representative_score(Severity.MEDIUM) == 6.9
