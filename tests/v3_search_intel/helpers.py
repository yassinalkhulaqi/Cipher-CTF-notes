"""Shared fixtures for search intelligence tests."""

from __future__ import annotations

from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityId, EntityKind, LinkKind
from redscribe.v3.search_intel.service import SearchIntelService


def build_service(*, start: float = 1_700_000_000.0) -> SearchIntelService:
    """Build a deterministic service with a small cross-entity graph."""
    clock = FixedClock(start=start)
    service = SearchIntelService(clock=clock)

    target = service.entities.create(
        EntityKind.TARGET,
        title="Web server 10.0.0.5",
        summary="Primary web target in scope",
        tags=("scope", "web"),
        owner="operator",
        value="web-01",
    )
    note = service.entities.create(
        EntityKind.NOTE,
        title="Recon notes",
        summary="Port 443 open; TLS certificate enumerated",
        tags=("recon", "web"),
        owner="operator",
        value="recon-01",
    )
    finding = service.entities.create(
        EntityKind.FINDING,
        title="TLS misconfiguration",
        summary="Weak cipher suites accepted on the web server",
        tags=("web", "high"),
        owner="operator",
        value="finding-01",
        metadata={"severity": "critical"},
    )
    second_finding = service.entities.create(
        EntityKind.FINDING,
        title="Missing security headers",
        summary="No Content-Security-Policy header present",
        tags=("web", "low"),
        owner="reviewer",
        value="finding-02",
        metadata={"severity": "warning"},
    )
    evidence = service.entities.create(
        EntityKind.EVIDENCE,
        title="nmap scan output",
        summary="TLS cipher capture from the target host",
        tags=("recon", "scan"),
        owner="operator",
        value="scan-01",
    )
    report = service.entities.create(
        EntityKind.REPORT,
        title="Client assessment report",
        summary="Findings and remediation guidance",
        tags=("report",),
        owner="reviewer",
        value="report-01",
    )
    service.entities.create(
        EntityKind.NOTE,
        title="Unlinked scratch note",
        summary="No relationships yet",
        value="orphan-01",
    )
    section = service.entities.create(
        EntityKind.SECTION,
        title="Executive summary",
        summary="Overall risk rating and scope",
        tags=("report",),
        owner="reviewer",
        value="section-01",
    )

    service.entities.link(finding.entity_id, evidence.entity_id, kind=LinkKind.EVIDENCES)
    service.entities.link(report.entity_id, finding.entity_id, kind=LinkKind.REFERENCES)
    service.entities.link(report.entity_id, second_finding.entity_id, kind=LinkKind.REFERENCES)
    service.entities.link(section.entity_id, report.entity_id, kind=LinkKind.CONTAINS)
    service.entities.link(note.entity_id, target.entity_id, kind=LinkKind.RELATES)
    service.entities.link(note.entity_id, finding.entity_id, kind=LinkKind.RELATES)
    service.index.refresh_links(service.entities)
    service.index.drain_dirty()
    return service


def ref(kind: str, value: str) -> str:
    """Build a canonical entity reference string."""
    return str(EntityId(EntityKind.parse(kind), value))


__all__ = ["build_service", "ref"]
