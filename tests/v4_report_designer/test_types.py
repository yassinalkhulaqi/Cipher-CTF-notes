"""Tests for report designer data contracts and validation."""

from __future__ import annotations

import pytest

from redscribe.v4.report_designer.types import (
    ExportFormat,
    Orientation,
    PageSize,
    PaginatedPage,
    ReportEntry,
    ReportLayout,
    ReportSection,
    ReportTheme,
    ResolvedTheme,
    SectionKind,
    ThemeColors,
    ThemeFonts,
    ThemeMargins,
    bool_field,
    clean_text,
    float_field,
    hex_color,
    int_field,
    string_tuple,
    text_of,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a4", PageSize.A4),
        (" A4 ", PageSize.A4),
        ("LETTER", PageSize.LETTER),
        ("a5", PageSize.A5),
    ],
)
def test_page_size_parse(value: str, expected: PageSize) -> None:
    assert PageSize.parse(value) is expected


def test_page_size_dimensions_and_labels() -> None:
    assert PageSize.A4.dimensions_mm == (210, 297)
    assert PageSize.LETTER.dimensions_mm == (216, 279)
    assert PageSize.A5.dimensions_mm == (148, 210)
    assert PageSize.A4.label == "A4"
    with pytest.raises(ValueError, match="unknown page size"):
        PageSize.parse("a3")


def test_orientation_apply_swaps_dimensions() -> None:
    assert Orientation.PORTRAIT.apply(PageSize.A4) == (210, 297)
    assert Orientation.LANDSCAPE.apply(PageSize.A4) == (297, 210)
    assert Orientation.LANDSCAPE.is_landscape is True
    assert Orientation.parse(" Portrait ").value == "portrait"
    with pytest.raises(ValueError, match="unknown orientation"):
        Orientation.parse("diagonal")


def test_section_kind_order_and_labels() -> None:
    assert [kind.order for kind in SectionKind] == [0, 1, 2, 3, 4]
    assert SectionKind.TOC.label == "Table of contents"
    assert SectionKind.parse("Findings") is SectionKind.FINDINGS
    with pytest.raises(ValueError, match="unknown section kind"):
        SectionKind.parse("summary")


def test_export_format_properties() -> None:
    assert ExportFormat.HTML.extension == ".html"
    assert ExportFormat.MARKDOWN.extension == ".md"
    assert ExportFormat.HTML.mime_type == "text/html"
    assert ExportFormat.parse("md") is ExportFormat.MARKDOWN
    assert ExportFormat.parse(" MARKDOWN ") is ExportFormat.MARKDOWN
    with pytest.raises(ValueError, match="unknown export format"):
        ExportFormat.parse("pdf")


def test_clean_text_rejects_non_strings_and_oversize() -> None:
    assert clean_text("  hello  ", "value") == "hello"
    assert text_of(19) == ""
    with pytest.raises(ValueError, match="value must be a string"):
        clean_text(19, "value")
    with pytest.raises(ValueError, match="value must not be empty"):
        clean_text("   ", "value", allow_empty=False)
    with pytest.raises(ValueError, match="value exceeds 3 characters"):
        clean_text("abcd", "value", limit=3)


def test_bounded_field_helpers() -> None:
    assert int_field(None, "count", 0, 10, 3) == 3
    assert int_field(7, "count", 0, 10, 3) == 7
    assert float_field(4.5, "ratio", 0.0, 5.0, 1.0) == 4.5
    assert bool_field(None, "flag", True) is True
    assert bool_field(False, "flag", True) is False
    with pytest.raises(ValueError, match="count must be an integer"):
        int_field(True, "count", 0, 10, 3)
    with pytest.raises(ValueError, match="count must be between"):
        int_field(11, "count", 0, 10, 3)
    with pytest.raises(ValueError, match="ratio must be a number"):
        float_field("wide", "ratio", 0.0, 5.0, 1.0)
    with pytest.raises(ValueError, match="flag must be a boolean"):
        bool_field(1, "flag")


def test_string_tuple_validation() -> None:
    assert string_tuple(None, "items") == ()
    assert string_tuple([" a ", "b"], "items") == ("a", "b")
    with pytest.raises(ValueError, match="items must be a sequence"):
        string_tuple("abc", "items")
    with pytest.raises(ValueError, match="items exceeds 1 items"):
        string_tuple(["a", "b"], "items", limit=1)
    with pytest.raises(ValueError, match="items\\[0\\] must be a string"):
        string_tuple([1], "items")


def test_hex_color_validation() -> None:
    assert hex_color("#FFAA00", "primary") == "#ffaa00"
    with pytest.raises(ValueError, match="primary must be a #RRGGBB color"):
        hex_color("red", "primary")
    with pytest.raises(ValueError, match="primary must be a #RRGGBB color"):
        hex_color("#12345", "primary")


def test_theme_patches_merge_and_round_trip() -> None:
    base = ThemeColors(primary="#111111", text="#222222")
    patch = ThemeColors(primary="#aaaaaa", accent="#bbbbbb")
    merged = patch.merged(base)
    assert merged.overrides() == {
        "primary": "#aaaaaa",
        "text": "#222222",
        "accent": "#bbbbbb",
    }
    assert ThemeColors.from_dict(patch.to_dict()) == patch
    with pytest.raises(ValueError, match=r"colors\.accent must be a #RRGGBB color"):
        ThemeColors(accent="nope")


def test_theme_fonts_merge_and_validation() -> None:
    base = ThemeFonts(body="Serif", body_size=11.0, line_height=1.5)
    patch = ThemeFonts(body="Sans", line_height=1.8)
    merged = patch.merged(base)
    assert merged.body == "Sans"
    assert merged.body_size == 11.0
    assert merged.line_height == 1.8
    assert ThemeFonts.from_dict(patch.to_dict()) == patch
    with pytest.raises(ValueError, match=r"fonts\.body_size must be between"):
        ThemeFonts(body_size=48.0)
    with pytest.raises(ValueError, match=r"fonts\.heading must not be empty"):
        ThemeFonts(heading="  ")


def test_theme_margins_merge_and_validation() -> None:
    base = ThemeMargins(top=18, right=18, bottom=18, left=18)
    patch = ThemeMargins(top=12, left=14)
    merged = patch.merged(base)
    assert merged.overrides() == {"top": 12, "right": 18, "bottom": 18, "left": 14}
    assert ThemeMargins.from_dict(patch.to_dict()) == patch
    with pytest.raises(ValueError, match=r"margins\.top must be between"):
        ThemeMargins(top=90)


def test_report_theme_round_trip_and_self_inheritance() -> None:
    theme = ReportTheme(
        name="client",
        parent="base",
        colors=ThemeColors(primary="#123456"),
        header="Client",
        description="Branded",
    )
    restored = ReportTheme.from_dict(theme.to_dict())
    assert restored == theme
    assert restored.is_root is False
    with pytest.raises(ValueError, match="cannot inherit from itself"):
        ReportTheme(name="loop", parent="loop")
    with pytest.raises(ValueError, match="theme name must not be empty"):
        ReportTheme.from_dict({"name": ""})
    with pytest.raises(ValueError, match="colors must be an object"):
        ReportTheme.from_dict({"name": "x", "colors": []})


def test_resolved_theme_css_and_page_area() -> None:
    theme = ResolvedTheme(
        name="test",
        colors=ThemeColors(primary="#123456", text="#abcdef"),
        fonts=ThemeFonts(body="Serif"),
        margins=ThemeMargins(top=10, right=20, bottom=10, left=20),
        lineage=("base", "test"),
    )
    assert theme.css_variables() == {
        "--report-primary": "#123456",
        "--report-text": "#abcdef",
    }
    assert theme.page_area_mm(PageSize.A4, Orientation.PORTRAIT) == (170, 277)
    assert theme.to_dict()["lineage"] == ["base", "test"]


def test_report_entry_validation_and_round_trip() -> None:
    entry = ReportEntry(title="Finding", detail="Details", level=2, ref="F-001")
    assert ReportEntry.from_dict(entry.to_dict()) == entry
    with pytest.raises(ValueError, match="entry title must not be empty"):
        ReportEntry(title="")
    with pytest.raises(ValueError, match="entry level must be between"):
        ReportEntry(title="x", level=9)


def test_report_section_defaults_and_round_trip() -> None:
    section = ReportSection(
        kind=SectionKind.TOC,
        entries=(ReportEntry(title="Findings"),),
        page_break_before=True,
    )
    assert section.title == "Table of contents"
    assert section.entry_count == 1
    restored = ReportSection.from_dict(section.to_dict())
    assert restored == section
    with pytest.raises(ValueError, match="page_break_before must be a boolean"):
        ReportSection(kind=SectionKind.COVER, page_break_before=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="sections support at most 250 entries"):
        ReportSection(kind=SectionKind.COVER, entries=(ReportEntry(title="x"),) * 251)
    with pytest.raises(ValueError, match="entries must be a sequence"):
        ReportSection.from_dict({"kind": "cover", "entries": "bad"})


def test_report_layout_validation_derived_fields_and_round_trip() -> None:
    section = ReportSection(kind=SectionKind.COVER, title="Cover")
    layout = ReportLayout(
        id="report.2026-01",
        title="Assessment",
        subtitle="v1",
        theme="client",
        page_size=PageSize.LETTER,
        orientation=Orientation.LANDSCAPE,
        sections=(section,),
        created_at="2026-01-01T00:00:00Z",
    )
    assert layout.section_kinds == (SectionKind.COVER,)
    assert layout.entry_count == 0
    assert layout.page_dimensions_mm == (279, 216)
    assert ReportLayout.from_dict(layout.to_dict()) == layout
    with pytest.raises(ValueError, match="invalid layout id"):
        ReportLayout(id="bad id!", title="x")
    with pytest.raises(ValueError, match="layout title must not be empty"):
        ReportLayout(id="valid.id", title="")
    with pytest.raises(ValueError, match="sections must be a sequence"):
        ReportLayout.from_dict({"id": "x", "title": "y", "sections": 4})
    with pytest.raises(ValueError, match="layouts support at most 32 sections"):
        ReportLayout(id="x", title="y", sections=(section,) * 33)


def test_paginated_page_validation_and_round_trip() -> None:
    page = PaginatedPage(
        number=2,
        section=SectionKind.FINDINGS,
        lines=("alpha", "beta"),
        title="Findings",
    )
    assert page.line_count == 2
    assert PaginatedPage.from_dict(page.to_dict()) == page
    with pytest.raises(ValueError, match="page number must be between"):
        PaginatedPage(number=0, section=SectionKind.COVER, lines=())
    with pytest.raises(ValueError, match="page lines\\[0\\] must be a string"):
        PaginatedPage.from_dict({"number": 1, "section": "cover", "lines": [3]})
