from __future__ import annotations

import pytest

from redscribe.domain.models import Node
from redscribe.storage.db import Vault
from redscribe.v2.reporting.evidence import (
    command_evidence,
    deduplicate_evidence,
    evidence_citations,
    evidence_digest,
    evidence_for_finding,
    evidence_from_note,
    evidence_from_notes,
    evidence_missing,
    evidence_signature,
    evidence_stats,
    excerpt,
    group_evidence_by_kind,
    sort_evidence,
    with_excerpts,
)
from redscribe.v2.reporting.inclusion import (
    all_rule_tags,
    apply_inclusion,
    confidence_for,
    default_rules,
    evidence_rules,
    filter_by_confidence,
    inclusion_decision,
    normalize_rules,
    notes_to_finding_evidence,
    open_only,
    rule_digest,
    rule_matches,
    rule_matches_finding,
    rule_summary,
    rules_for_config,
    select_notes,
    severity_threshold,
    sort_selected,
)
from redscribe.v2.reporting.models import (
    EvidenceRef,
    Finding,
    InclusionRule,
    RedactionRule,
    ReportConfig,
    ReportSection,
    SeverityCounts,
    SourceNote,
)
from redscribe.v2.reporting.redaction import (
    builtin_redactions,
    compile_rule,
    merge_rules,
    preview_redaction,
    redact_evidence,
    redact_finding,
    redact_section,
    redact_text,
    redaction_summary,
    rule_names,
    sorted_rules,
)
from redscribe.v2.reporting.redaction import (
    rule_digest as redaction_rule_digest,
)
from redscribe.v2.reporting.sections import (
    assign_unique_identifiers,
    clone_section_tree,
    find_section,
    findings_in_sections,
    flatten_sections,
    insert_section,
    move_section,
    remove_section,
    renumber_sections,
    reorder_sections,
    section_by_order,
    section_index,
    section_path,
    section_stats,
    section_titles,
    sections_with_findings,
    update_section,
)
from redscribe.v2.reporting.serialization import (
    config_from_json,
    config_to_json,
    parse_config,
    parse_evidence,
    parse_finding,
    parse_format,
    parse_redaction,
    parse_rule,
    parse_section,
    summary_of_config,
)
from redscribe.v2.reporting.severity import (
    at_least,
    counts_from_values,
    filter_minimum_severity,
    format_count_line,
    merge_counts,
    risk_level,
    severity_bar,
    severity_counts_from_pairs,
    severity_distribution,
    severity_index,
    severity_label,
    severity_summary,
    severity_table,
    severity_totals,
    sort_findings,
)
from redscribe.v2.reporting.source import (
    OPEN_STATUSES,
    SEVERITY_TAGS,
    build_source,
    note_to_source,
    source_by_title,
    source_digest,
    source_paths,
    source_tags,
)
from redscribe.v2.reporting.templates import (
    TEMPLATES,
    clone_template_sections,
    find_template_by_tag,
    get_template,
    section_kinds,
    template_digest,
    template_keys,
    template_summaries,
)
from redscribe.v2.reporting.validation import (
    has_errors,
    issues_as_dicts,
    validate_config,
    validate_format,
    validate_section_tree,
)


def note(identifier: int = 1, **changes: object) -> SourceNote:
    values: dict[str, object] = {
        "identifier": identifier,
        "title": f"Note {identifier}",
        "path": "labs / target",
        "content": "Short body with enough text to be useful.",
        "tags": ("web", "critical"),
        "status": "active",
        "severity": "critical",
        "category": "web",
        "target": "app.test",
        "flag": "flag{demo1234}",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    values.update(changes)
    return SourceNote(**values)


def finding(identifier: str = "f-1", severity: str = "high") -> Finding:
    return Finding(
        identifier=identifier,
        title=f"Finding {identifier}",
        severity=severity,
        evidence=(EvidenceRef(identifier=f"ev-{identifier}", title="Evidence", content="body"),),
        confidence=0.8,
    )


def section(identifier: str = "root", **changes: object) -> ReportSection:
    values: dict[str, object] = {
        "identifier": identifier,
        "title": identifier.replace("-", " ").title(),
    }
    values.update(changes)
    return ReportSection(**values)


def test_source_helpers_and_snapshot(vault: Vault) -> None:
    vault.create_node(
        "Critical note",
        content="flag{demo1234} admin@example.test",
        tags="critical, web",
        target="app.test",
        status="active",
        flag="flag{demo1234}",
    )
    folder = vault.create_node("Archive", kind="folder")
    vault.create_node(
        "Old note",
        folder.id,
        content="quiet text",
        tags="low",
        status="done",
    )
    snapshot = build_source(vault, generated_at="2026-01-01T00:00:00Z")
    assert len(snapshot.notes) == 2
    assert snapshot.generated_at == "2026-01-01T00:00:00Z"
    assert snapshot.schema_version > 0
    assert source_digest(snapshot) == snapshot.digest()
    assert "web" in source_tags(snapshot)
    assert "Archive" in source_paths(snapshot)
    assert source_by_title(snapshot, "critical note") is not None
    assert source_by_title(snapshot, "missing") is None
    assert "critical" in SEVERITY_TAGS
    assert OPEN_STATUSES == ("todo", "active")


def test_source_filters_and_root_scope(vault: Vault) -> None:
    root = vault.create_node("Scope", kind="folder")
    vault.create_node("In scope", root.id, tags="web", status="active")
    vault.create_node("Out scope", tags="web", status="active")
    tagged = build_source(vault, tag="web")
    assert len(tagged.notes) == 2
    scoped = build_source(vault, root_id=root.id)
    assert [item.title for item in scoped.notes] == ["In scope"]
    assert build_source(vault, status="done").notes == ()
    with pytest.raises(ValueError):
        build_source(vault, root_id=999)


def test_note_to_source_from_domain_node(vault: Vault) -> None:
    node = Node(
        id=7,
        parent_id=None,
        title="Node",
        kind="note",
        content="api_key: abcdef123456",
        tags="high, secret",
        target="host.test",
        status="todo",
        difficulty="",
        flag="",
        pinned=False,
        sort_order=0,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-02T00:00:00Z",
    )
    converted = note_to_source(node, vault)
    assert converted.identifier == 7
    assert converted.severity == "high"
    assert converted.sensitive is True
    assert converted.category == ""
    assert converted.tags == ("high", "secret")


def test_inclusion_rule_matching_and_decisions() -> None:
    item = note()
    web_rule = InclusionRule("web", "include", tags=("web",))
    blocked_rule = InclusionRule("blocked", "exclude", statuses=("blocked",))
    assert rule_matches(web_rule, item)
    assert rule_matches_finding(web_rule, item)
    assert not rule_matches(blocked_rule, item)
    assert inclusion_decision(item, (web_rule,)) == (True, "web")
    assert inclusion_decision(item, (blocked_rule, web_rule)) == (True, "web")
    assert inclusion_decision(item, ()) == (True, "default")
    assert normalize_rules((web_rule, blocked_rule, web_rule)) == (web_rule, blocked_rule)


def test_inclusion_selection_and_confidence() -> None:
    items = (note(1), note(2, tags=("secret",)), note(3, status="blocked"))
    rules = (InclusionRule("only-web", "include", tags=("web",), statuses=("active",)),)
    selected = select_notes(items, rules)
    assert [item.identifier for item in selected] == [1]
    assert select_notes(items, (), tags=("missing",)) == ()
    assert select_notes(items, (), statuses=("active",))[0].identifier == 1
    assert [item.identifier for item in open_only(items)] == [1, 2]
    assert len(filter_by_confidence(items, 0.9)) == 3
    assert filter_by_confidence((note(9, flag=""),), 0.9) == ()
    assert confidence_for(items[0]) == 1.0
    assert severity_threshold(items[0], "high") is True
    assert sort_selected(items)[0].identifier == 1
    assert all_rule_tags(rules) == ("web",)
    assert evidence_rules()[0].name == "evidence-notes"
    assert rule_summary(rules)["includes"] == 1
    assert rule_digest(rules) == rule_digest((rules[0],))
    assert len(notes_to_finding_evidence(items)) == 3


def test_apply_inclusion_uses_config_filters() -> None:
    items = (note(1), note(2, tags=("secret",)), note(3, severity="low"))
    config = ReportConfig(title="Report", minimum_severity="high")
    selected = apply_inclusion(items, config)
    assert [item.identifier for item in selected] == [1]
    assert len(rules_for_config(config)) == len(default_rules())
    custom = ReportConfig(
        title="Report",
        rules=(InclusionRule("all", "include", severities=("info", "low", "high", "critical")),),
    )
    assert len(apply_inclusion(items, custom)) == 3


def test_evidence_helpers() -> None:
    item = note(4)
    evidence_item = evidence_from_note(item, locator="§ 3")
    assert evidence_item.identifier == "note-4"
    assert evidence_item.locator == "§ 3"
    assert evidence_item.sensitive is False
    assert evidence_from_notes((item,)) == (evidence_from_note(item),)
    assert evidence_digest(evidence_item) == evidence_digest(evidence_item)
    assert evidence_signature((evidence_item,)) == evidence_signature((evidence_item,))
    assert deduplicate_evidence((evidence_item, evidence_item)) == (evidence_item,)
    assert evidence_for_finding(finding())[0].identifier == "ev-f-1"
    assert evidence_citations((evidence_item,)) == ("[1] Note 4 (§ 3)",)
    assert evidence_missing((EvidenceRef("empty", "Empty", ""),)) == ("empty",)
    assert evidence_stats((finding(),))["evidence"] == 1
    assert set(group_evidence_by_kind((evidence_item,))) == {"note"}


def test_excerpt_and_command_evidence() -> None:
    text = "# Heading\n\n$ nmap -sV 127.0.0.1\n```\nignored\n```\nbody text\n"
    assert excerpt(text) == "Heading $ nmap -sV 127.0.0.1 body text"
    assert excerpt("x" * 100, width=24).endswith("…")
    with pytest.raises(ValueError):
        excerpt("body", width=10)
    log = command_evidence("$ whoami\n# id\nplain", title="Commands")
    assert log.kind == "command"
    assert log.title == "Commands"
    assert "whoami" in log.content
    assert "id" in log.content


def test_evidence_sorting_and_excerpt_filling() -> None:
    note_item = EvidenceRef("n", "Note", "body", kind="note", source_path="b")
    command_item = EvidenceRef("c", "Command", "$ id", kind="command", source_path="a")
    assert [item.identifier for item in sort_evidence((note_item, command_item))] == ["n", "c"]
    item = Finding("f", "Finding", evidence=(EvidenceRef("e", "Evidence", "line one\nline two"),))
    updated = with_excerpts(item)
    assert updated.evidence[0].excerpt == "line one line two"
    assert item.evidence[0].excerpt == ""


def test_redaction_rules_and_text() -> None:
    rules = builtin_redactions(include_hosts=True)
    assert [rule.name for rule in rules][-1] == "host"
    assert [rule.name for rule in sorted_rules(rules)] == [
        "private-key",
        "api-secret",
        "email",
        "flag",
        "ipv4",
        "host",
    ]
    result = redact_text(
        "flag{demo1234} admin@example.com api_key: abcdef123456 host.test",
        rules,
    )
    assert "[FLAG]" in result.text
    assert "[EMAIL]" in result.text
    assert "[SECRET]" in result.text
    assert "[HOST]" in result.text
    assert set(result.applied) == {"flag", "email", "api-secret", "host"}
    assert result.counts["email"] == 1
    assert compile_rule(RedactionRule("case", "abc")).search("ABC") is not None


def test_redaction_preview_and_summaries() -> None:
    rules = builtin_redactions()
    spans = preview_redaction("flag{demo1234}", rules, context=2)
    assert spans[0]["rule"] == "flag"
    assert spans[0]["matched"] == "flag{demo1234}"
    assert spans[0]["before"] == ""
    with pytest.raises(ValueError):
        preview_redaction("text", rules, context=-1)
    with pytest.raises(ValueError):
        preview_redaction("text", rules, max_spans=0)
    summary = redaction_summary(rules, "admin@example.com")
    assert summary["applied"] == ["email"]
    assert summary["matches"] == 1
    assert summary["rule_count"] == len(rules)


def test_redaction_of_finding_evidence_and_section() -> None:
    rules = (RedactionRule("name", "Root", "[ROLE]"), RedactionRule("mail", "@", "[AT]"))
    item = EvidenceRef("e", "Root output", "admin@example.com", source_path="root")
    assert redact_evidence(item, rules).title == "[ROLE] output"
    assert "[AT]" in redact_evidence(item, rules).content
    report_finding = Finding("f", "Root access", evidence=(item,))
    redacted = redact_finding(report_finding, rules)
    assert redacted.title == "[ROLE] access"
    assert redacted.evidence[0].content == "admin[AT]example.com"
    tree = ReportSection("s", "Root section", body="Root text")
    assert redact_section(tree, rules).title == "[ROLE] section"
    assert redact_section(tree, rules).body == "[ROLE] text"
    assert rule_names(rules) == ("mail", "name")
    assert redaction_rule_digest(rules) == redaction_rule_digest((rules[1], rules[0]))


def test_merge_rules_overrides_by_name() -> None:
    first = RedactionRule("a", "one", priority=1)
    second = RedactionRule("a", "two", priority=2)
    third = RedactionRule("b", "three", priority=3)
    merged = merge_rules((first, third), (second,))
    assert len(merged) == 2
    assert merged[0].pattern == "two"
    assert [rule.name for rule in merged] == ["a", "b"]


def test_severity_helpers() -> None:
    findings = (finding("a", "critical"), finding("b", "low"), finding("c", "medium"))
    counts = SeverityCounts(critical=1, low=1, medium=1)
    assert severity_totals(findings) == counts.as_dict()
    assert severity_index("high") == 3
    assert at_least("critical", "medium") is True
    assert at_least("low", "high") is False
    assert [item.identifier for item in filter_minimum_severity(findings, "medium")] == ["a", "c"]
    assert [item.identifier for item in sort_findings(findings)] == ["a", "c", "b"]
    assert severity_summary(counts)["highest"] == "critical"
    assert severity_summary(counts)["risk_level"] == "critical"
    assert risk_level(SeverityCounts(low=1)) == "low"
    assert risk_level(SeverityCounts()) == "informational"
    assert len(severity_bar(counts)) == 20
    assert set(severity_bar(SeverityCounts()).strip(".")) == set()
    assert severity_table(counts).endswith("| **Total** | 3 |")
    assert format_count_line("Low", 2) == "| Low | 2 |"
    assert severity_label("severe") == "Critical"


def test_severity_count_builders() -> None:
    left = SeverityCounts(info=1, high=1)
    right = SeverityCounts(low=2, high=1)
    merged = merge_counts(left, right)
    assert merged.as_dict()["high"] == 2
    assert merged.as_dict()["low"] == 2
    assert counts_from_values({"low": 3, "unknown": 9}).low == 3
    assert severity_counts_from_pairs((("high", 1), ("high", 2))).high == 2
    assert severity_distribution((finding("a", "high"), finding("b", "high")))["high"] == 2
    with pytest.raises(ValueError):
        severity_bar(SeverityCounts(), width=3)


def test_serialization_parsers() -> None:
    parsed_evidence = parse_evidence(
        {"identifier": "e", "kind": "artifact", "content": "body", "source_id": 4}
    )
    assert parsed_evidence.kind == "artifact"
    assert parsed_evidence.source_id == 4
    parsed_finding = parse_finding(
        {
            "identifier": "f",
            "title": "Finding",
            "severity": "high",
            "status": "open",
            "confidence": 0.5,
        }
    )
    assert parsed_finding.severity == "high"
    assert parsed_finding.confidence == 0.5
    parsed_section = parse_section(
        {"identifier": "s", "title": "Section", "level": 2, "metadata": {"a": "b"}}
    )
    assert parsed_section.metadata == {"a": "b"}
    assert parsed_section.level == 2
    parsed_rule = parse_rule({"name": "r", "action": "exclude", "statuses": "blocked"})
    assert parsed_rule.statuses == ("blocked",)
    parsed_redaction = parse_redaction({"name": "r", "pattern": "secret"})
    assert parsed_redaction.scope == "all"
    assert parse_format(" MARKDOWN ") == "markdown"
    assert parse_format("HTML") == "html"


def test_serialization_rejects_bad_payloads() -> None:
    bad_payloads = (
        lambda: parse_evidence({"identifier": "e", "kind": "unknown"}),
        lambda: parse_finding({"identifier": "f", "title": "F", "status": "later"}),
        lambda: parse_finding({"identifier": "f", "title": "F", "severity": "unknown"}),
        lambda: parse_section({"identifier": "s", "title": "S", "level": "two"}),
        lambda: parse_rule({"name": "r", "action": "maybe"}),
        lambda: parse_redaction({"name": "r", "pattern": ""}),
        lambda: parse_format("pdf"),
    )
    for call in bad_payloads:
        with pytest.raises(ValueError):
            call()


def test_parse_config_defaults_and_json_roundtrip() -> None:
    config = parse_config({"title": "Report", "template": "ctf", "statuses": "todo,active"})
    assert config.template == "ctf"
    assert config.statuses == ("todo", "active")
    assert config.print_profile == "compact"
    assert len(config.sections) > 0
    assert config.include_evidence is True
    encoded = config_to_json(config)
    assert config_from_json(encoded) == config
    assert summary_of_config(config)["title"] == "Report"
    assert summary_of_config(config)["sections"] > 0


def test_validation_reports_expected_issues() -> None:
    clean = ReportConfig(title="Report", sections=(section("s"),))
    assert validate_config(clean) == ()
    assert has_errors(validate_config(clean)) is False
    invalid = ReportConfig(
        title="",
        template="",
        classification="unknown",
        minimum_severity="catastrophic",
        page_size="tabloid",
        orientation="diagonal",
        findings=(
            Finding("Bad ID", "Title", severity="high", status="open", confidence=0.1),
            finding("dupe"),
            finding("dupe"),
        ),
        rules=(InclusionRule("r", "include"), InclusionRule("r", "include")),
        redactions=(RedactionRule("bad", "["), RedactionRule("bad", "ok")),
    )
    issues = validate_config(invalid)
    codes = {issue.code for issue in issues}
    assert "title_required" in codes
    assert "template_required" in codes
    assert "classification_invalid" in codes
    assert "severity_invalid" in codes
    assert "page_size_invalid" in codes
    assert "orientation_invalid" in codes
    assert "finding_id_invalid" in codes
    assert "finding_id_duplicate" in codes
    assert "rule_empty" in codes
    assert "rule_name_duplicate" in codes
    assert "redaction_pattern_invalid" in codes
    assert "redaction_name_duplicate" in codes
    assert has_errors(issues) is True
    assert issues_as_dicts(issues)[0]["code"]


def test_section_validation_and_format_validation() -> None:
    issues = validate_section_tree((section("Bad ID", title="Title"),))
    assert {issue.code for issue in issues} == {"section_id_invalid"}
    assert validate_section_tree((section("ok"),)) == ()
    duplicates = validate_section_tree((section("same"), section("same")))
    assert {issue.code for issue in duplicates} == {"section_id_duplicate"}
    assert validate_format(" Markdown ") == "markdown"
    with pytest.raises(ValueError):
        validate_format("pdf")


def test_section_tree_operations() -> None:
    child = section("child", title="Child", level=2)
    other = section("other", title="Other", level=2)
    root = section("root", title="Root", children=(child,))
    assert [item.identifier for item in flatten_sections((root,))] == ["root", "child"]
    assert section_index((root,))["child"].title == "Child"
    assert find_section((root,), "missing") is None
    assert [item.identifier for item in section_path((root,), "child")] == ["root", "child"]
    assert section_path((root,), "missing") == ()
    updated = update_section((root,), "child", title="Renamed")
    assert find_section(updated, "child").title == "Renamed"
    assert len(insert_section((root,), other, parent_id="root", index=0)[0].children) == 2
    assert len(insert_section((root,), other)[1].identifier) > 0
    assert find_section(remove_section((root,), "child"), "child") is None
    moved = move_section((root, other), "other", parent_id="root", index=0)
    assert [item.identifier for item in find_section(moved, "root").children] == ["other", "child"]
    with pytest.raises(ValueError):
        move_section((root,), "root", parent_id="child", index=0)
    with pytest.raises(ValueError):
        move_section((root,), "missing", parent_id="", index=0)


def test_section_ordering_renumbering_and_stats() -> None:
    children = (section("a", level=2), section("b", level=2), section("c", level=2))
    root = section("root", children=children)
    reordered = reorder_sections((root,), "root", ("c", "a"))
    assert [item.identifier for item in reordered[0].children] == ["c", "a", "b"]
    renumbered = renumber_sections((root,))
    assert [item.order for item in renumbered[0].children] == [2, 3, 4]
    assert [item.level for item in renumbered[0].children] == [2, 2, 2]
    clone = clone_section_tree((root,))
    assert clone == (root,)
    assert clone[0] is not root
    stats = section_stats((root,))
    assert stats["sections"] == 4
    assert stats["roots"] == 1
    duplicates = (section("first", title="Same"), section("second", title="Same"))
    assert [item.identifier for item in assign_unique_identifiers(duplicates)] == [
        "same",
        "same-2",
    ]
    assert section_titles((root,)) == ("Root", "  A", "  B", "  C")
    assert section_by_order(flatten_sections(renumbered), 4).identifier == "c"
    with_findings = section("find", findings=(finding(),))
    assert sections_with_findings((with_findings,)) == (with_findings,)
    assert findings_in_sections((with_findings,))[0].identifier == "f-1"


def test_template_registry_helpers() -> None:
    keys = template_keys()
    assert "engagement" in keys
    assert "ctf" in keys
    assert len(TEMPLATES) == len(keys)
    assert get_template("PENTEST").key == "pentest"
    assert find_template_by_tag("ctf")[0].key == "ctf"
    assert len(template_summaries()) == len(keys)
    assert all("print_profile" in item for item in template_summaries())
    assert "text" in section_kinds()
    assert len(clone_template_sections("engagement")) > 0
    assert len(template_digest("engagement")) == 64
    with pytest.raises(ValueError):
        get_template("missing")
