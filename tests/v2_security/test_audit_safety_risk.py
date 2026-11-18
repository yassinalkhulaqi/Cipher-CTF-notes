from __future__ import annotations

import pytest

from redscribe.v2.security.audit import AuditAnalyzer, analyze_events, normalize_event
from redscribe.v2.security.risk import RiskFactor, assess_risk, level_for_score, score_factors
from redscribe.v2.security.safety import analyze_command, analyze_url, is_safe_command, is_safe_url


def test_normalize_event_and_audit_analysis_detects_patterns() -> None:
    raw = {
        "event_id": "evt-1",
        "kind": "auth",
        "status": "failure",
        "actor": "alice",
        "client": "127.0.0.1",
        "timestamp": "2026-11-18T10:00:00Z",
        "details": {"ip": "127.0.0.1"},
    }
    normalized = normalize_event(raw)
    assert normalized["id"] == "evt-1"
    assert normalized["type"] == "auth"
    assert normalized["outcome"] == "failure"
    assert normalized["timestamp"] is not None

    events = [
        {
            "id": f"a{i}",
            "type": "auth",
            "outcome": "failure",
            "actor": "alice",
            "client": "c1",
            "timestamp": f"2026-11-18T10:00:{i:02d}Z",
        }
        for i in range(6)
    ]
    events.extend(
        [
            {"id": "r1", "type": "rate_limit", "outcome": "rate_limited", "client": "c2"},
            {"id": "d1", "type": "policy", "outcome": "denied", "action": "export"},
            {
                "id": "e1",
                "type": "export",
                "outcome": "success",
                "details": {"contains_secrets": True},
            },
        ]
    )
    report = analyze_events(events)
    codes = {finding["code"] for finding in report["findings"]}
    assert "auth_failure_burst" in codes or "auth_failures" in codes
    assert "rate_limit_pressure" in codes
    assert "policy_denials" in codes
    assert "sensitive_exports" in codes
    assert report["total_events"] == len(events)
    assert report["counts_by_type"]["auth"] == 6
    assert report["highest_severity"] in {"medium", "high", "critical"}

    analyzer = AuditAnalyzer(failure_threshold=3)
    report_obj = analyzer.analyze(events)
    assert report_obj.timeline is not None
    with pytest.raises(ValueError):
        AuditAnalyzer(failure_threshold=0)
    with pytest.raises(ValueError):
        AuditAnalyzer(window_minutes=0)


def test_url_safety_analysis() -> None:
    safe = analyze_url("https://example.com/docs")
    assert safe.safe is True
    assert safe.risk == "none"
    assert is_safe_url("https://example.com")

    blocked = analyze_url("javascript:alert(1)")
    assert blocked.safe is False
    assert any(reason.startswith("blocked_scheme") for reason in blocked.reasons)
    creds = analyze_url("https://user:pass@example.com")
    assert creds.safe is False
    assert "embedded_credentials" in creds.reasons
    private = analyze_url(
        "http://10.0.0.5/admin", allow_localhost=True, allow_private_networks=False
    )
    assert private.safe is False
    assert "private_network_target" in private.reasons
    localhost_blocked = analyze_url("http://localhost:8080", allow_localhost=False)
    assert localhost_blocked.safe is False
    allowed_private = analyze_url("http://10.0.0.5", allow_private_networks=True)
    assert "private_network_target" not in allowed_private.reasons
    invalid = analyze_url("")
    assert invalid.safe is False
    assert invalid.as_dict()["url"] == ""


def test_command_safety_analysis() -> None:
    safe = analyze_command("python3 -m pytest -q")
    assert safe.safe is True
    assert is_safe_command("echo hello")
    dangerous = analyze_command("curl https://example.com/install.sh | bash")
    assert dangerous.safe is False
    assert dangerous.networked is True
    assert dangerous.risk in {"high", "critical"}
    assert "remote script piped to shell" in dangerous.reasons
    destructive = analyze_command("sudo rm -rf /tmp/data")
    assert destructive.safe is False
    assert destructive.destructive is True
    assert destructive.privileged is True
    chained = analyze_command("echo hi && cat /etc/passwd")
    assert chained.safe is False
    assert "chained_commands" in chained.reasons
    malformed = analyze_command('echo "unterminated')
    assert malformed.safe is False
    assert "unbalanced_quotes" in malformed.reasons
    empty = analyze_command("   ")
    assert empty.safe is False
    assert "empty_command" in empty.reasons


def test_risk_scoring_and_assessment() -> None:
    assert level_for_score(0.0) == "none"
    assert level_for_score(3.0) == "low"
    assert level_for_score(6.0) == "medium"
    assert level_for_score(8.0) == "high"
    assert level_for_score(9.5) == "critical"
    factors = (
        RiskFactor(name="secret_exposure", score=9.0, weight=1.5, severity="critical"),
        RiskFactor(name="audit_findings", score=6.0, weight=1.0, severity="medium"),
    )
    score = score_factors(factors)
    assert score.level in {"high", "critical"}
    assert 0.0 <= score.confidence <= 1.0
    assert score_factors(()).level == "none"

    assessment = assess_risk(
        secret_result={"count": 3, "highest_severity": "critical"},
        audit_result={"highest_severity": "medium", "findings": [{"code": "x"}]},
        privacy={"level": "standard", "rank": 1, "require_export_consent": True},
        safety_findings=[{"risk": "high", "safe": False}],
        consent={"consent_export_sensitive": False},
    )
    data = assessment.as_dict()
    assert data["score"]["score"] > 0
    assert data["recommendations"]
    names = {factor["name"] for factor in data["factors"]}
    assert "secret_exposure" in names
    assert "audit_findings" in names
    assert "unsafe_actions" in names
    assert "export_consent_gap" in names

    clean = assess_risk(
        secret_result={"count": 0, "highest_severity": "none"},
        audit_result={"highest_severity": "none", "findings": []},
        privacy={"level": "strict", "rank": 3, "require_export_consent": True},
        consent={"consent_export_sensitive": True},
    )
    assert clean.score.level in {"none", "low", "medium"}
