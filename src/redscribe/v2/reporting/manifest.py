"""Reproducibility manifests for generated reports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from redscribe import __version__
from redscribe.v2.reporting.identifiers import canonical_json, digest, digest_text
from redscribe.v2.reporting.models import RenderedReport, ReportConfig, ReportDocument
from redscribe.v2.reporting.print_layout import get_print_profile, profile_digest

MANIFEST_VERSION = "1.0.0"


def input_manifest(
    config: ReportConfig,
    *,
    source_digest: str = "",
    template_digest: str = "",
    rules_digest: str = "",
    redaction_digest: str = "",
    print_digest: str = "",
) -> dict[str, Any]:
    """Describe every input that can change a rendered report."""
    return {
        "config_fingerprint": config.fingerprint(),
        "source_digest": source_digest,
        "template_digest": template_digest,
        "rules_digest": rules_digest,
        "redaction_digest": redaction_digest,
        "print_digest": print_digest or profile_digest(get_print_profile(config.print_profile)),
        "template": config.template,
        "generated_at": config.generated_at,
        "finding_count": config.finding_count(),
    }


def reproducibility_manifest(
    document: ReportDocument,
    *,
    rendered: RenderedReport | None = None,
    template_digest: str = "",
    rules_digest: str = "",
    redaction_digest: str = "",
    print_digest: str = "",
    generator: str = "redscribe-reporting-studio",
) -> dict[str, Any]:
    """Build a complete manifest for a report and an optional render output."""
    inputs = input_manifest(
        document.config,
        source_digest=document.source_digest or source_fallback(document),
        template_digest=template_digest,
        rules_digest=rules_digest,
        redaction_digest=redaction_digest,
        print_digest=print_digest,
    )
    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "generator": generator,
        "generator_version": __version__,
        "report_id": document.identifier,
        "title": document.title,
        "inputs": inputs,
        "outputs": {},
        "warnings": list(document.warnings),
    }
    if rendered is not None:
        manifest["outputs"] = output_manifest(rendered)
        manifest["digest"] = digest(manifest)
    return manifest


def source_fallback(document: ReportDocument) -> str:
    """Return a digest derived from report content when no source is attached."""
    return digest_text(canonical_json(document.as_dict()))


def output_manifest(rendered: RenderedReport) -> dict[str, Any]:
    """Describe one rendered output."""
    return {
        rendered.format: {
            "filename": rendered.filename,
            "mime": rendered.mime,
            "bytes": len(rendered.content.encode("utf-8")),
            "sha256": digest_text(rendered.content),
        }
    }


def merge_manifests(manifests: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge output and warning lists from several render manifests."""
    items = list(manifests)
    if not items:
        return {"manifest_version": MANIFEST_VERSION, "outputs": {}, "warnings": []}
    base = dict(items[0])
    outputs: dict[str, Any] = {}
    warnings: list[str] = []
    for manifest in items:
        outputs.update(dict(manifest.get("outputs", {})))
        warnings.extend(str(value) for value in manifest.get("warnings", []))
    base["outputs"] = outputs
    base["warnings"] = sorted(set(warnings))
    base["digest"] = digest({key: value for key, value in base.items() if key != "digest"})
    return base


def manifest_text(manifest: Mapping[str, Any]) -> str:
    """Render a manifest as stable, human-readable text."""
    lines = [
        f"Manifest version: {manifest.get('manifest_version', MANIFEST_VERSION)}",
        f"Generator: {manifest.get('generator', 'redscribe-reporting-studio')}",
        f"Report: {manifest.get('title', 'untitled')}",
    ]
    inputs = manifest.get("inputs", {})
    if isinstance(inputs, Mapping):
        lines.append("Inputs:")
        for key in sorted(inputs):
            lines.append(f"  {key}: {inputs[key]}")
    outputs = manifest.get("outputs", {})
    if isinstance(outputs, Mapping):
        lines.append("Outputs:")
        for key in sorted(outputs):
            lines.append(f"  {key}: {outputs[key]}")
    return "\n".join(lines) + "\n"


def verify_manifest(manifest: Mapping[str, Any]) -> tuple[bool, str]:
    """Verify that a manifest's stored digest matches its content."""
    expected = manifest.get("digest")
    if not isinstance(expected, str):
        return False, "missing digest"
    content = {key: value for key, value in manifest.items() if key != "digest"}
    actual = digest(content)
    return (actual == expected, actual)


def manifest_fingerprint(manifest: Mapping[str, Any]) -> str:
    """Return a digest of a manifest with any stored digest removed."""
    return digest({key: value for key, value in manifest.items() if key != "digest"})
