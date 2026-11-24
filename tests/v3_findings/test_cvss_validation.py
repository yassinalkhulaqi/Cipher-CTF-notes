"""Tests for CVSS v4 vector validation, defaults, and immutability."""

from __future__ import annotations

import pytest

from redscribe.v3.findings.cvss_v4 import (
    CvssV4Error,
    SeverityBand,
    cvss_v4_severity,
    parse_cvss_v4_vector,
)

BASE = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"


@pytest.mark.parametrize(
    "vector",
    [
        "",
        "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "CVSS:4.0/AV:N",
        "CVSS:4.0/AV:Z/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N",
        "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SX:N",
        "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N/AV:A",
        "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N/extra",
    ],
)
def test_invalid_vectors_are_rejected(vector: str) -> None:
    """Only well-formed, complete CVSS v4 vectors are accepted."""
    with pytest.raises(CvssV4Error):
        parse_cvss_v4_vector(vector)


def test_vector_defaults_and_effective_values() -> None:
    """X-valued threat and environmental metrics use worst-case defaults."""
    vector = parse_cvss_v4_vector(BASE)
    assert vector.version == "4.0"
    assert vector.effective("E") == "A"
    assert vector.effective("CR") == "H"
    assert vector.effective("AV") == "N"
    assert vector.effective("MSI") == "X"
    assert vector.metric("missing", "fallback") == "fallback"


def test_modified_metrics_override_base_values() -> None:
    """Modified base metrics replace the corresponding base metrics."""
    vector = parse_cvss_v4_vector(BASE + "/MAV:P/MVI:L/MSI:S")
    assert vector.effective("AV") == "P"
    assert vector.effective("VI") == "L"
    assert vector.metrics["MSI"] == "S"
    assert vector.effective("MSI") == "S"
    explicit_x = parse_cvss_v4_vector(BASE + "/MUI:X")
    assert explicit_x.effective("UI") == "N"


def test_metric_group_views_are_disjoint() -> None:
    """Base, threat, environmental, and supplemental views partition metrics."""
    vector = parse_cvss_v4_vector(BASE + "/E:U/CR:L/MAV:A/S:P/AU:Y/R:I/V:C/RE:L/U:Amber")
    assert len(vector.base) == 11
    assert vector.threat == {"E": "U"}
    assert set(vector.environmental) == {"CR", "MAV"}
    assert vector.supplemental == {
        "S": "P",
        "AU": "Y",
        "R": "I",
        "V": "C",
        "RE": "L",
        "U": "Amber",
    }


def test_vector_transformations_are_immutable() -> None:
    """Derived vectors are new instances and the original stays unchanged."""
    vector = parse_cvss_v4_vector(BASE)
    changed = vector.with_metric("E", "U")
    assert vector.metric("E") == ""
    assert changed.metric("E") == "U"
    stripped = changed.without(("E",))
    assert stripped.render() == BASE
    assert vector.render() == BASE


def test_supplemental_metrics_do_not_change_score() -> None:
    """Safety and other supplemental metrics never alter the numeric score."""
    from redscribe.v3.findings.cvss_v4 import cvss_v4_score

    vector = parse_cvss_v4_vector(BASE)
    augmented = vector.with_metric("S", "P").with_metric("AU", "Y")
    assert cvss_v4_score(augmented) == cvss_v4_score(vector)


def test_safety_value_is_only_valid_on_modified_subsequent_metrics() -> None:
    """Safety is accepted on MSI/MSA and rejected on base impact metrics."""
    parse_cvss_v4_vector(BASE + "/MSI:S/MSA:S")
    with pytest.raises(CvssV4Error):
        parse_cvss_v4_vector(BASE + "/SI:S")


def test_as_dict_is_json_safe() -> None:
    """Vector serialization exposes metrics and the canonical string."""
    payload = parse_cvss_v4_vector(BASE + "/E:P").as_dict()
    assert payload["version"] == "4.0"
    assert payload["metrics"]["E"] == "P"
    assert payload["vector"].endswith("/E:P")


def test_severity_band_helpers() -> None:
    """Severity bands expose stable ranks and color tokens."""
    assert SeverityBand.for_score(9.5) is SeverityBand.CRITICAL
    assert SeverityBand.CRITICAL.rank == 4
    assert SeverityBand.NONE.rank == 0
    assert "severity-critical" in SeverityBand.CRITICAL.color_token
    assert cvss_v4_severity(9.1) is SeverityBand.CRITICAL
