from __future__ import annotations

import pytest

from redscribe.v2.blocks.diff import PatchEntry, PatchOperation, make_patch
from redscribe.v2.blocks.mentions import (
    MentionIndex,
    build_mention_index,
    document_mentions,
    extract_mentions,
    mention_pattern,
    mention_targets,
    refresh_block_mentions,
    render_mention,
    replace_mention_targets,
)
from redscribe.v2.blocks.model import BlockDocument, Mention, make_block, make_document
from redscribe.v2.blocks.search import (
    BlockSearchIndex,
    SearchResult,
    block_from_result,
    build_search_index,
    highlight_terms,
    merge_results,
    query_terms,
    result_to_mapping,
    search_payload,
    snippet_for,
    tokenize,
    word_boundary_count,
)
from redscribe.v2.blocks.types import IssueSeverity, MentionKind
from redscribe.v2.blocks.validation import (
    ValidationReport,
    issues_from_payload,
    validate_block,
    validate_document,
    validate_documents,
    validate_patch,
)


def test_tokenize_and_query_terms_are_stable() -> None:
    assert tokenize("Alpha, BETA alpha_2") == ("alpha", "beta", "alpha_2")
    assert query_terms("beta alpha beta") == ("beta", "alpha")
    assert query_terms("   ") == ()
    assert len(query_terms(" ".join(f"term{index}" for index in range(30)))) == 12


def test_snippet_and_highlights_center_on_first_match() -> None:
    assert snippet_for("short text", ["text"]) == "short text"
    long_text = "prefix " + ("filler " * 20) + "target " + ("tail " * 20)
    snippet = snippet_for(long_text, ["target"], width=40)
    assert "target" in snippet
    assert snippet.startswith("…")
    assert snippet.endswith("…")
    assert "…" in snippet_for(long_text, ["missing"], width=40)
    assert highlight_terms("Alpha beta", ["alpha", "gamma", "beta"]) == ("alpha", "beta")


def test_search_index_add_remove_and_replace() -> None:
    index = BlockSearchIndex()
    first = make_document(
        "doc-1",
        "Notes",
        [
            make_block("paragraph", "alpha beta", block_id="b1"),
            make_block("heading", "gamma", block_id="b2", level=1),
        ],
    )
    second = make_document(
        "doc-2",
        "Other",
        [make_block("paragraph", "alpha delta", block_id="b3")],
    )
    assert index.add(first) == 3
    assert index.add(second) == 2
    assert index.size() == 3
    assert index.document_ids == ("doc-1", "doc-2")
    assert index.vocabulary() == ("alpha", "beta", "delta", "gamma")
    assert index.facets() == {"heading": 1, "paragraph": 2}
    assert index.terms_for("doc-1", "b1") == ("alpha", "beta")
    assert index.terms_for("missing", "b1") == ()
    assert index.replace(first) == 3
    assert index.remove("doc-1") is True
    assert index.remove("doc-1") is False
    assert index.size() == 1
    index.clear()
    assert index.document_ids == ()
    assert index.size() == 0


def test_search_index_ranks_filters_and_paginates() -> None:
    first = make_document(
        "doc-1",
        "Notes",
        [
            make_block("paragraph", "alpha beta", block_id="b1"),
            make_block("heading", "alpha", block_id="b2", level=1),
        ],
    )
    second = make_document(
        "doc-2",
        "Other",
        [make_block("paragraph", "alpha beta delta", block_id="b3")],
    )
    index = build_search_index([first, second])
    all_matches = index.search("alpha beta")
    assert [result.block_id for result in all_matches] == ["b1", "b3"]
    assert all_matches[0].score >= all_matches[1].score
    assert all_matches[0].snippet
    assert set(all_matches[0].highlights) == {"alpha", "beta"}
    assert [result.block_id for result in index.search("alpha beta", match_all=False)] == [
        "b1",
        "b3",
        "b2",
    ]
    assert [result.block_id for result in index.search("alpha", block_types=["heading"])] == ["b2"]
    assert [result.block_id for result in index.search("alpha", document_id="doc-1")] == [
        "b2",
        "b1",
    ]
    assert index.search("alpha", offset=1, limit=1)[0].block_id == "b1"
    assert index.search("") == []
    assert index.reindex([first]) == 1
    assert index.size() == 2


def test_search_payload_and_result_helpers() -> None:
    document = make_document("doc-1", "Notes", [make_block("paragraph", "alpha", block_id="b1")])
    index = build_search_index([document])
    result = index.search("alpha")[0]
    assert isinstance(result, SearchResult)
    assert result.as_dict()["block_id"] == "b1"
    assert result_to_mapping(result) == result.as_dict()
    payload = search_payload([result])
    assert payload["total"] == 1
    assert payload["items"][0]["document_title"] == "Notes"
    merged = merge_results([result], [result])
    assert len(merged) == 1
    other = SearchResult("doc-2", "Two", "b9", "paragraph", 99, "snippet", ())
    assert merge_results([result], [other])[0] is other
    assert block_from_result({"doc-1": document}, result) == document.blocks[0]
    assert block_from_result({}, result) is None
    assert word_boundary_count("alpha beta") > 0


def test_mention_extraction_and_rendering() -> None:
    text = "See @[Vault](note:vault-1) and @[F-7](finding:F-7); ignore @[x](bad:target)."
    mentions = extract_mentions(text, block_id="b1")
    assert [mention.kind for mention in mentions] == [
        MentionKind.NOTE,
        MentionKind.FINDING,
    ]
    assert mentions[0].target == "vault-1"
    assert mentions[0].label == "Vault"
    assert mentions[0].block_id == "b1"
    assert text[mentions[0].start : mentions[0].end] == "@[Vault](note:vault-1)"
    assert mention_pattern().search(text) is not None
    assert render_mention(MentionKind.TAG, "web", "Web") == "@[Web](tag:web)"
    replaced = replace_mention_targets(
        text,
        {(MentionKind.NOTE.value, "vault-1"): "vault-2"},
    )
    assert "@[Vault](note:vault-2)" in replaced
    assert "@[F-7](finding:F-7)" in replaced


def test_refresh_mentions_and_target_lists() -> None:
    text = "@[vault](note:vault-1) @[vault](note:vault-1)"
    block = make_block(
        "paragraph",
        text,
        block_id="b1",
        mentions=extract_mentions(text, block_id="b1"),
    )
    refreshed = refresh_block_mentions(block.with_changes(mentions=()))
    assert len(refreshed.mentions) == 2
    assert mention_targets(refreshed.mentions) == ["vault-1"]
    assert mention_targets(refreshed.mentions, kind=MentionKind.FINDING) == []
    document = make_document("doc-1", blocks=[refreshed])
    assert len(document_mentions(document)) == 2


def test_mention_index_queries_and_suggestions() -> None:
    first_text = "@[vault](note:vault-1)"
    second_text = "@[Vault again](note:vault-1) @[root](target:root)"
    first = make_document(
        "doc-1",
        blocks=[make_block("paragraph", first_text, mentions=extract_mentions(first_text))],
    )
    second = make_document(
        "doc-2",
        blocks=[make_block("paragraph", second_text, mentions=extract_mentions(second_text))],
    )
    index = MentionIndex()
    assert index.add(first) == 1
    assert index.add(second) == 2
    assert index.size() == 2
    hits = index.for_target("VAULT-1")
    assert [hit.document_id for hit in hits] == ["doc-1", "doc-2"]
    assert len(index.for_target("vault-1", kind=MentionKind.NOTE)) == 2
    assert index.for_target("vault-1", kind=MentionKind.TAG) == []
    assert len(index.for_kind(MentionKind.NOTE)) == 2
    assert index.for_kind(MentionKind.TARGET)[0].mention.target == "root"
    assert len(index.all()) == 3
    suggestions = index.suggestions("vault", kind=MentionKind.NOTE)
    assert len(suggestions) == 1
    assert suggestions[0].target == "vault-1"
    assert index.suggestions("vault", kind=MentionKind.TAG) == []
    assert index.replace(first) == 1
    assert index.remove("doc-1") is True
    assert index.remove("doc-1") is False
    index.clear()
    assert index.all() == []
    assert build_mention_index([first, second]).size() == 2


def test_valid_document_and_patch_pass_validation() -> None:
    document = make_document(
        "doc-1",
        "Report",
        [
            make_block("heading", "Report", block_id="b1", level=1),
            make_block("paragraph", "body text", block_id="b2"),
        ],
    )
    report = validate_document(document)
    assert report.ok
    assert not report.has_errors
    assert not report.has_warnings
    assert report.as_dict() == {
        "target": "doc-1",
        "ok": True,
        "errors": 0,
        "warnings": 0,
        "issues": [],
    }
    patch = make_patch(document, [PatchEntry(PatchOperation.DELETE, "b2")])
    patch_report = validate_patch(patch)
    assert patch_report.ok
    assert validate_documents([document])[0].ok


def test_validate_block_detects_structural_errors() -> None:
    cases = [
        (make_block("heading", "", block_id="empty", level=0), "invalid_heading_level"),
        (make_block("code", "run()", block_id="lang", language="bad lang"), "invalid_language"),
        (make_block("list", block_id="no-items"), "empty_list"),
        (
            make_block("list", block_id="tasks", items=["a"], style="tasks", checked=[]),
            "checkbox_mismatch",
        ),
        (
            make_block("table", block_id="table", headers=["A", "B"], rows=[["1"]]),
            "ragged_table",
        ),
        (make_block("image", block_id="image", source="javascript:alert(1)"), "unsafe_source"),
        (make_block("image", block_id="image", source="/x.png"), "missing_alt"),
        (make_block("paragraph", "bad\x00text", block_id="control"), "control_characters"),
    ]
    for block, code in cases:
        report = validate_block(block)
        assert code in {issue.code for issue in report.issues}
        assert report.for_block(block.id)


def test_validate_block_reports_mention_problems() -> None:
    mention = Mention(MentionKind.NOTE, "vault", "Vault", 0, 10, "b1")
    block = make_block("paragraph", "short", block_id="b1", mentions=[mention, mention])
    report = validate_block(block)
    codes = {issue.code for issue in report.issues}
    assert "duplicate_mention" in codes
    assert "mention_offsets" in codes
    assert report.count(IssueSeverity.ERROR) >= 1


def test_validate_document_reports_collection_rules() -> None:
    duplicate = make_block("paragraph", "text", block_id="same")
    document = BlockDocument(
        id="",
        title="x" * 400,
        blocks=(duplicate, duplicate),
    )
    report = validate_document(document)
    codes = {issue.code for issue in report.issues}
    assert {
        "missing_id",
        "title_too_long",
        "duplicate_block_id",
    } <= codes
    assert not document.blocks[0].mentions
    empty = make_document("doc-1", blocks=[]).with_blocks([])
    assert "no_blocks" in {issue.code for issue in validate_document(empty).issues}


def test_validate_patch_reports_missing_payloads() -> None:
    patch = make_patch(
        make_document("doc-1", blocks=[make_block("paragraph", "x", block_id="b1")]),
        [
            PatchEntry(PatchOperation.INSERT, ""),
            PatchEntry(PatchOperation.UPDATE, "b1"),
        ],
        label="bad",
    )
    report = validate_patch(patch)
    codes = {issue.code for issue in report.issues}
    assert "missing_block_id" in codes
    assert "missing_block" in codes
    assert not report.ok


def test_issue_payload_decoding_is_defensive() -> None:
    issues = issues_from_payload(
        {
            "issues": [
                {"severity": "error", "code": "broken", "message": "Bad", "block_id": "b1"},
                {"severity": "unknown", "code": "odd"},
                "not-an-object",
            ]
        }
    )
    assert len(issues) == 2
    assert issues[0].severity is IssueSeverity.ERROR
    assert issues[0].block_id == "b1"
    assert issues[1].severity is IssueSeverity.INFO
    assert ValidationReport("target", issues).target == "target"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("alpha", ("alpha",)),
        ("alpha-beta", ("alpha", "beta")),
        ("", ()),
    ],
)
def test_tokenize_handles_common_separators(text: str, expected: tuple[str, ...]) -> None:
    assert tokenize(text) == expected
