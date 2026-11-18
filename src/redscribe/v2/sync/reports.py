"""Report builders for sync and portability workflows."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from redscribe.v2.sync.change_journal import ChangeJournal
from redscribe.v2.sync.models import ChangeRecord, ConflictRecord, DryRunReport, MergeResult


def summarize_changes(changes: Iterable[ChangeRecord]) -> dict[str, Any]:
    items = list(changes)
    actions = Counter(item.action for item in items)
    kinds = Counter(item.entity_type for item in items)
    return {
        "total": len(items),
        "actions": dict(actions),
        "entity_types": dict(kinds),
        "paths": [item.path for item in items[:20]],
    }


def summarize_conflicts(conflicts: Iterable[ConflictRecord]) -> dict[str, Any]:
    items = list(conflicts)
    kinds = Counter(item.kind for item in items)
    resolutions = Counter(item.resolution for item in items)
    return {
        "total": len(items),
        "kinds": dict(kinds),
        "resolutions": dict(resolutions),
        "unresolved": resolutions.get("unresolved", 0),
        "suggested": [item.suggested for item in items if item.suggested],
    }


def dry_run_summary(report: DryRunReport) -> dict[str, Any]:
    return {
        "operation": report.operation,
        "valid": report.valid,
        "summary": dict(report.summary),
        "changes": summarize_changes(report.changes),
        "conflicts": summarize_conflicts(report.conflicts),
        "warnings": list(report.warnings),
    }


def merge_summary(result: MergeResult) -> dict[str, Any]:
    return {
        "strategy": result.strategy,
        "dry_run": result.dry_run,
        "applied": len(result.applied),
        "skipped": len(result.skipped),
        "conflicts": summarize_conflicts(result.conflicts),
        "actions": summarize_changes(result.applied + result.skipped),
    }


def journal_report(
    local: Iterable[Mapping[str, Any]],
    remote: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    journal = ChangeJournal()
    changes = journal.build(local, remote)
    actionable = [item for item in changes if item.action != "unchanged"]
    return {
        "summary": journal.summary(),
        "changes": [item.as_dict() for item in actionable],
        "details": summarize_changes(actionable),
    }


def portability_health(payload: Mapping[str, Any]) -> dict[str, Any]:
    records = int(payload.get("records", 0) or 0)
    schema = int(payload.get("schema_version", 0) or 0)
    warnings = []
    if records == 0:
        warnings.append("Vault has no records to export")
    if schema <= 0:
        warnings.append("Schema version unavailable")
    return {
        "ok": not warnings,
        "records": records,
        "schema_version": schema,
        "warnings": warnings,
        "recommendations": [
            "Create a sqlite backup before restore operations.",
            "Run dry-run import to inspect conflicts.",
            "Verify checksums when transferring snapshots across devices.",
        ],
    }
