"""Tests for CVSS v4 calculation, finding services and storage indexes."""

from __future__ import annotations

import pytest

from redscribe.v4.events import EventBus, EventKind, InMemoryOutbox
from redscribe.v4.findings_v4.service import (
    CvssV4Calculator,
    FindingError,
    FindingService,
    round_up,
)
from redscribe.v4.findings_v4.storage import FindingStore
from redscribe.v4.findings_v4.types import (
    LEGAL_TRANSITIONS,
    CvssV4Vector,
    Finding,
    LifecycleState,
    RetestRecord,
    RetestVerdict,
    Severity,
)

TEMPLATE = (
    "CVSS:4.0/AV:{av}/AC:{ac}/AT:{at}/PR:{pr}/UI:{ui}/VC:{vc}/VI:{vi}/VA:{va}"
    "/SC:{sc}/SI:{si}/SA:{sa}/E:{e}/CR:{cr}/IR:{ir}/AR:{ar}"
)
DEFAULTS = {
    "av": "N",
    "ac": "L",
    "at": "N",
    "pr": "N",
    "ui": "N",
    "vc": "N",
    "vi": "N",
    "va": "N",
    "sc": "N",
    "si": "N",
    "sa": "N",
    "e": "X",
    "cr": "X",
    "ir": "X",
    "ar": "X",
}


def make_vector(**overrides: str) -> CvssV4Vector:
    values = dict(DEFAULTS)
    values.update(overrides)
    return CvssV4Vector.parse(TEMPLATE.format(**values))


def fixed_clock() -> str:
    return "2026-06-01T12:00:00.000Z"


@pytest.fixture
def store() -> FindingStore:
    return FindingStore()


@pytest.fixture
def bus() -> EventBus:
    return EventBus(InMemoryOutbox())


@pytest.fixture
def service(store: FindingStore, bus: EventBus) -> FindingService:
    return FindingService(store=store, bus=bus, clock=fixed_clock)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, 0.0),
        (-1.5, 0.0),
        (0.01, 0.1),
        (1.0, 1.0),
        (1.01, 1.1),
        (9.76, 9.8),
        (10.0, 10.0),
        (12.0, 10.0),
    ],
)
def test_round_up(value: float, expected: float) -> None:
    assert round_up(value) == expected


@pytest.mark.parametrize(
    ("overrides", "base"),
    [
        ({}, 0.0),
        ({"av": "L", "ac": "H", "at": "P", "pr": "H", "ui": "P", "vc": "L"}, 1.8),
        ({"vc": "L", "vi": "L"}, 6.5),
        ({"vc": "H", "vi": "H"}, 9.1),
        ({"vc": "H", "vi": "H", "va": "H"}, 9.8),
        ({"vc": "H", "vi": "H", "va": "H", "sc": "H", "si": "H", "sa": "H"}, 10.0),
        ({"av": "P", "vc": "H", "vi": "H", "va": "H"}, 6.8),
        ({"av": "A", "vc": "H", "vi": "H", "va": "H"}, 8.8),
        ({"ui": "P", "vc": "H", "vi": "H", "va": "H"}, 8.8),
        ({"pr": "H", "vc": "H", "vi": "H", "va": "H"}, 7.2),
        ({"at": "P", "vc": "H", "vi": "H", "va": "H"}, 9.4),
    ],
)
def test_known_base_scores(overrides: dict[str, str], base: float) -> None:
    calculator = CvssV4Calculator()
    assert calculator.base_score(make_vector(**overrides)) == base


def test_threat_scores() -> None:
    calculator = CvssV4Calculator()
    assert calculator.threat_score(make_vector(vc="H", vi="H", va="H", e="P")) == 9.7
    assert calculator.threat_score(make_vector(vc="H", vi="H", va="H", e="U")) == 8.3
    assert calculator.threat_score(make_vector(vc="H", vi="H", va="H", e="A")) == 9.8


def test_environmental_scores() -> None:
    calculator = CvssV4Calculator()
    assert calculator.environmental_score(make_vector(vc="H", vi="H", va="H", cr="H")) == 10.0
    assert calculator.environmental_score(make_vector(vc="H", vi="H", va="H", cr="L")) == 9.5
    assert calculator.environmental_score(make_vector()) == 0.0


def test_calculator_score_bundle() -> None:
    calculator = CvssV4Calculator()
    result = calculator.score(make_vector(vc="H", vi="H", va="H", e="U", cr="H"))
    assert result.base == 9.8
    assert result.threat == 8.3
    assert result.environmental == 8.6
    assert result.final == 8.6
    assert result.severity is Severity.HIGH
    assert result.nomenclature == "CVSS:BTE"
    data = result.to_dict()
    assert data["severity"] == "high"
    assert data["final"] == 8.6


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"e": "X"}, "CVSS:B"),
        ({"e": "P"}, "CVSS:BT"),
        ({"cr": "H"}, "CVSS:BE"),
        ({"ir": "L"}, "CVSS:BE"),
        ({"ar": "M"}, "CVSS:BE"),
        ({"e": "A", "cr": "H", "ir": "M", "ar": "L"}, "CVSS:BTE"),
    ],
)
def test_nomenclature(overrides: dict[str, str], expected: str) -> None:
    assert CvssV4Calculator.nomenclature(make_vector(**overrides)) == expected


def test_severity_for_score() -> None:
    calculator = CvssV4Calculator()
    assert calculator.severity_for(0.0) is Severity.NONE
    assert calculator.severity_for(5.0) is Severity.MEDIUM
    assert calculator.severity_for(9.0) is Severity.CRITICAL


def test_score_is_deterministic_and_bounded() -> None:
    calculator = CvssV4Calculator()
    vector = make_vector(vc="H", vi="H", va="H", sc="H", si="H", sa="L", cr="H", e="A")
    first = calculator.score(vector)
    second = calculator.score(vector)
    assert first == second
    assert 0.0 <= first.final <= 10.0
    assert round(first.final, 1) == first.final


def test_create_persists_and_emits(service: FindingService, bus: EventBus) -> None:
    vector = make_vector(vc="H", vi="H", va="H")
    finding = service.create(
        title="SQL injection in login",
        vector_text=vector.format(),
        description="Unparameterized query",
        finding_id="finding-1",
    )
    assert finding.id == "finding-1"
    assert finding.severity is Severity.CRITICAL
    assert service.store.count() == 1
    assert service.get("finding-1") is finding
    events = bus.published
    assert len(events) == 1
    assert events[0].kind is EventKind.FINDING_CREATED
    assert events[0].occurred_at == fixed_clock()
    assert events[0].payload["severity"] == "critical"


def test_create_rejects_invalid_vector(service: FindingService) -> None:
    with pytest.raises(FindingError, match="invalid_vector"):
        service.create(title="Bad", vector_text="CVSS:4.0/AV:N")


def test_create_emits_no_event_without_bus(store: FindingStore) -> None:
    service = FindingService(store=store, bus=None, clock=fixed_clock)
    service.create(title="No bus", finding_id="finding-nobus")
    assert store.count() == 1


def test_score_updates_severity_and_emits(service: FindingService, bus: EventBus) -> None:
    finding = service.create(
        title="Weak vector",
        vector_text=make_vector(vc="N", vi="N", va="N").format(),
        finding_id="finding-2",
    )
    assert finding.severity is Severity.NONE
    finding.vector = make_vector(vc="H", vi="H", va="H")
    result = service.score(finding.id)
    assert result.base == 9.8
    assert finding.severity is Severity.CRITICAL
    assert bus.published[-1].kind is EventKind.FINDING_SCORED
    assert bus.published[-1].payload["base"] == 9.8


def test_missing_finding_errors(service: FindingService) -> None:
    with pytest.raises(FindingError, match="not_found"):
        service.get("missing")
    with pytest.raises(FindingError, match="not_found"):
        service.score("missing")


def test_every_legal_transition(service: FindingService) -> None:
    for source, targets in LEGAL_TRANSITIONS.items():
        for target in targets:
            finding = service.create(
                title=f"{source.value} to {target.value}",
                finding_id=f"t-{source.value}-{target.value}",
                lifecycle_state=source,
            )
            assert finding.lifecycle_state is source
            moved = service.transition(finding.id, target)
            assert moved.lifecycle_state is target


def test_every_illegal_transition(service: FindingService) -> None:
    for source in LifecycleState:
        for target in LifecycleState:
            if source.can_transition_to(target):
                continue
            finding = service.create(
                title=f"illegal {source.value} {target.value}",
                finding_id=f"i-{source.value}-{target.value}",
                lifecycle_state=source,
            )
            with pytest.raises(FindingError, match="illegal_transition"):
                service.transition(finding.id, target)
            assert finding.lifecycle_state is source


def test_transition_rejects_unknown_state(service: FindingService) -> None:
    finding = service.create(title="State test", finding_id="finding-3")
    with pytest.raises(FindingError, match="invalid_state"):
        service.transition(finding.id, "bogus")  # type: ignore[arg-type]


def test_assign_remediation(service: FindingService) -> None:
    finding = service.create(title="Remediation", finding_id="finding-4")
    updated = service.assign_remediation(finding.id, "2026-12-31", "Patch dependency")
    assert updated.remediation_due == "2026-12-31"
    assert updated.remediation_notes == "Patch dependency"
    assert service.get(finding.id).remediation_due == "2026-12-31"


@pytest.mark.parametrize(
    "due",
    ["", "2026/12/31", "not-a-date", "2026-02-30", "2026-1-1"],
)
def test_assign_remediation_rejects_bad_dates(service: FindingService, due: str) -> None:
    finding = service.create(title="Bad date", finding_id="finding-5")
    with pytest.raises(FindingError, match="invalid_due"):
        service.assign_remediation(finding.id, due)


def _retestable(service: FindingService, finding_id: str) -> Finding:
    finding = service.create(
        title="Retest target",
        vector_text=make_vector(vc="H", vi="H", va="H").format(),
        finding_id=finding_id,
    )
    service.transition(finding.id, LifecycleState.OPEN)
    service.transition(finding.id, LifecycleState.CONFIRMED)
    service.transition(finding.id, LifecycleState.REMEDIATING)
    return finding


def test_retest_increments_and_records(service: FindingService, bus: EventBus) -> None:
    finding = _retestable(service, "finding-6")
    first = service.retest(
        finding.id,
        RetestVerdict.FAIL,
        note="still vulnerable",
        occurred_at="2026-06-02T00:00:00Z",
    )
    assert first.sequence == 1
    assert finding.retest_count == 1
    assert finding.lifecycle_state is LifecycleState.REMEDIATING
    assert first.occurred_at == "2026-06-02T00:00:00Z"
    assert bus.published[-1].kind is EventKind.FINDING_RETESTED
    assert bus.published[-1].payload["sequence"] == 1

    service.transition(finding.id, LifecycleState.RETEST)
    second = service.retest(finding.id, RetestVerdict.PASS, note="verified")
    assert second.sequence == 2
    assert finding.retest_count == 2
    assert finding.lifecycle_state is LifecycleState.CLOSED
    assert service.history(finding.id) == (first, second)


def test_retest_partial_returns_to_remediating(service: FindingService) -> None:
    finding = _retestable(service, "finding-7")
    service.transition(finding.id, LifecycleState.RETEST)
    record = service.retest(finding.id, RetestVerdict.PARTIAL)
    assert record.verdict is RetestVerdict.PARTIAL
    assert finding.lifecycle_state is LifecycleState.REMEDIATING


def test_retest_uses_injected_clock(service: FindingService) -> None:
    finding = _retestable(service, "finding-8")
    record = service.retest(finding.id, RetestVerdict.FAIL)
    assert record.occurred_at == fixed_clock()


def test_retest_rejects_non_retestable_state(service: FindingService) -> None:
    finding = service.create(title="Draft retest", finding_id="finding-9")
    with pytest.raises(FindingError, match="cannot retest"):
        service.retest(finding.id, RetestVerdict.PASS)


def test_retest_rejects_unknown_verdict(service: FindingService) -> None:
    finding = _retestable(service, "finding-10")
    with pytest.raises(FindingError, match="invalid_verdict"):
        service.retest(finding.id, "maybe")  # type: ignore[arg-type]


def test_rescore_all_reports_changes(service: FindingService) -> None:
    weak = service.create(
        title="Weak",
        vector_text=make_vector().format(),
        finding_id="finding-11",
    )
    strong = service.create(
        title="Strong",
        vector_text=make_vector(vc="H", vi="H", va="H").format(),
        finding_id="finding-12",
    )
    weak.vector = make_vector(vc="H", vi="H", va="H")
    strong.vector = make_vector()
    changed = service.rescore_all()
    assert {item.id for item in changed} == {weak.id, strong.id}
    assert weak.severity is Severity.CRITICAL
    assert strong.severity is Severity.NONE


def test_store_crud_and_indexes(store: FindingStore) -> None:
    high = Finding(
        title="High",
        vector=make_vector(vc="H", vi="H", va="H"),
        id="f-high",
        severity=Severity.CRITICAL,
    )
    low = Finding(
        title="Low",
        vector=make_vector(),
        id="f-low",
        severity=Severity.LOW,
        lifecycle_state=LifecycleState.OPEN,
    )
    store.add(high)
    store.add(low)
    assert len(store) == 2
    assert store.count() == 2
    assert "f-high" in store
    assert store.ids() == ("f-high", "f-low")
    assert store.by_severity(Severity.CRITICAL) == (high,)
    assert store.by_state(LifecycleState.OPEN) == (low,)
    assert store.by_severity_at_least(Severity.HIGH) == (high,)
    assert store.severity_counts()["low"] == 1
    assert store.state_counts()["draft"] == 1

    high.lifecycle_state = LifecycleState.CONFIRMED
    store.update(high)
    assert store.by_state(LifecycleState.DRAFT) == ()
    assert store.by_state(LifecycleState.CONFIRMED) == (high,)

    removed = store.delete("f-low")
    assert removed is low
    assert store.get("f-low") is None
    assert store.severity_counts()["low"] == 0


def test_store_rejects_duplicates_and_unknown_updates(store: FindingStore) -> None:
    finding = Finding(title="X", vector=make_vector(), id="f-dup")
    store.add(finding)
    with pytest.raises(ValueError, match="duplicate finding id"):
        store.add(finding)
    with pytest.raises(KeyError, match="unknown finding id"):
        store.update(Finding(title="Y", vector=make_vector(), id="f-missing"))
    with pytest.raises(KeyError, match="unknown finding id"):
        store.delete("f-missing")


def test_store_retests_and_snapshot_roundtrip(store: FindingStore) -> None:
    finding = Finding(title="Snapshot", vector=make_vector(), id="f-snap")
    store.add(finding)
    record = RetestRecord("f-snap", 1, RetestVerdict.FAIL, "nope", "now", 4.2)
    store.add_retest(record)
    assert store.retest_count() == 1
    assert store.retests("f-snap") == (record,)
    with pytest.raises(KeyError, match="unknown finding id"):
        store.add_retest(RetestRecord("missing", 1, RetestVerdict.FAIL, "", "now", 0.0))
    with pytest.raises(ValueError, match="duplicate retest sequence"):
        store.add_retest(record)

    snapshot = store.snapshot()
    assert snapshot["version"] == 1
    assert snapshot["findings"][0]["id"] == "f-snap"
    restored = FindingStore()
    restored.restore(snapshot)
    assert restored.all() == store.all()
    assert restored.retests("f-snap") == store.retests("f-snap")


def test_store_restore_rejects_bad_snapshot(store: FindingStore) -> None:
    with pytest.raises(ValueError, match="unsupported snapshot version"):
        store.restore({"version": 99})
    with pytest.raises(ValueError, match="findings and retests lists"):
        store.restore({"version": 1})
    snapshot = store.snapshot()
    snapshot["indexes"]["severity"]["none"] = 99
    with pytest.raises(ValueError, match="severity index is inconsistent"):
        store.restore(snapshot)


def test_store_clear_and_construction_from_iterable() -> None:
    finding = Finding(title="Seed", vector=make_vector(), id="f-seed")
    store = FindingStore([finding])
    assert store.count() == 1
    store.clear()
    assert store.count() == 0
    assert store.retest_count() == 0
    assert store.all() == []
