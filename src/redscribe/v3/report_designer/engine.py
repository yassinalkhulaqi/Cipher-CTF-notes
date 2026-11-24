"""Report design engine that ties selection, layout, pagination, and render together."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from redscribe.v3.report_designer.builders import (
    AppendixBuilder,
    CoverBuilder,
    TocBuilder,
    TocEntry,
)
from redscribe.v3.report_designer.identifiers import digest, slugify
from redscribe.v3.report_designer.model import (
    FindingItem,
    LayoutDocument,
    LayoutSection,
    RedactionRule,
    SectionKind,
    SelectionRule,
)
from redscribe.v3.report_designer.pagination import PaginationEngine, PaginationPlan
from redscribe.v3.report_designer.redaction import (
    RedactionPreview,
    apply_redactions,
    preview_document,
)
from redscribe.v3.report_designer.redaction import (
    rule_digest as redaction_rule_digest,
)
from redscribe.v3.report_designer.renderers.base import (
    RENDER_FORMATS,
    RenderContext,
    RenderFormat,
    RenderOutput,
)
from redscribe.v3.report_designer.renderers.registry import RendererRegistry
from redscribe.v3.report_designer.selection import SelectionPolicy, SelectionResult
from redscribe.v3.report_designer.themes import ReportTheme, ThemeRegistry

MAX_TOC_PASSES = 6


@dataclass(frozen=True, slots=True)
class DesignSpec:
    """All user-controlled inputs required to produce one report design."""

    key: str
    title: str
    subtitle: str = ""
    client: str = ""
    author: str = ""
    classification: str = "internal"
    generated_at: str = ""
    theme: str = "client"
    sections: tuple[LayoutSection, ...] = ()
    findings: tuple[FindingItem, ...] = ()
    rules: tuple[SelectionRule, ...] = ()
    redactions: tuple[RedactionRule, ...] = ()
    minimum_severity: str = "info"
    statuses: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    require_evidence: bool = False
    include_sensitive_evidence: bool = False
    formats: tuple[RenderFormat, ...] = RENDER_FORMATS
    options: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Design key cannot be blank")
        if not self.title.strip():
            raise ValueError("Design title cannot be blank")
        for output_format in self.formats:
            if output_format not in RENDER_FORMATS:
                raise ValueError(f"Unknown render format: {output_format}")

    @property
    def policy(self) -> SelectionPolicy:
        """Build the selection policy encoded by this spec."""
        return SelectionPolicy(
            rules=self.rules,
            minimum_severity=self.minimum_severity,
            statuses=self.statuses,
            tags=self.tags,
            require_evidence=self.require_evidence,
            include_sensitive_evidence=self.include_sensitive_evidence,
        )

    def option(self, name: str, default: bool) -> bool:
        """Read a boolean design option."""
        return bool(self.options.get(name, default))

    def fingerprint(self) -> str:
        """Stable digest of every build-affecting input."""
        return digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "key": self.key,
            "title": self.title,
            "subtitle": self.subtitle,
            "client": self.client,
            "author": self.author,
            "classification": self.classification,
            "generated_at": self.generated_at,
            "theme": self.theme,
            "sections": [section.as_dict() for section in self.sections],
            "findings": [item.as_dict() for item in self.findings],
            "rules": [rule.as_dict() for rule in self.rules],
            "redactions": [rule.as_dict() for rule in self.redactions],
            "minimum_severity": self.minimum_severity,
            "statuses": list(self.statuses),
            "tags": list(self.tags),
            "require_evidence": self.require_evidence,
            "include_sensitive_evidence": self.include_sensitive_evidence,
            "formats": list(self.formats),
            "options": dict(sorted(self.options.items())),
        }


@dataclass(frozen=True, slots=True)
class DesignResult:
    """Everything produced by one report design run."""

    spec: DesignSpec
    document: LayoutDocument
    selection: SelectionResult
    theme: ReportTheme
    plan: PaginationPlan
    entries: tuple[TocEntry, ...]
    preview: RedactionPreview
    outputs: tuple[RenderOutput, ...]
    manifest: dict[str, Any]

    @property
    def design_digest(self) -> str:
        """Digest of the full design result."""
        return str(self.manifest["design_digest"])

    def output(self, output_format: RenderFormat) -> RenderOutput | None:
        """Return a rendered output by format."""
        return next((item for item in self.outputs if item.format == output_format), None)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation, omitting rendered bodies."""
        return {
            "spec": self.spec.as_dict(),
            "document": self.document.as_dict(),
            "selection": self.selection.as_dict(),
            "theme": self.theme.as_dict(),
            "pagination": self.plan.as_dict(),
            "toc": [entry.as_dict() for entry in self.entries],
            "redaction_preview": self.preview.as_dict(),
            "outputs": [item.as_dict() for item in self.outputs],
            "manifest": dict(self.manifest),
        }


class ReportDesignerEngine:
    """Build deterministic, client-ready report designs."""

    def __init__(
        self,
        themes: ThemeRegistry | None = None,
        renderers: RendererRegistry | None = None,
        paginator: PaginationEngine | None = None,
    ) -> None:
        self.themes = themes or ThemeRegistry()
        self.renderers = renderers or RendererRegistry()
        self.paginator = paginator or PaginationEngine()

    def _resolve_theme(self, key: str, registry: ThemeRegistry | None = None) -> ReportTheme:
        """Resolve a theme key, using the first registered theme as fallback."""
        registry = registry or self.themes
        if registry.has(key):
            return registry.get(key)
        themes = registry.list()
        if not themes:
            raise ValueError("No report themes are registered")
        return themes[0]

    def _build_document(self, spec: DesignSpec, selection: SelectionResult) -> LayoutDocument:
        """Build the authored portion of the design tree."""
        sections = list(spec.sections)
        if selection.included and spec.option("findings_section", True):
            sections.append(
                LayoutSection(
                    key="findings",
                    title="Findings",
                    kind=SectionKind.FINDINGS,
                    level=1,
                    order=100,
                    findings=selection.included,
                )
            )
        sections.sort(key=lambda section: (section.order, section.key))
        return LayoutDocument(
            key=spec.key,
            title=spec.title,
            subtitle=spec.subtitle,
            client=spec.client,
            author=spec.author,
            classification=spec.classification,
            generated_at=spec.generated_at,
            theme=spec.theme,
            sections=tuple(sections),
            metadata={
                "selection_digest": selection.digest(),
                "source": "v3-report-designer",
            },
        )

    def _assemble(
        self,
        base: LayoutDocument,
        theme: ReportTheme,
        spec: DesignSpec,
    ) -> tuple[LayoutDocument, PaginationPlan, tuple[TocEntry, ...]]:
        """Insert generated front/back matter and stabilize TOC page numbers."""
        cover: tuple[LayoutSection, ...] = ()
        if spec.option("cover", True):
            cover = (CoverBuilder().build(base, theme),)
        appendices = (
            AppendixBuilder().build_all(base, theme) if spec.option("appendix", True) else ()
        )
        authored = base.sections
        candidate = base.with_sections((*cover, *authored, *appendices))
        plan = self.paginator.paginate(candidate, theme)
        if not spec.option("toc", True):
            return candidate, plan, ()
        toc, entries = TocBuilder().build(candidate, plan, theme)
        candidate = base.with_sections((*cover, toc, *authored, *appendices))
        for _ in range(MAX_TOC_PASSES):
            plan = self.paginator.paginate(candidate, theme)
            toc, entries = TocBuilder().build(candidate, plan, theme)
            current = candidate.sections[len(cover)]
            if toc.body == current.body and toc.summary == current.summary:
                candidate = base.with_sections((*cover, toc, *authored, *appendices))
                plan = self.paginator.paginate(candidate, theme)
                return candidate, plan, entries
            candidate = base.with_sections((*cover, toc, *authored, *appendices))
        plan = self.paginator.paginate(candidate, theme)
        _, entries = TocBuilder().build(candidate, plan, theme)
        return candidate, plan, entries

    def _manifest(
        self,
        spec: DesignSpec,
        theme: ReportTheme,
        selection: SelectionResult,
        preview: RedactionPreview,
        plan: PaginationPlan,
        document: LayoutDocument,
    ) -> dict[str, Any]:
        """Build reproducibility metadata for one design."""
        canonical_spec = replace(spec, formats=RENDER_FORMATS)
        parts = {
            "spec_digest": canonical_spec.fingerprint(),
            "theme_digest": theme.digest(),
            "selection_digest": selection.digest(),
            "redaction_digest": redaction_rule_digest(spec.redactions),
            "pagination_digest": plan.digest(),
            "document_digest": document.fingerprint(),
            "redaction_matches": preview.total_matches,
            "formats": list(spec.formats),
        }
        canonical_parts = {**parts, "formats": list(RENDER_FORMATS)}
        parts["design_digest"] = digest(canonical_parts)
        return parts

    def design(
        self,
        spec: DesignSpec,
        *,
        themes: ThemeRegistry | None = None,
        renderers: RendererRegistry | None = None,
    ) -> DesignResult:
        """Execute the full design pipeline for ``spec``."""
        renderer_registry = renderers or self.renderers
        if not renderer_registry.formats():
            raise ValueError("No report renderers are registered")
        theme = self._resolve_theme(spec.theme, themes)
        selection = spec.policy.select(spec.findings)
        base = self._build_document(spec, selection)
        preview = preview_document(base, spec.redactions)
        document = apply_redactions(base, spec.redactions) if spec.option("redact", True) else base
        final_document, plan, entries = self._assemble(document, theme, spec)
        manifest = self._manifest(spec, theme, selection, preview, plan, final_document)
        context = RenderContext(
            document=final_document,
            theme=theme,
            plan=plan,
            entries=entries,
            manifest=manifest,
            options=dict(spec.options),
        )
        outputs = tuple(
            renderer_registry.render(output_format, context) for output_format in spec.formats
        )
        return DesignResult(
            spec=spec,
            document=final_document,
            selection=selection,
            theme=theme,
            plan=plan,
            entries=entries,
            preview=preview,
            outputs=outputs,
            manifest=manifest,
        )

    def render_one(self, spec: DesignSpec, output_format: RenderFormat) -> RenderOutput:
        """Design and return a single output format."""
        if output_format not in spec.formats:
            spec = replace(spec, formats=(output_format,))
        result = self.design(spec)
        output = result.output(output_format)
        if output is None:
            raise ValueError(f"Renderer did not produce {output_format}")
        return output

    def manifest_for(self, spec: DesignSpec) -> dict[str, Any]:
        """Return the manifest for a spec without rendering outputs."""
        return self.design(replace(spec, formats=("json",))).manifest


def default_engine(
    themes: ThemeRegistry | None = None,
    renderers: RendererRegistry | None = None,
) -> ReportDesignerEngine:
    """Return an engine wired with all built-in themes and renderers."""
    from redscribe.v3.report_designer.renderers import default_registry as make_renderers
    from redscribe.v3.report_designer.themes import default_theme_registry as make_themes

    return ReportDesignerEngine(
        themes=themes or make_themes(),
        renderers=renderers or make_renderers(),
    )


def design_key(title: str, *, prefix: str = "report") -> str:
    """Derive a stable design key from a title."""
    return slugify(title, fallback=prefix)
