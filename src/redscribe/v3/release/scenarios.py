"""Pure Python golden-path scenario runners.

Each scenario builds a fresh :class:`GoldenPathVault`, drives one workflow with
deterministic inputs, and records observable assertions as
:class:`~redscribe.v3.release.models.ScenarioStep` values. No step performs
network I/O, shell execution, or dynamic imports of user data.
"""

from __future__ import annotations

from typing import Any

from redscribe.v3.api.errors import V3Error
from redscribe.v3.clock import FixedClock
from redscribe.v3.entities.types import EntityKind, LinkKind
from redscribe.v3.events.redaction import RedactionPolicy
from redscribe.v3.release.golden import (
    DEFAULT_CORRELATION,
    GoldenBundle,
    GoldenPathVault,
)
from redscribe.v3.release.models import ReleasePhase, ScenarioResult, ScenarioStep, phase_values

GOLDEN_SCENARIO = "capture-to-merge"
REDACTION_SCENARIO = "redaction-boundary"
IDEMPOTENCY_SCENARIO = "idempotent-retry"
DETERMINISM_SCENARIO = "deterministic-export"

SCENARIO_DESCRIPTIONS: dict[str, str] = {
    GOLDEN_SCENARIO: "Capture, finding, evidence, report, export, import and merge.",
    REDACTION_SCENARIO: "Secrets never reach an exported event payload.",
    IDEMPOTENCY_SCENARIO: "Repeated writes return the cached result and preserve state.",
    DETERMINISM_SCENARIO: "Identical runs produce byte-identical export digests.",
}


def _render(value: Any) -> str:
    """Render a value for human-readable step evidence."""
    if isinstance(value, str):
        return value
    return repr(value)


def _step(
    phase: ReleasePhase,
    name: str,
    detail: str,
    expected: Any,
    actual: Any,
    passed: bool,
    metadata: dict[str, Any] | None = None,
) -> ScenarioStep:
    """Build one scenario assertion."""
    return ScenarioStep(
        phase=phase,
        name=name,
        detail=detail,
        expected=_render(expected),
        actual=_render(actual),
        passed=passed,
        metadata=dict(metadata or {}),
    )


def _equals(
    phase: ReleasePhase,
    name: str,
    detail: str,
    expected: Any,
    actual: Any,
    metadata: dict[str, Any] | None = None,
) -> ScenarioStep:
    """Build an equality assertion."""
    return _step(phase, name, detail, expected, actual, expected == actual, metadata)


def _new_vault(prefix: str = "golden", start: float = 1000.0) -> GoldenPathVault:
    """Create a vault with a fixed clock."""
    return GoldenPathVault(prefix=prefix, clock=FixedClock(start=start, step=1.0))


def _drive_primary(vault: GoldenPathVault) -> dict[str, Any]:
    """Run the first four phases against a vault."""
    note = vault.capture_note()
    finding = vault.create_finding()
    evidence = vault.attach_evidence()
    report = vault.compose_report()
    return {"note": note, "finding": finding, "evidence": evidence, "report": report}


def run_golden_path(*, prefix: str = "golden", start: float = 1000.0) -> ScenarioResult:
    """Run the full capture-to-merge golden path."""
    vault = _new_vault(prefix=prefix, start=start)
    note_ref = f"note:{prefix}-note-capture"
    finding_ref = f"finding:{prefix}-finding"
    report_ref = f"report:{prefix}-report"
    note_id = vault.ref_for(EntityKind.NOTE, "note-capture")
    finding_id = vault.ref_for(EntityKind.FINDING, "finding")
    steps: list[ScenarioStep] = []

    note = vault.capture_note()
    steps.append(
        _equals(
            ReleasePhase.CAPTURE,
            "note-created",
            "Capture produces a typed note entity.",
            note_ref,
            note["entity_id"],
        )
    )
    steps.append(
        _equals(
            ReleasePhase.CAPTURE,
            "note-version",
            "The captured note starts at version one.",
            1,
            note["version"],
        )
    )
    steps.append(
        _step(
            ReleasePhase.CAPTURE,
            "capture-event",
            "Capture emits a correlated event.",
            "golden.captured",
            vault.event_kinds()[0] if vault.event_kinds() else "",
            "golden.captured" in vault.event_kinds(),
        )
    )

    finding = vault.create_finding()
    steps.append(
        _equals(
            ReleasePhase.FINDING,
            "finding-created",
            "A finding is derived from the captured note.",
            finding_ref,
            finding["entity_id"],
        )
    )
    steps.append(
        _step(
            ReleasePhase.FINDING,
            "derives-link",
            "The finding is linked to the note with a derives edge.",
            True,
            vault.has_link(note_id, finding_id, LinkKind.DERIVES),
            vault.has_link(note_id, finding_id, LinkKind.DERIVES),
        )
    )
    steps.append(
        _equals(
            ReleasePhase.FINDING,
            "finding-severity",
            "Finding severity is carried onto the entity metadata.",
            "high",
            finding["severity"],
        )
    )

    evidence = vault.attach_evidence()
    evidence_id = vault.ref_for(EntityKind.EVIDENCE, "evidence")
    steps.append(
        _step(
            ReleasePhase.EVIDENCE,
            "evidence-hash",
            "Evidence carries the supplied content hash.",
            evidence["sha256"],
            evidence["sha256"],
            len(evidence["sha256"]) == 64,
        )
    )
    steps.append(
        _step(
            ReleasePhase.EVIDENCE,
            "evidences-link",
            "Evidence supports the finding.",
            True,
            vault.has_link(evidence_id, finding_id, LinkKind.EVIDENCES),
            vault.has_link(evidence_id, finding_id, LinkKind.EVIDENCES),
        )
    )

    report = vault.compose_report()
    report_id = vault.ref_for(EntityKind.REPORT, "report")
    steps.append(
        _equals(
            ReleasePhase.REPORT,
            "report-created",
            "Report entities are first-class and versioned.",
            report_ref,
            report["entity_id"],
        )
    )
    steps.append(
        _step(
            ReleasePhase.REPORT,
            "report-links",
            "The report contains the finding and references the note.",
            True,
            vault.has_link(report_id, finding_id, LinkKind.CONTAINS)
            and vault.has_link(report_id, note_id, LinkKind.REFERENCES),
            vault.has_link(report_id, finding_id, LinkKind.CONTAINS)
            and vault.has_link(report_id, note_id, LinkKind.REFERENCES),
        )
    )
    expected_stats = {"entities": 4, "links": 4, "events": 4}
    actual_stats = vault.stats()
    steps.append(
        _step(
            ReleasePhase.REPORT,
            "state-shape",
            "All four entities, four links, and four events exist before export.",
            expected_stats,
            {key: actual_stats[key] for key in expected_stats},
            all(actual_stats[key] == value for key, value in expected_stats.items()),
        )
    )

    bundle = vault.export_bundle(source="device-a")
    steps.append(
        _step(
            ReleasePhase.EXPORT,
            "bundle-verified",
            "The exported bundle digest verifies.",
            True,
            GoldenPathVault.verify_bundle(bundle),
            GoldenPathVault.verify_bundle(bundle),
        )
    )
    steps.append(
        _equals(
            ReleasePhase.EXPORT,
            "bundle-size",
            "The bundle carries every entity and link.",
            4,
            len(bundle.records),
        )
    )
    steps.append(
        _step(
            ReleasePhase.EXPORT,
            "bundle-redacted",
            "Secrets are absent from the exported event payloads.",
            True,
            "should-not-be-exported" not in bundle.canonical(),
            "should-not-be-exported" not in bundle.canonical(),
        )
    )

    restored, import_result = GoldenPathVault.from_bundle(
        bundle, correlation_id="golden-import-001"
    )
    steps.append(
        _equals(
            ReleasePhase.IMPORT,
            "records-restored",
            "Import restores every entity.",
            4,
            import_result.restored,
        )
    )
    steps.append(
        _equals(
            ReleasePhase.IMPORT,
            "links-restored",
            "Import restores every typed link.",
            4,
            import_result.links_restored,
        )
    )
    steps.append(
        _equals(
            ReleasePhase.IMPORT,
            "correlation-preserved",
            "Imported runs use their own correlation id.",
            "golden-import-001",
            restored.stats()["correlation_id"],
        )
    )

    peer = _new_vault(prefix="peer", start=2000.0)
    _drive_primary(peer)
    peer_bundle = peer.export_bundle(source="device-b")
    peer_merge = restored.merge_bundle(peer_bundle, source="device-b")
    steps.append(
        _equals(
            ReleasePhase.MERGE,
            "peer-records-added",
            "Merging a peer vault adds its four entities.",
            4,
            peer_merge.added,
        )
    )
    steps.append(
        _equals(
            ReleasePhase.MERGE,
            "peer-links-added",
            "Merging a peer vault adds its four links.",
            4,
            peer_merge.links_added,
        )
    )
    replay_merge = restored.merge_bundle(bundle, source="device-a-replay")
    steps.append(
        _equals(
            ReleasePhase.MERGE,
            "replay-skipped",
            "Replaying the original bundle is idempotent.",
            4,
            replay_merge.skipped,
        )
    )
    steps.append(
        _step(
            ReleasePhase.MERGE,
            "final-state",
            "After merging both bundles the vault contains eight entities.",
            8,
            restored.stats()["entities"],
            restored.stats()["entities"] == 8,
        )
    )
    return ScenarioResult(
        name=GOLDEN_SCENARIO, description=SCENARIO_DESCRIPTIONS[GOLDEN_SCENARIO], steps=tuple(steps)
    )


def run_redaction_scenario() -> ScenarioResult:
    """Prove that export payloads cannot leak configured secret shapes."""
    vault = _new_vault()
    _drive_primary(vault)
    bundle = vault.export_bundle(source="redaction-check")
    policy = RedactionPolicy(extra_keys=("sessionid",))
    cleaned = policy.apply({"api_key": "abc", "sessionid": "xyz", "note": "mail me at a@b.co"})
    steps = [
        _equals(
            ReleasePhase.EVIDENCE,
            "api-key-hidden",
            "API keys are redacted by the shared policy.",
            "[redacted]",
            cleaned["api_key"],
        ),
        _equals(
            ReleasePhase.EVIDENCE,
            "extra-key-hidden",
            "Additional sensitive keys are redacted.",
            "[redacted]",
            cleaned["sessionid"],
        ),
        _step(
            ReleasePhase.EXPORT,
            "no-secret-in-bundle",
            "The bundle text contains no raw secret value.",
            True,
            "should-not-be-exported" not in bundle.canonical(),
            "should-not-be-exported" not in bundle.canonical(),
        ),
        _step(
            ReleasePhase.EXPORT,
            "redaction-in-events",
            "Redacted values appear in exported events.",
            True,
            any("[redacted]" in str(event.get("payload", {})) for event in bundle.events),
            any("[redacted]" in str(event.get("payload", {})) for event in bundle.events),
        ),
    ]
    return ScenarioResult(
        name=REDACTION_SCENARIO,
        description=SCENARIO_DESCRIPTIONS[REDACTION_SCENARIO],
        steps=tuple(steps),
    )


def run_idempotency_scenario() -> ScenarioResult:
    """Prove that retries and conflicting keys are handled deterministically."""
    vault = _new_vault()
    first = vault.capture_note()
    second = vault.capture_note()
    conflict_code = ""
    try:
        vault.guard.execute("retry-key", {"value": 1}, lambda: {"ok": True})
        vault.guard.execute("retry-key", {"value": 2}, lambda: {"ok": True})
    except V3Error as error:
        conflict_code = error.code.value
    steps = [
        _equals(
            ReleasePhase.CAPTURE,
            "first-not-cached",
            "The initial capture runs the operation.",
            False,
            first["cached"],
        ),
        _equals(
            ReleasePhase.CAPTURE,
            "retry-cached",
            "The repeated capture is served from the cache.",
            True,
            second["cached"],
        ),
        _equals(
            ReleasePhase.CAPTURE,
            "no-duplicate-entity",
            "Retries do not create a second note.",
            1,
            vault.stats()["entities"],
        ),
        _equals(
            ReleasePhase.CAPTURE,
            "retry-same-result",
            "The cached result is identical to the first one.",
            first["entity_id"],
            second["entity_id"],
        ),
        _equals(
            ReleasePhase.EXPORT,
            "key-conflict",
            "Reusing a key with a different payload is rejected.",
            "idempotency_conflict",
            conflict_code,
        ),
    ]
    return ScenarioResult(
        name=IDEMPOTENCY_SCENARIO,
        description=SCENARIO_DESCRIPTIONS[IDEMPOTENCY_SCENARIO],
        steps=tuple(steps),
    )


def run_determinism_scenario() -> ScenarioResult:
    """Prove that identical inputs yield identical exports."""
    first = _new_vault()
    second = _new_vault()
    _drive_primary(first)
    _drive_primary(second)
    first_bundle = first.export_bundle(source="device-a")
    second_bundle = second.export_bundle(source="device-a")
    tampered = GoldenBundle(
        source=first_bundle.source,
        version=first_bundle.version,
        records=(
            dict(first_bundle.records[0], title="tampered"),
            *first_bundle.records[1:],
        ),
        links=first_bundle.links,
        events=first_bundle.events,
        digest=first_bundle.digest,
    )
    steps = [
        _equals(
            ReleasePhase.EXPORT,
            "digest-stable",
            "Two identical runs produce the same digest.",
            first_bundle.digest,
            second_bundle.digest,
        ),
        _step(
            ReleasePhase.EXPORT,
            "digest-verifies",
            "The stable digest validates the bundle.",
            True,
            GoldenPathVault.verify_bundle(second_bundle),
            GoldenPathVault.verify_bundle(second_bundle),
        ),
        _step(
            ReleasePhase.IMPORT,
            "tamper-detected",
            "Editing a record invalidates the digest.",
            False,
            GoldenPathVault.verify_bundle(tampered),
            GoldenPathVault.verify_bundle(tampered) is False,
        ),
        _equals(
            ReleasePhase.EXPORT,
            "correlation-stable",
            "Event correlation ids are deterministic.",
            DEFAULT_CORRELATION,
            first.stats()["correlation_id"],
        ),
    ]
    return ScenarioResult(
        name=DETERMINISM_SCENARIO,
        description=SCENARIO_DESCRIPTIONS[DETERMINISM_SCENARIO],
        steps=tuple(steps),
    )


def run_all_scenarios() -> tuple[ScenarioResult, ...]:
    """Run every registered golden-path scenario."""
    return (
        run_golden_path(),
        run_redaction_scenario(),
        run_idempotency_scenario(),
        run_determinism_scenario(),
    )


def scenario_manifest() -> dict[str, Any]:
    """Return a lightweight description of the scenario catalogue."""
    return {
        "version": "3.0",
        "scenarios": [
            {
                "name": name,
                "description": description,
                "phases": list(phase_values()),
            }
            for name, description in SCENARIO_DESCRIPTIONS.items()
        ],
        "phase_count": len(phase_values()),
    }


def run_scenario(name: str) -> ScenarioResult:
    """Run one scenario by name."""
    runners = {
        GOLDEN_SCENARIO: run_golden_path,
        REDACTION_SCENARIO: run_redaction_scenario,
        IDEMPOTENCY_SCENARIO: run_idempotency_scenario,
        DETERMINISM_SCENARIO: run_determinism_scenario,
    }
    runner = runners.get(name)
    if runner is None:
        raise ValueError(f"Unknown golden-path scenario: {name}")
    return runner()
