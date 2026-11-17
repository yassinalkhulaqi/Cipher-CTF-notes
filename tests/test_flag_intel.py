from __future__ import annotations

from redscribe.domain.flags import FLAG_PREFIXES
from redscribe.domain.models import FlagCandidate
from redscribe.domain.registry import (
    FLAG_FORMATS,
    FORMATS_BY_KEY,
    assess_flag,
    best_candidate,
    confidence_band,
    infer_category,
    rank_candidates,
    score_confidence,
)
from redscribe.domain.validation import (
    check_uniqueness,
    find_duplicate_groups,
    prefix_distribution,
    screen_candidates,
    unique_flags,
    validate_flag_format,
)
from redscribe.services.flag_intel import (
    KNOWN_FLAG_PATTERNS,
    PATTERNS_BY_PREFIX,
    build_flag_insights,
    build_flag_intel_report,
    check_flag,
    flag_assessment_rows,
    flag_insights_payload,
    flag_intel_report_payload,
    flag_patterns_payload,
    rank_collected_flags,
    screen_vault_flags,
)
from redscribe.storage.db import Vault
from redscribe.ui.web.api import Api


def test_registry_covers_every_detected_prefix() -> None:
    assert {pattern.pattern_key for pattern in KNOWN_FLAG_PATTERNS} == set(FLAG_PREFIXES)


def test_registry_keys_are_unique_and_lowercase() -> None:
    keys = [pattern.pattern_key for pattern in KNOWN_FLAG_PATTERNS]
    assert len(keys) == len(set(keys))
    assert all(key == key.lower() for key in keys)
    assert set(PATTERNS_BY_PREFIX) == set(keys)


def test_curated_platforms_describe_the_well_known_events() -> None:
    assert PATTERNS_BY_PREFIX["htb"].platform == "Hack The Box"
    assert PATTERNS_BY_PREFIX["thm"].platform == "TryHackMe"
    assert PATTERNS_BY_PREFIX["picoctf"].platform == "picoCTF"


def test_check_flag_accepts_a_known_format() -> None:
    check = check_flag("HTB{demo_value}")
    assert check.ok is True
    assert check.known_prefix is True
    assert check.platform == "Hack The Box"
    assert check.value_length == len("demo_value")


def test_check_flag_accepts_an_unknown_but_wellformed_prefix() -> None:
    check = check_flag("unknownctf{demo_value}")
    assert check.ok is True
    assert check.known_prefix is False
    assert "not a known event prefix" in check.hint


def test_check_flag_rejects_empty_and_unbalanced_values() -> None:
    assert check_flag("").ok is False
    assert check_flag("flag{}").ok is False
    assert check_flag("flag{unterminated").ok is False
    assert check_flag("flag{a}b}").ok is False


def test_check_flag_trims_surrounding_quotes_and_whitespace() -> None:
    check = check_flag('  "HTB{abc}"  ')
    assert check.ok is True
    assert check.known_prefix is True


def _seed(vault: Vault) -> None:
    htb = vault.create_node(
        "HTB — Corporate",
        content="loot:\nHTB{one}\n",
        flag="HTB{one}",
        status="done",
    )
    vault.create_node("Same flag elsewhere", content=htb.flag, status="todo")
    vault.create_node(
        "Done without flag",
        content="## progress\n\nnothing captured yet",
        status="done",
    )
    vault.create_node("Open and flagless", content="## idea", status="todo")


def test_build_flag_insights_counts_manual_detected_and_duplicates(vault: Vault) -> None:
    _seed(vault)

    insights = build_flag_insights(vault)

    assert insights.unique_flags == 1
    assert insights.manual_flags == 1
    assert insights.detected_flags == 0
    assert [(item.prefix, item.platform, item.count) for item in insights.by_source] == [
        ("htb", "Hack The Box", 1)
    ]
    assert len(insights.duplicates) == 1
    assert insights.duplicates[0].flag == "HTB{one}"
    assert insights.duplicates[0].note_count == 2
    assert insights.missing_flag_notes == 1


def test_build_flag_insights_empty_vault(vault: Vault) -> None:
    insights = build_flag_insights(vault)

    assert insights.unique_flags == 0
    assert insights.by_source == ()
    assert insights.duplicates == ()
    assert insights.missing_flag_notes == 0


def test_flag_patterns_payload_shapes_registry() -> None:
    payload = flag_patterns_payload()

    assert payload
    first = payload[0]
    assert set(first) == {"prefix", "pattern_key", "platform", "example", "hint", "category"}
    assert first["example"] == f"{first['prefix']}{{...}}"


def test_flag_insights_payload_serializes(vault: Vault) -> None:
    _seed(vault)

    payload = flag_insights_payload(build_flag_insights(vault))

    assert set(payload) == {
        "unique_flags",
        "manual_flags",
        "detected_flags",
        "by_source",
        "duplicates",
        "missing_flag_notes",
    }
    assert payload["unique_flags"] == 1


def test_api_flag_endpoints(vault: Vault) -> None:
    api = Api(vault)

    patterns = api.flag_patterns({})
    assert patterns
    assert patterns[0]["example"].endswith("{...}")

    insights = api.flag_insights({})
    assert set(insights) == {
        "unique_flags",
        "manual_flags",
        "detected_flags",
        "by_source",
        "duplicates",
        "missing_flag_notes",
    }


def test_domain_registry_covers_every_prefix_with_weights() -> None:
    assert set(FORMATS_BY_KEY) == set(FLAG_PREFIXES)
    assert len(FLAG_FORMATS) == len(FLAG_PREFIXES)
    assert FORMATS_BY_KEY["htb"].confidence > FORMATS_BY_KEY["flag"].confidence
    assert FORMATS_BY_KEY["hacktoday"].category == "ctf"


def test_infer_category_prefers_payload_keywords_over_prefix() -> None:
    assert infer_category("picoCTF{demo_buffer_overflow}") == "pwn"
    assert infer_category("HTB{rsa_key_recovered}") == "crypto"
    assert infer_category("HTB{plain_value}") == "htb"
    assert infer_category("random{value}") == "generic"


def test_confidence_scoring_and_bands() -> None:
    assert score_confidence("HTB{demo_value}") == 0.98
    assert score_confidence("flag{abc}") == 0.56
    assert score_confidence("not a flag") == 0.0
    assert confidence_band(0.0) == "invalid"
    assert confidence_band(0.56) == "low"
    assert confidence_band(0.70) == "medium"
    assert confidence_band(0.98) == "high"


def test_assess_flag_reports_reasons_and_rank_orders_results() -> None:
    assessment = assess_flag("HTB{demo_value}")
    assert assessment.known_prefix is True
    assert assessment.band == "high"
    assert assessment.category == "htb"
    assert "known prefix: HTB" in assessment.reasons

    ranked = rank_candidates(["flag{abc}", "HTB{demo_value}"])
    assert ranked[0].value == "HTB{demo_value}"
    assert best_candidate([]) is None
    best = best_candidate(["flag{abc}"])
    assert best is not None
    assert best.value == "flag{abc}"


def test_validate_flag_format_reports_specific_issues() -> None:
    valid = validate_flag_format("HTB{demo_value}")
    assert valid.ok is True
    assert valid.prefix == "HTB"
    assert valid.body == "demo_value"

    malformed = validate_flag_format("flag{a}b}")
    assert malformed.ok is False
    assert [issue.code for issue in malformed.issues] == ["shape"]

    unknown = validate_flag_format("unknownctf{demo_value}")
    assert unknown.ok is True
    assert [issue.severity for issue in unknown.issues] == ["warning"]

    blank = validate_flag_format("flag{}")
    assert blank.ok is False
    assert "body-empty" in [issue.code for issue in blank.issues]


def test_uniqueness_helpers_normalize_prefixes() -> None:
    values = ["HTB{one}", "htb{one}", "HTB{two}", "flag{one}"]
    assert unique_flags(values) == ["HTB{one}", "HTB{two}", "flag{one}"]
    assert unique_flags(values, case_sensitive=False)[0] == "HTB{one}"

    groups = find_duplicate_groups(values)
    assert len(groups) == 1
    assert set(groups[0][1]) == {"HTB{one}", "htb{one}"}

    report = check_uniqueness(values)
    assert report.total == 4
    assert report.unique == 3
    assert report.duplicate_count == 1
    assert prefix_distribution(values)[0] == ("htb", 3)


def test_screen_candidates_combines_validation_and_confidence() -> None:
    screened = screen_candidates(
        [FlagCandidate("HTB{demo_value}", "note:1"), FlagCandidate("bad value", "note:2")]
    )
    assert screened[0].ok is True
    assert screened[0].confidence == 0.98
    assert screened[0].source == "note:1"
    assert screened[1].ok is False
    assert screened[1].confidence == 0.0
    assert screened[1].issues[0].code == "shape"


def _seed_confidence(vault: Vault) -> None:
    vault.create_node("HTB box", content="HTB{demo_value}", flag="HTB{demo_value}", status="done")
    vault.create_node("Weak flag", content="flag{abc}", status="todo")
    vault.create_node("Pwned", content="picoCTF{demo_buffer_overflow}", status="done")


def test_confidence_report_over_vault(vault: Vault) -> None:
    _seed_confidence(vault)

    rows = rank_collected_flags(vault)
    assert [row.flag for row in rows] == [
        "HTB{demo_value}",
        "picoCTF{demo_buffer_overflow}",
        "flag{abc}",
    ]
    assert all(row.confidence > 0 for row in rows)

    report = build_flag_intel_report(vault)
    assert report.total == 3
    assert report.high_confidence == 2
    assert report.medium_confidence == 0
    assert report.low_confidence == 1
    assert report.weak_flags == ("flag{abc}",)
    assert [(item.category, item.count) for item in report.categories] == [
        ("generic", 1),
        ("htb", 1),
        ("pwn", 1),
    ]
    assert report.uniqueness.unique == 3

    payload = flag_intel_report_payload(report)
    assert set(payload) == {
        "total",
        "high_confidence",
        "medium_confidence",
        "low_confidence",
        "weak_flags",
        "categories",
        "uniqueness",
    }
    assert payload["weak_flags"] == ["flag{abc}"]


def test_flag_hit_rows_and_screening_are_pure(vault: Vault) -> None:
    hits = vault.collected_flags()
    rows = flag_assessment_rows(hits)
    assert len(rows) == len(hits)
    assert all(row.node_id > 0 for row in rows)
    assert all(item.ok for item in screen_vault_flags(vault))
