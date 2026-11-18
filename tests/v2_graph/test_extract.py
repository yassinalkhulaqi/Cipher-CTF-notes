from __future__ import annotations

from redscribe.v2.graph.extract import (
    extract_frontmatter,
    extract_frontmatter_tags,
    extract_inline_tags,
    extract_tags,
    extract_wikilinks,
    link_snippet,
    mask_protected_spans,
    normalize_reference,
    parse_wikilink,
    reference_index,
)


def test_normalize_reference_handles_headings_and_aliases() -> None:
    assert normalize_reference("  HTB Corporate  ") == "htb-corporate"
    assert normalize_reference("Path/To Note#Heading") == "path-to-note"
    assert normalize_reference("Back\\Slash") == "back-slash"
    assert normalize_reference("") == ""


def test_parse_wikilink_splits_target_alias_and_heading() -> None:
    assert parse_wikilink("Target") == ("Target", "", "")
    assert parse_wikilink("Target|Alias") == ("Target", "Alias", "")
    assert parse_wikilink(" Target #Heading | Label ") == ("Target", "Label", "Heading")


def test_extract_wikilinks_returns_reading_order_and_metadata() -> None:
    content = "First [[Alpha]] then [[Beta|the other]] and [[Gamma#Section]]."
    links = extract_wikilinks(content)
    assert [item.target for item in links] == ["Alpha", "Beta", "Gamma"]
    assert [item.display for item in links] == ["Alpha", "the other", "Gamma"]
    assert links[0].start == content.index("[[Alpha]]")
    assert links[0].end == links[0].start + len("[[Alpha]]")
    assert all(item.line == 1 for item in links)
    assert links[0].key == "alpha"
    assert links[2].heading == "Section"
    assert links[0].as_dict()["key"] == "alpha"


def test_extract_wikilinks_ignores_escapes_and_duplicates() -> None:
    links = extract_wikilinks("\\[[Escaped]] and [[Alpha]] twice [[Alpha]]")
    assert len(links) == 1
    assert links[0].target == "Alpha"


def test_mask_protected_spans_preserves_offsets() -> None:
    content = "[[Alpha]]\n```\n[[Beta]]\n```\n`[[Gamma]]`\n[[Delta]]"
    masked = mask_protected_spans(content)
    assert len(masked) == len(content)
    assert "[[Alpha]]" in masked
    assert "[[Beta]]" not in masked
    assert "[[Gamma]]" not in masked
    assert "[[Delta]]" in masked
    assert masked.count("\n") == content.count("\n")


def test_extract_wikilinks_skips_code_fences_and_inline_code() -> None:
    content = "[[Alpha]]\n```md\n[[Beta]]\n```\n`[[Gamma]]`\n[[Delta]]"
    links = extract_wikilinks(content)
    assert [item.target for item in links] == ["Alpha", "Delta"]
    assert links[1].line == 6


def test_extract_inline_tags_ignores_headings_and_code() -> None:
    content = "# Heading\nBody #web and #WEB again.\n`#code` and #recon/sub.\n## #ignored"
    tags = extract_inline_tags(content)
    assert [item.value for item in tags] == ["web", "recon/sub"]
    assert all(item.source == "inline" for item in tags)
    assert tags[0].as_dict()["value"] == "web"


def test_extract_frontmatter_scalars_and_tags() -> None:
    content = "---\ntitle: Example\ntags: [web, recon]\nstatus: done\n# comment: ignored\n---\nBody"
    fields = extract_frontmatter(content)
    assert fields["title"] == "Example"
    assert fields["tags"] == "[web, recon]"
    assert fields["status"] == "done"
    assert "comment" not in fields
    tags = extract_frontmatter_tags(content)
    assert [item.value for item in tags] == ["web", "recon"]
    assert all(item.source == "frontmatter" for item in tags)


def test_extract_frontmatter_tags_supports_comma_and_space_lists() -> None:
    content = "---\ntag: '#alpha, beta; gamma delta'\n---\n"
    tags = extract_frontmatter_tags(content)
    assert [item.value for item in tags] == ["alpha", "beta", "gamma", "delta"]


def test_extract_frontmatter_handles_missing_or_malformed_blocks() -> None:
    assert extract_frontmatter("plain body") == {}
    assert extract_frontmatter_tags("plain body") == ()
    assert extract_frontmatter("---\nnot a field\n---\nbody") == {}
    assert extract_frontmatter_tags("---\ntags:\n---\n") == ()


def test_extract_tags_deduplicates_across_sources() -> None:
    content = "---\ntags: [web, front]\n---\nBody #WEB and #inline."
    tags = extract_tags(content, stored="stored, #web")
    assert [item.value for item in tags] == ["stored", "web", "front", "inline"]
    assert [item.source for item in tags] == [
        "stored",
        "frontmatter",
        "frontmatter",
        "inline",
    ]


def test_extract_empty_content_returns_empty_tuples() -> None:
    assert extract_wikilinks("") == ()
    assert extract_inline_tags("") == ()
    assert extract_tags("") == ()
    assert link_snippet("", 0, 1) == ""


def test_link_snippet_trims_and_bounds_text() -> None:
    content = "before [[Alpha|Alias]] after"
    start = content.index("[[")
    end = content.index("]]") + 2
    snippet = link_snippet(content, start, end, width=12)
    assert "Alpha" in snippet
    assert "[[" not in snippet
    assert "]]" not in snippet
    long = "x" * 500 + "[[Target]]" + "y" * 500
    start = long.index("[[")
    end = start + len("[[Target]]")
    compact = link_snippet(long, start, end, width=80)
    assert len(compact) <= 181
    assert compact.startswith("…")
    assert compact.endswith("…")


def test_link_snippet_rejects_small_width() -> None:
    assert link_snippet("content", 0, 4, width=4) == ""


def test_reference_index_keeps_first_id_for_each_key() -> None:
    index = reference_index([(1, "Alpha"), (2, "alpha"), (3, "Beta Note")])
    assert index == {"alpha": 1, "beta-note": 3}


def test_extract_wikilinks_handles_multiline_targets_only_when_valid() -> None:
    content = "[[Alpha]]\n[[Beta\nGamma]]\n[[Delta]]"
    links = extract_wikilinks(content)
    assert [item.target for item in links] == ["Alpha", "Delta"]


def test_inline_tags_ignore_numbers_and_slashes_at_start() -> None:
    content = "#abc #123 hash/tag #nested/tag"
    tags = extract_inline_tags(content)
    assert [item.value for item in tags] == ["abc", "nested/tag"]


def test_frontmatter_tags_ignore_empty_tokens() -> None:
    content = "---\ntags: '#one,,  ,#two'\n---\n"
    assert [item.value for item in extract_frontmatter_tags(content)] == ["one", "two"]


def test_tag_occurrence_keys_are_case_folded() -> None:
    tags = extract_inline_tags("#Web #web #WEB")
    assert len(tags) == 1
    assert tags[0].key == "web"


def test_mask_protected_spans_handles_tildes() -> None:
    content = "~~~python\n[[Hidden]]\n~~~\n[[Shown]]"
    masked = mask_protected_spans(content)
    assert "[[Hidden]]" not in masked
    assert "[[Shown]]" in masked


def test_extract_wikilinks_dedupe_includes_alias() -> None:
    links = extract_wikilinks("[[Alpha]] [[Alpha|Alias]] [[Alpha]]")
    assert [item.display for item in links] == ["Alpha", "Alias"]


def test_link_occurrence_positions_are_stable() -> None:
    content = "start [[Alpha]] middle [[Beta|label]] end"
    links = extract_wikilinks(content)
    for item in links:
        assert content[item.start : item.end].startswith("[[")
    assert links[1].alias == "label"


def test_inline_tag_positions_point_at_tag_value() -> None:
    content = "text #web more"
    tags = extract_inline_tags(content)
    assert len(tags) == 1
    assert content[tags[0].start - 1] == "#"
    assert content[tags[0].start : tags[0].end] == "web"


def test_normalize_reference_strips_only_first_heading() -> None:
    assert normalize_reference("Note#One#Two") == "note"


def test_extract_tags_does_not_mutate_input() -> None:
    content = "# Heading\n#web"
    original = content[:]
    extract_tags(content)
    assert content == original


def test_frontmatter_keyword_fallback() -> None:
    content = "---\nkeywords: alpha, beta\n---\n"
    assert [item.value for item in extract_frontmatter_tags(content)] == ["alpha", "beta"]


def test_empty_frontmatter_tag_field() -> None:
    content = "---\ntags: []\n---\n"
    assert extract_frontmatter_tags(content) == ()


def test_extract_wikilinks_keeps_alias_with_heading() -> None:
    links = extract_wikilinks("[[Note#Heading|Alias]]")
    assert len(links) == 1
    assert links[0].target == "Note"
    assert links[0].heading == "Heading"
    assert links[0].display == "Alias"


def test_reference_index_is_empty_for_empty_input() -> None:
    assert reference_index([]) == {}


def test_mask_protected_spans_handles_empty_input() -> None:
    assert mask_protected_spans("") == ""
