"""Persistence adapters and export manifests for v4 report layouts.

The store is in-memory and SQLite-ready: it owns identity, ordering and
secondary indexes, and all snapshots are plain dicts suitable for JSON. No
adapter performs I/O or executes user-supplied data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from redscribe.v4.pagination import paginate, weak_etag
from redscribe.v4.report_designer.types import (
    ExportFormat,
    Orientation,
    PageSize,
    ReportLayout,
    ReportSection,
    SectionKind,
    clean_text,
    text_of,
)


class StoreError(ValueError):
    """Raised for missing layouts or inconsistent persisted data."""


@dataclass(frozen=True, slots=True)
class LayoutStats:
    """A deterministic summary of the layout collection."""

    layouts: int
    sections: int
    entries: int
    themes: int
    page_sizes: int

    def to_dict(self) -> dict[str, int]:
        return {
            "layouts": self.layouts,
            "sections": self.sections,
            "entries": self.entries,
            "themes": self.themes,
            "page_sizes": self.page_sizes,
        }


@dataclass(frozen=True, slots=True)
class ExportManifestEntry:
    """One exported artifact recorded in a manifest."""

    layout_id: str
    format: str
    checksum: str
    page_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout_id": self.layout_id,
            "format": self.format,
            "checksum": self.checksum,
            "page_count": self.page_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExportManifestEntry:
        return cls(
            layout_id=clean_text(data.get("layout_id", ""), "layout_id", 80, False),
            format=ExportFormat.parse(text_of(data.get("format"))).value,
            checksum=clean_text(data.get("checksum", ""), "checksum", 64),
            page_count=int(data.get("page_count", 0)),
        )


@dataclass(frozen=True, slots=True)
class ExportManifest:
    """A signed-by-content inventory of rendered report artifacts."""

    id: str
    entries: tuple[ExportManifestEntry, ...] = ()
    generated_at: str = ""
    version: int = 1

    def __post_init__(self) -> None:
        if not self.id:
            raise StoreError("manifest id must not be empty")
        if self.version < 1:
            raise StoreError("manifest version must be >= 1")

    @property
    def digest(self) -> str:
        canonical = "|".join(
            f"{entry.layout_id}:{entry.format}:{entry.checksum}:{entry.page_count}"
            for entry in sorted(
                self.entries,
                key=lambda item: (item.layout_id, item.format, item.checksum),
            )
        )
        return weak_etag(canonical)

    def formats(self) -> tuple[str, ...]:
        return tuple(sorted({entry.format for entry in self.entries}))

    def layout_ids(self) -> tuple[str, ...]:
        return tuple(sorted({entry.layout_id for entry in self.entries}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "generated_at": self.generated_at,
            "digest": self.digest,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExportManifest:
        raw_entries = data.get("entries", ())
        if not isinstance(raw_entries, Sequence):
            raise StoreError("manifest entries must be a sequence")
        entries = tuple(
            ExportManifestEntry.from_dict(item)
            if isinstance(item, Mapping)
            else ExportManifestEntry.from_dict({})
            for item in raw_entries
        )
        return cls(
            id=clean_text(data.get("id", ""), "manifest id", 80, False),
            entries=entries,
            generated_at=text_of(data.get("generated_at")),
            version=int(data.get("version", 1)),
        )


class LayoutStore:
    """CRUD store with theme, format and section-kind indexes."""

    SCHEMA_VERSION = 2

    def __init__(self, id_factory: Any = None) -> None:
        self._layouts: dict[str, ReportLayout] = {}
        self._by_theme: dict[str, set[str]] = {}
        self._by_size: dict[PageSize, set[str]] = {}
        self._by_kind: dict[SectionKind, set[str]] = {}
        self._by_orientation: dict[Orientation, set[str]] = {}
        self._id_factory = id_factory or (lambda: "layout-generated")

    def put(self, layout: ReportLayout) -> ReportLayout:
        """Insert or replace a layout and refresh all secondary indexes."""
        if not layout.id:
            raise StoreError("layout id must not be empty")
        existing = self._layouts.get(layout.id)
        if existing is not None:
            self._unindex(existing)
        self._layouts[layout.id] = layout
        theme_key = layout.theme.casefold()
        self._by_theme.setdefault(theme_key, set()).add(layout.id)
        self._by_size.setdefault(layout.page_size, set()).add(layout.id)
        self._by_orientation.setdefault(layout.orientation, set()).add(layout.id)
        for kind in set(layout.section_kinds):
            self._by_kind.setdefault(kind, set()).add(layout.id)
        return layout

    def create(
        self,
        title: str,
        theme: str = "classic",
        page_size: PageSize = PageSize.A4,
        orientation: Orientation = Orientation.PORTRAIT,
        sections: Sequence[ReportSection] = (),
    ) -> ReportLayout:
        """Create a layout with an injected deterministic identifier."""
        generated = str(self._id_factory())
        if not generated:
            raise StoreError("id factory returned an empty identifier")
        return self.put(
            ReportLayout(
                id=generated,
                title=title,
                theme=theme,
                page_size=page_size,
                orientation=orientation,
                sections=tuple(sections),
            )
        )

    def get(self, layout_id: str) -> ReportLayout | None:
        return self._layouts.get(layout_id)

    def require(self, layout_id: str) -> ReportLayout:
        layout = self._layouts.get(layout_id)
        if layout is None:
            raise StoreError(f"unknown layout: {layout_id}")
        return layout

    def update(self, layout_id: str, changes: Mapping[str, Any]) -> ReportLayout:
        """Apply validated field changes to an existing layout."""
        current = self.require(layout_id)
        allowed = {
            "title",
            "subtitle",
            "theme",
            "page_size",
            "orientation",
            "sections",
            "created_at",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise StoreError(f"unsupported layout fields: {sorted(unknown)}")
        overrides: dict[str, Any] = {key: value for key, value in changes.items() if key in allowed}
        if "id" in changes and str(changes["id"]) != layout_id:
            raise StoreError("layout id is immutable")
        candidate = ReportLayout.from_dict({**current.to_dict(), **overrides})
        if candidate.id != layout_id:
            raise StoreError("layout id is immutable")
        return self.put(candidate)

    def delete(self, layout_id: str) -> ReportLayout:
        layout = self.require(layout_id)
        self._unindex(layout)
        del self._layouts[layout_id]
        return layout

    def clone(self, layout_id: str, new_id: str, title: str | None = None) -> ReportLayout:
        """Copy a layout under a new identifier without sharing mutable state."""
        source = self.require(layout_id)
        return self.put(
            replace(
                source,
                id=new_id,
                title=title or f"{source.title} (copy)",
                sections=tuple(source.sections),
            )
        )

    def _unindex(self, layout: ReportLayout) -> None:
        theme_key = layout.theme.casefold()
        theme_ids = self._by_theme.get(theme_key)
        if theme_ids is not None:
            theme_ids.discard(layout.id)
            if not theme_ids:
                del self._by_theme[theme_key]
        size_ids = self._by_size.get(layout.page_size)
        if size_ids is not None:
            size_ids.discard(layout.id)
            if not size_ids:
                del self._by_size[layout.page_size]
        orientation_ids = self._by_orientation.get(layout.orientation)
        if orientation_ids is not None:
            orientation_ids.discard(layout.id)
            if not orientation_ids:
                del self._by_orientation[layout.orientation]
        for kind in set(layout.section_kinds):
            kind_ids = self._by_kind.get(kind)
            if kind_ids is not None:
                kind_ids.discard(layout.id)
                if not kind_ids:
                    del self._by_kind[kind]

    def all(self) -> tuple[ReportLayout, ...]:
        return tuple(self._layouts[layout_id] for layout_id in sorted(self._layouts))

    def by_theme(self, theme: str) -> tuple[ReportLayout, ...]:
        ids = self._by_theme.get(theme.strip().casefold(), set())
        return tuple(self._layouts[item] for item in sorted(ids))

    def by_page_size(self, size: PageSize) -> tuple[ReportLayout, ...]:
        ids = self._by_size.get(size, set())
        return tuple(self._layouts[item] for item in sorted(ids))

    def by_orientation(self, orientation: Orientation) -> tuple[ReportLayout, ...]:
        ids = self._by_orientation.get(orientation, set())
        return tuple(self._layouts[item] for item in sorted(ids))

    def by_section_kind(self, kind: SectionKind) -> tuple[ReportLayout, ...]:
        ids = self._by_kind.get(kind, set())
        return tuple(self._layouts[item] for item in sorted(ids))

    def theme_index(self) -> dict[str, int]:
        """Return layout counts per theme, sorted by theme name."""
        return {theme: len(ids) for theme, ids in sorted(self._by_theme.items())}

    def stats(self) -> LayoutStats:
        layouts = self.all()
        return LayoutStats(
            layouts=len(layouts),
            sections=sum(len(layout.sections) for layout in layouts),
            entries=sum(layout.entry_count for layout in layouts),
            themes=len(self._by_theme),
            page_sizes=len(self._by_size),
        )

    def snapshot(self) -> tuple[dict[str, Any], ...]:
        """Export every layout as a plain-data snapshot."""
        return tuple(layout.to_dict() for layout in self.all())

    def restore(self, snapshot: Iterable[Mapping[str, Any]]) -> int:
        """Replace the collection with a validated snapshot, returning its size."""
        restored = tuple(ReportLayout.from_dict(item) for item in snapshot)
        ids = {layout.id for layout in restored}
        if len(ids) != len(restored):
            raise StoreError("snapshot contains duplicate layout ids")
        self._layouts.clear()
        self._by_theme.clear()
        self._by_size.clear()
        self._by_kind.clear()
        self._by_orientation.clear()
        for layout in restored:
            self.put(layout)
        return len(restored)

    def build_manifest(
        self,
        manifests: Iterable[tuple[str, ExportFormat, str, int]],
        manifest_id: str,
        generated_at: str = "",
    ) -> ExportManifest:
        """Record rendered artifacts in a deterministic export manifest."""
        entries = tuple(
            ExportManifestEntry(
                layout_id=self.require(layout_id).id,
                format=fmt.value,
                checksum=checksum,
                page_count=page_count,
            )
            for layout_id, fmt, checksum, page_count in manifests
        )
        return ExportManifest(id=manifest_id, entries=entries, generated_at=generated_at)

    def page(self, page: int = 1, page_size: int = 50) -> Any:
        """Return one page of layouts using the v4 pagination helper."""
        return paginate(self.all(), page, page_size)


__all__ = [
    "ExportManifest",
    "ExportManifestEntry",
    "LayoutStats",
    "LayoutStore",
    "StoreError",
]
