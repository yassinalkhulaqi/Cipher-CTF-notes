"""Tests for deterministic pagination and line estimation."""

from __future__ import annotations

import pytest

from redscribe.v3.report_designer.model import FindingItem, LayoutDocument, LayoutSection
from redscribe.v3.report_designer.pagination import (
    PaginationEngine,
    estimate_finding_lines,
    estimate_section_lines,
    ordered_sections,
    wrapped_lines,
)
from redscribe.v3.report_designer.themes import ReportTheme, ThemeTokens


def test_wrapped_lines() -> None:
    assert wrapped_lines("", 20) == 0
    assert wrapped_lines("short", 20) == 1
    assert wrapped_lines("a" * 21, 20) == 2
    assert wrapped_lines("one\ntwo\nthree", 20) == 3
    with pytest.raises(ValueError):
        wrapped_lines("x", 0)


def test_estimate_heights(finding: FindingItem) -> None:
    assert estimate_finding_lines(finding, 80) > 2
    section = LayoutSection(key="s", title="S", body="x" * 100, findings=(finding,))
    assert estimate_section_lines(section, 80) > estimate_section_lines(
        LayoutSection(key="e", title="E"), 80
    )
    assert estimate_section_lines(section, 20) > estimate_section_lines(section, 80)


def test_ordered_sections() -> None:
    second = LayoutSection(key="b", title="B", order=2)
    first = LayoutSection(key="a", title="A", order=1)
    child = LayoutSection(key="a-child", title="A child", order=9)
    first = first.with_children((child,))
    assert tuple(item.key for item in ordered_sections((second, first))) == (
        "a",
        "a-child",
        "b",
    )


def test_pagination_plan(section: LayoutSection, finding: FindingItem) -> None:
    sections = (
        section,
        LayoutSection(key="findings", title="Findings", order=10, findings=(finding,)),
    )
    document = LayoutDocument(key="doc", title="Report", sections=sections)
    theme = ReportTheme(key="t", name="T", tokens=ThemeTokens(lines_per_page=20))
    plan = PaginationEngine().paginate(document, theme)
    assert plan.total_pages >= 1
    assert plan.document_key == "doc"
    assert plan.theme == "t"
    assert plan.lines_per_page == 20
    assert plan.anchors["sec-overview"] >= 1
    assert plan.finding_pages[finding.key] >= 1
    assert plan.page_for_anchor("sec-scope") == plan.page_for_anchor("sec-overview")
    assert plan.page_for_anchor("missing") is None
    assert plan.page_for_finding("missing") is None
    assert plan.label_for(1) == f"Page 1 of {plan.total_pages}"
    assert plan.digest() == plan.digest()


def test_forced_page_breaks() -> None:
    a = LayoutSection(key="a", title="A", order=1, body="first")
    cover = LayoutSection(key="cover", title="Cover", kind="cover", order=2)
    b = LayoutSection(key="b", title="B", order=3, body="last")
    document = LayoutDocument(key="doc", title="Doc", sections=(a, cover, b))
    theme = ReportTheme(key="t", name="T", tokens=ThemeTokens(lines_per_page=40))
    plan = PaginationEngine().paginate(document, theme)
    assert plan.total_pages == 2
    assert plan.anchors["sec-a"] == 1
    assert plan.anchors["sec-cover"] == 2
    assert plan.anchors["sec-b"] == 2
    assert plan.pages[1].forced_break is True


def test_explicit_page_break_and_continuation() -> None:
    huge = LayoutSection(key="huge", title="Huge", body=("line of text\n" * 300))
    forced = LayoutSection(key="forced", title="Forced", order=2, page_break_before=True)
    document = LayoutDocument(key="doc", title="Doc", sections=(huge, forced))
    theme = ReportTheme(key="t", name="T", tokens=ThemeTokens(lines_per_page=25))
    plan = PaginationEngine().paginate(document, theme)
    assert plan.total_pages >= 14
    huge_items = [item for page in plan.pages for item in page.items if item.section_key == "huge"]
    assert len(huge_items) > 1
    assert any(item.continued for item in huge_items)
    assert sum(item.lines for item in huge_items) == estimate_section_lines(huge, 92)
    assert plan.anchors["sec-huge"] == 1
    assert plan.anchors["sec-forced"] == plan.total_pages
    assert all(page.used_lines <= page.capacity for page in plan.pages)
    assert PaginationEngine().paginate(document, theme).digest() == plan.digest()


def test_empty_document_has_one_page() -> None:
    document = LayoutDocument(key="empty", title="Empty")
    theme = ReportTheme(key="t", name="T")
    plan = PaginationEngine().paginate(document, theme)
    assert plan.total_pages == 1
    assert plan.pages[0].items == ()
    assert plan.anchors == {}
