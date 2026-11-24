"""Tests for secret-free posture scoring."""

from __future__ import annotations

import json

import pytest

from redscribe.v3.vault_security.crypto import RECOMMENDED_ITERATIONS
from redscribe.v3.vault_security.policy import PolicyError, SecretPattern, default_policy
from redscribe.v3.vault_security.posture import (
    PostureLevel,
    assert_secret_free,
    level_for_score,
    report_to_json,
    score_posture,
)


def snapshots(**overrides: dict[str, object]) -> dict[str, dict[str, object]]:
    base: dict[str, dict[str, object]] = {
        "vault": {"state": "locked", "initialized": True, "ciphertext_bytes": 120},
        "keyring": {
            "initialized": True,
            "keys": [
                {
                    "status": "active",
                    "iterations": RECOMMENDED_ITERATIONS,
                    "created_at": 90.0,
                }
            ],
        },
        "recovery": {
            "active": 2,
            "codes": [{"state": "active", "created_at": 95.0}],
        },
        "policy": {
            "patterns": [{"name": f"p{index}"} for index in range(6)],
            "rules": [{"rule_id": "r1"}],
            "consents": {"granted": [], "pending": ["ai_assist"]},
        },
        "audit": {"stats": {"total": 3}},
    }
    base.update(overrides)
    return base


def test_healthy_posture_is_strong() -> None:
    report = score_posture(snapshots(), now=1000.0)
    assert report.score == 100
    assert report.level is PostureLevel.STRONG
    assert report.passed == 10
    assert report.total == 10
    assert report.gaps == ()
    assert report.contains_secrets is False
    assert "gap_ids" in report.as_dict()


def test_weak_posture_reports_gaps_without_values() -> None:
    weak = snapshots()
    weak["vault"] = {"state": "unlocked", "initialized": True}
    weak["keyring"] = {"initialized": False, "keys": []}
    weak["recovery"] = {"active": 0, "codes": []}
    weak["policy"] = {
        "patterns": [],
        "rules": [],
        "consents": {"granted": ["export_plaintext"], "pending": []},
    }
    weak["audit"] = {"stats": {"total": 0}}
    report = score_posture(weak, now=1000.0)
    assert report.score < 50
    assert report.level is PostureLevel.CRITICAL
    assert len(report.gaps) >= 8
    rendered = report_to_json(report)
    assert "iterations" not in rendered
    assert "AKIA" not in rendered
    assert "hunter2secret" not in rendered
    assert_secret_free(report, default_policy())


def test_kdf_strength_and_key_age_gaps() -> None:
    weak = snapshots()
    weak["keyring"] = {
        "initialized": True,
        "keys": [{"status": "active", "iterations": 1000, "created_at": -20_000_000.0}],
    }
    report = score_posture(weak, now=1000.0)
    gap_ids = {check.check_id for check in report.gaps}
    assert {"kdf_strength", "key_rotation"} <= gap_ids


def test_recovery_freshness_gap() -> None:
    stale = snapshots()
    stale["recovery"] = {
        "active": 1,
        "codes": [{"state": "active", "created_at": -20_000_000.0}],
    }
    report = score_posture(stale, now=1000.0)
    assert {check.check_id for check in report.gaps} >= {"recovery_fresh"}


def test_score_levels_and_invalid_score() -> None:
    assert level_for_score(0) is PostureLevel.CRITICAL
    assert level_for_score(50) is PostureLevel.WEAK
    assert level_for_score(70) is PostureLevel.FAIR
    assert level_for_score(85) is PostureLevel.STRONG
    with pytest.raises(ValueError, match="score"):
        level_for_score(-1)


def test_warnings_and_report_serialization() -> None:
    report = score_posture(snapshots(), now=1234.0, warnings=("not configured",))
    assert report.warnings == ("not configured",)
    payload = json.loads(report_to_json(report))
    assert payload["generated_at"] == 1234.0
    assert payload["contains_secrets"] is False
    assert payload["warnings"] == ["not configured"]


def test_assert_secret_free_rejects_contaminated_report() -> None:
    report = score_posture(snapshots(), now=1000.0)
    engine = default_policy()
    engine.add_pattern(
        SecretPattern(name="report_secret", expression=r"LEAK-[0-9]{6}", severity="high")
    )
    contaminated = report.__class__(
        score=report.score,
        level=report.level,
        checks=report.checks,
        generated_at=report.generated_at,
        warnings=("LEAK-123456",),
    )
    with pytest.raises(PolicyError, match="secret-free"):
        assert_secret_free(contaminated, engine)
