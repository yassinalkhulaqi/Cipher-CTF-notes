"""RTL layout metadata and bidirectional helper tests."""

from __future__ import annotations

from redscribe.v3.a11y_refinement.models import SurfaceSpec
from redscribe.v3.a11y_refinement.rtl_layout import (
    MIRRORED_ICONS,
    PANE_REGIONS,
    STATIC_ICONS,
    bidi_report,
    css_variables,
    document_attributes,
    layout_for,
    layout_manifest,
    mirrored_icons,
    order_regions,
    pane_names,
    resolve_direction,
    side_map,
    sides_for,
    surface_direction,
    validate_layout,
)


def test_pane_metadata_covers_all_v3_surfaces() -> None:
    names = pane_names()
    assert len(names) == 12
    assert "a11y-refinement" in names
    assert "command-center" in names
    assert all(region for region in PANE_REGIONS.values())


def test_direction_resolution_and_override() -> None:
    assert resolve_direction("ar") == "rtl"
    assert resolve_direction("fa") == "rtl"
    assert resolve_direction("en") == "ltr"
    assert resolve_direction("en", override="rtl") == "rtl"
    assert resolve_direction("ar", override="auto") == "rtl"


def test_ltr_layout_uses_physical_sides() -> None:
    layout = layout_for("command-center", "en")
    assert layout.direction == "ltr"
    assert layout.sides["start"] == "left"
    assert layout.sides["end"] == "right"
    assert layout.css_class == "v3-rtl-ltr"
    assert layout.mirror_icons == ()
    assert layout.ordered_regions == PANE_REGIONS["command-center"]


def test_rtl_layout_mirrors_panes_and_icons() -> None:
    layout = layout_for("finding-studio", "ar")
    assert layout.direction == "rtl"
    assert layout.sides["start"] == "right"
    assert layout.sides["end"] == "left"
    assert layout.css_class == "v3-rtl-rtl"
    assert "chevron-left" in layout.mirror_icons
    assert layout.ordered_regions == tuple(reversed(PANE_REGIONS["finding-studio"]))


def test_unknown_pane_gets_generic_region() -> None:
    layout = layout_for("future-pane", "en")
    assert layout.ordered_regions == ("content",)
    assert validate_layout(layout)["valid"] is True


def test_css_variables_flip_with_direction() -> None:
    ltr = css_variables("en")
    rtl = css_variables("ar")
    assert ltr["--v3-inline-start"] == "left"
    assert rtl["--v3-inline-start"] == "right"
    assert rtl["--v3-text-align"] == "right"
    assert rtl["--v3-panel-order"] == "rtl"
    assert sides_for("rtl") == {"start": "right", "end": "left", "top": "top", "bottom": "bottom"}


def test_mirrored_icon_lists() -> None:
    assert mirrored_icons("rtl") == MIRRORED_ICONS
    assert mirrored_icons("ltr") == ()
    assert "search" in STATIC_ICONS
    assert "search" not in MIRRORED_ICONS


def test_order_regions_preserves_all_regions() -> None:
    regions = ("a", "b", "c")
    assert order_regions(regions, "ltr") == regions
    assert order_regions(regions, "rtl") == ("c", "b", "a")
    assert set(order_regions(regions, "rtl")) == set(regions)


def test_layout_manifest_includes_every_pane() -> None:
    manifest = layout_manifest("he")
    assert manifest["direction"] == "rtl"
    assert manifest["rtl"] is True
    assert len(manifest["panes"]) == len(pane_names())
    assert manifest["panes"][0]["sides"]["start"] == "right"
    assert manifest["static_icons"]
    subset = layout_manifest("en", panes=["timeline", "sync"])
    assert [item["pane"] for item in subset["panes"]] == ["timeline", "sync"]


def test_bidi_report_flags_mixed_direction_text() -> None:
    report = bidi_report("hello שלום", "he")
    assert report["rtl_locale"] is True
    assert report["direction"] == "rtl"
    assert report["warnings"]
    assert report["logical_left"] == "end"
    assert report["physical_start"] == "right"


def test_layout_validation_detects_broken_metadata() -> None:
    from dataclasses import replace

    layout = layout_for("timeline", "en")
    broken = replace(layout, css_class="unexpected")
    result = validate_layout(broken)
    assert result["valid"] is False
    assert any("class" in problem for problem in result["problems"])


def test_document_attributes_and_surface_direction() -> None:
    attributes = document_attributes("ar", override="rtl")
    assert attributes == {"lang": "ar", "dir": "rtl"}
    spec = SurfaceSpec(name="rtl-surface", label="RTL", locale="ar")
    assert surface_direction(spec) == "rtl"
    assert surface_direction(spec, override="ltr") == "ltr"
    assert side_map(layout_for("x", "ar"))["end"] == "left"
