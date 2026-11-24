"""CWE and framework mapping metadata for the finding studio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redscribe.v3.findings.models import CweMapping, FindingMappings

_CATALOG: tuple[CweMapping, ...] = (
    CweMapping(
        cwe_id="CWE-22",
        name="Improper Limitation of a Pathname to a Restricted Directory",
        category="Path Traversal",
        description=(
            "The product uses external input to construct a pathname outside a "
            "restricted directory."
        ),
        owasp=("A01:2021",),
        capec=("CAPEC-126",),
        mitigations=(
            "Use allowlisted canonical paths",
            "Resolve and verify paths before opening files",
        ),
        references=("https://cwe.mitre.org/data/definitions/22.html",),
    ),
    CweMapping(
        cwe_id="CWE-79",
        name="Improper Neutralization of Input During Web Page Generation",
        category="Cross-site Scripting",
        description=(
            "The product does not neutralize user-controlled input before placing it "
            "into a web page."
        ),
        owasp=("A03:2021",),
        capec=("CAPEC-63", "CAPEC-91"),
        mitigations=(
            "Context-aware output encoding",
            "Apply a strict Content-Security-Policy",
        ),
        references=("https://cwe.mitre.org/data/definitions/79.html",),
    ),
    CweMapping(
        cwe_id="CWE-89",
        name="Improper Neutralization of Special Elements in SQL Commands",
        category="SQL Injection",
        description="The product builds SQL commands from untrusted input without neutralization.",
        owasp=("A03:2021",),
        capec=("CAPEC-66",),
        mitigations=("Use parameterized queries", "Apply least-privilege database accounts"),
        references=("https://cwe.mitre.org/data/definitions/89.html",),
    ),
    CweMapping(
        cwe_id="CWE-287",
        name="Improper Authentication",
        category="Authentication",
        description="The product does not correctly verify that an actor is who they claim to be.",
        owasp=("A07:2021",),
        capec=("CAPEC-151",),
        mitigations=("Enforce server-side authentication", "Rotate default credentials"),
        references=("https://cwe.mitre.org/data/definitions/287.html",),
    ),
    CweMapping(
        cwe_id="CWE-306",
        name="Missing Authentication for Critical Function",
        category="Authentication",
        description="The product does not require authentication for a critical function.",
        owasp=("A07:2021",),
        capec=("CAPEC-62",),
        mitigations=("Require authentication on every privileged endpoint", "Deny by default"),
        references=("https://cwe.mitre.org/data/definitions/306.html",),
    ),
    CweMapping(
        cwe_id="CWE-352",
        name="Cross-Site Request Forgery",
        category="Session Security",
        description=(
            "The product does not verify that a state-changing request originated "
            "from a trusted page."
        ),
        owasp=("A01:2021",),
        capec=("CAPEC-62",),
        mitigations=("Use synchronizer tokens", "Set SameSite cookies"),
        references=("https://cwe.mitre.org/data/definitions/352.html",),
    ),
    CweMapping(
        cwe_id="CWE-434",
        name="Unrestricted Upload of File with Dangerous Type",
        category="File Handling",
        description=(
            "The product allows an attacker to upload a file that can be executed "
            "by the target system."
        ),
        owasp=("A04:2021",),
        capec=("CAPEC-1",),
        mitigations=("Validate content type and extension", "Store uploads outside the web root"),
        references=("https://cwe.mitre.org/data/definitions/434.html",),
    ),
    CweMapping(
        cwe_id="CWE-502",
        name="Deserialization of Untrusted Data",
        category="Data Handling",
        description="The product deserializes untrusted data without validating it.",
        owasp=("A08:2021",),
        capec=("CAPEC-586",),
        mitigations=("Avoid native deserializers", "Use signed, schema-validated formats"),
        references=("https://cwe.mitre.org/data/definitions/502.html",),
    ),
    CweMapping(
        cwe_id="CWE-798",
        name="Use of Hard-coded Credentials",
        category="Credential Management",
        description=(
            "The product contains hard-coded credentials used for authentication or encryption."
        ),
        owasp=("A07:2021",),
        capec=("CAPEC-191",),
        mitigations=("Move secrets to a vault", "Rotate exposed credentials"),
        references=("https://cwe.mitre.org/data/definitions/798.html",),
    ),
    CweMapping(
        cwe_id="CWE-918",
        name="Server-Side Request Forgery",
        category="Request Forgery",
        description=(
            "The product fetches a remote resource using attacker-controlled input "
            "without validation."
        ),
        owasp=("A10:2021",),
        capec=("CAPEC-664",),
        mitigations=("Allowlist destinations", "Block link-local and metadata addresses"),
        references=("https://cwe.mitre.org/data/definitions/918.html",),
    ),
)

_BY_ID = {entry.cwe_id: entry for entry in _CATALOG}


class MappingError(ValueError):
    """Raised when mapping metadata is malformed."""


@dataclass(frozen=True, slots=True)
class MappingResolution:
    """A CWE lookup result with catalog match status."""

    cwe_id: str
    entry: CweMapping | None
    known: bool

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "cwe_id": self.cwe_id,
            "known": self.known,
            "entry": self.entry.as_dict() if self.entry else None,
        }


def cwe_catalog() -> tuple[CweMapping, ...]:
    """Return the full built-in CWE catalog."""
    return _CATALOG


def lookup_cwe(cwe_id: str) -> MappingResolution:
    """Look up a CWE by identifier."""
    normalized = cwe_id.strip().upper()
    return MappingResolution(
        cwe_id=normalized,
        entry=_BY_ID.get(normalized),
        known=normalized in _BY_ID,
    )


def search_cwe(query: str, *, category: str = "") -> tuple[CweMapping, ...]:
    """Search CWE identifiers, names, categories, and mitigations."""
    needle = query.strip().casefold()
    facet = category.strip().casefold()
    return tuple(
        entry
        for entry in _CATALOG
        if (not facet or facet in entry.category.casefold())
        and (
            not needle
            or needle in entry.cwe_id.casefold()
            or needle in entry.name.casefold()
            or needle in entry.category.casefold()
            or any(needle in item.casefold() for item in entry.mitigations)
        )
    )


def resolve_mappings(findings_mappings: FindingMappings) -> tuple[MappingResolution, ...]:
    """Resolve every CWE attached to a finding."""
    return tuple(lookup_cwe(cwe_id) for cwe_id in findings_mappings.cwes)


def mapping_report(findings_mappings: FindingMappings) -> dict[str, Any]:
    """Return a UI-ready mapping report."""
    resolutions = resolve_mappings(findings_mappings)
    mitigations: list[str] = []
    owasp: list[str] = list(findings_mappings.owasp)
    for resolution in resolutions:
        if resolution.entry is None:
            continue
        for item in resolution.entry.mitigations:
            if item not in mitigations:
                mitigations.append(item)
        for item in resolution.entry.owasp:
            if item not in owasp:
                owasp.append(item)
    return {
        "cwes": list(findings_mappings.cwes),
        "cves": list(findings_mappings.cves),
        "owasp": owasp,
        "mitre_attack": list(findings_mappings.mitre_attack),
        "known_count": sum(1 for item in resolutions if item.known),
        "unknown": [item.cwe_id for item in resolutions if not item.known],
        "mitigations": mitigations,
        "resolutions": [item.as_dict() for item in resolutions],
    }


def validate_mappings(findings_mappings: FindingMappings) -> tuple[str, ...]:
    """Return mapping validation issues for a finding draft."""
    issues: list[str] = []
    if not findings_mappings.cwes:
        issues.append("no CWE assigned")
    for cwe_id in findings_mappings.cwes:
        if lookup_cwe(cwe_id).entry is None:
            issues.append(f"unknown CWE: {cwe_id}")
    for cve_id in findings_mappings.cves:
        if len(cve_id) < 9:
            issues.append(f"malformed CVE: {cve_id}")
    return tuple(issues)
