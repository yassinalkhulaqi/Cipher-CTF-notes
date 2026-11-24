"""Tests for the orchestration service and V3 API namespace."""

from __future__ import annotations

import base64

import pytest

from redscribe.v3.api.errors import V3Error, V3ErrorCode
from redscribe.v3.api.router import V3Router
from redscribe.v3.capabilities import CAP_EVIDENCE_LAB, Capabilities
from redscribe.v3.clock import FixedClock
from redscribe.v3.entities import EntityRef
from redscribe.v3.events import EventBus
from redscribe.v3.evidence_lab.custody import CustodyStep
from redscribe.v3.evidence_lab.errors import (
    CapabilityDisabledError,
    EvidenceNotFoundError,
    InvalidInputError,
    PayloadTooLargeError,
)
from redscribe.v3.evidence_lab.service import (
    EvidenceLabService,
    default_service,
    set_default_service,
)
from redscribe.v3.evidence_lab.types import BundleEntry, IntegrityState
from redscribe.v3.namespaces.evidence import register


def make_service(*, enabled: bool = True) -> tuple[EvidenceLabService, EventBus]:
    bus = EventBus()
    caps = Capabilities() if enabled else Capabilities().remove(CAP_EVIDENCE_LAB)
    service = EvidenceLabService(capabilities=caps, bus=bus, clock=FixedClock(1_700_000_000.0))
    return service, bus


def test_service_inspect_and_cache() -> None:
    service, bus = make_service()
    ref = EntityRef.of("evidence", "png-1", "logo")
    data = b"\x89PNG\r\n\x1a\n" + b"Readable string inside\x00" + bytes(range(64))
    panel = service.inspect_bytes(data, ref=ref, expected_size=len(data))
    assert panel.size_bytes == len(data)
    assert panel.badge.state is IntegrityState.VERIFIED
    assert panel.hex_window is not None
    assert panel.hex_window.rows
    assert panel.strings is not None
    assert any("Readable" in hit.text for hit in panel.strings.hits)
    assert panel.entropy is not None
    assert panel.entropy.sample_bytes == len(data)
    assert service.get_report(str(ref)) is panel
    assert service.get_record(str(ref)).filename == "evidence:png-1"
    assert len(service.list_records()) == 1
    assert bus.of_kind("evidence.lab.inspected")
    assert bus.of_kind("evidence.lab.verified")


def test_service_verification_mismatch_warning() -> None:
    service, _ = make_service()
    report = service.inspect_bytes(
        b"abc",
        ref=EntityRef.of("evidence", "mismatch"),
        expected_sha256="0" * 64,
    )
    assert report.badge.state is IntegrityState.MISMATCH
    assert any("integrity" in warning for warning in report.warnings)
    assert service.panel_for(str(report.ref)) is report.panel


def test_service_capability_gate() -> None:
    service, _ = make_service(enabled=False)
    with pytest.raises(CapabilityDisabledError):
        service.inspect_bytes(b"abc", ref=EntityRef.of("evidence", "x"))
    assert service.manifest()["enabled"] is False


def test_service_decode_payload() -> None:
    service, _ = make_service()
    assert service.decode_payload(base64.b64encode(b"abc").decode()) == b"abc"
    with pytest.raises(InvalidInputError):
        service.decode_payload("!!!")
    with pytest.raises(InvalidInputError):
        service.decode_payload("")
    tiny = EvidenceLabService(max_payload_bytes=2)
    with pytest.raises(PayloadTooLargeError):
        tiny.decode_payload(base64.b64encode(b"abc").decode())


def test_service_custody_and_bundles() -> None:
    service, bus = make_service()
    steps = (
        CustodyStep(
            "disk-1", "acquired", actor="ana", timestamp="2026-01-01T00:00:00Z", sequence=1
        ),
        CustodyStep(
            "disk-1", "verified", actor="bob", timestamp="2026-01-02T00:00:00Z", sequence=2
        ),
    )
    graph = service.register_custody("disk-1", steps)
    assert graph.verified is True
    assert service.get_graph("disk-1") is graph
    assert bus.of_kind("evidence.custody.registered")
    assert service.custody_index()["disk-1"]["nodes"] == len(graph.nodes)
    left = (BundleEntry("a", "1" * 64, 10),)
    right = (BundleEntry("b", "2" * 64, 20),)
    service.register_bundle("before", left)
    service.register_bundle("after", right)
    diff = service.compare_bundles("before", "after")
    assert diff["counts"]["added"] == 1
    assert diff["counts"]["removed"] == 1
    assert service.compare_entries(left, left)["identical"] is True
    assert service.bundle_summary(left)["count"] == 1
    with pytest.raises(EvidenceNotFoundError):
        service.compare_bundles("before", "missing")


def test_service_reports_and_manifest() -> None:
    service, _ = make_service()
    manifest = service.manifest()
    assert manifest["capability"] == CAP_EVIDENCE_LAB
    assert manifest["enabled"] is True
    assert manifest["signatures"] >= 20
    assert manifest["records"] == 0
    with pytest.raises(EvidenceNotFoundError):
        service.get_report("evidence:none")
    with pytest.raises(EvidenceNotFoundError):
        service.get_record("evidence:none")
    with pytest.raises(EvidenceNotFoundError):
        service.get_graph("none")


def test_namespace_registration_and_actions() -> None:
    service, _ = make_service()
    router = V3Router()
    register(router)
    assert "evidence" in router.namespaces()
    assert router.size() == 14
    actions = {spec.action for spec in router.routes()}
    assert {
        "manifest",
        "inspect",
        "hex",
        "strings",
        "entropy",
        "classify",
        "hashes",
        "verify",
        "ranges",
        "register",
        "custody",
        "custody_graph",
        "compare",
        "bundle",
    } == actions
    payload = base64.b64encode(b"\x89PNG\r\n\x1a\nHELLO STRING").decode()
    body = {"ref": "ns-1", "data": payload}
    old = default_service()
    set_default_service(service)
    try:
        report = router.dispatch("evidence", "inspect", body)
        assert report["file_class"]["media_type"] == "image/png"
        assert router.dispatch("evidence", "hex", body)["rows"]
        assert router.dispatch("evidence", "strings", body)["hits"]
        assert router.dispatch("evidence", "entropy", body)["entropy"] > 0
        assert router.dispatch("evidence", "classify", body)["category"] == "image"
        hashes = router.dispatch("evidence", "hashes", body)
        assert len(hashes["panel"]["sha256"]) == 64
        assert router.dispatch("evidence", "verify", {"ref": "ns-1"})["ref"] == "evidence:ns-1"
        ranges = router.dispatch("evidence", "ranges", body | {"range": "bytes=0-3"})
        assert ranges["chunks"][0]["length"] == 4
        registered = router.dispatch("evidence", "register", body | {"filename": "sample.png"})
        assert registered["filename"] == "sample.png"
        custody = router.dispatch(
            "evidence",
            "custody",
            {
                "root": "ns-1",
                "steps": [{"evidence_id": "ns-1", "action": "acquired", "sequence": 1}],
            },
        )
        assert custody["verified"] is True
        cached = router.dispatch("evidence", "custody_graph", {"root": "ns-1"})
        assert cached["root"] == custody["root"]
        compared = router.dispatch(
            "evidence",
            "compare",
            {
                "left": [{"key": "a", "sha256": "1" * 64}],
                "right": [{"key": "b", "sha256": "2" * 64}],
            },
        )
        assert compared["counts"]["added"] == 1
        manifest = router.dispatch("evidence", "manifest")
        assert manifest["capability"] == CAP_EVIDENCE_LAB
    finally:
        set_default_service(old)


def test_namespace_validation_errors() -> None:
    service, _ = make_service()
    router = V3Router()
    register(router)
    old = default_service()
    set_default_service(service)
    try:
        with pytest.raises(V3Error) as exc:
            router.dispatch("evidence", "inspect", {"ref": "x", "data": "not-base64"})
        assert exc.value.code is V3ErrorCode.INVALID_REQUEST
        with pytest.raises(V3Error) as exc:
            router.dispatch(
                "evidence",
                "strings",
                {
                    "ref": "x",
                    "data": base64.b64encode(b"abc").decode(),
                    "encoding": "ebcdic",
                },
            )
        assert exc.value.code is V3ErrorCode.INVALID_CHOICE
        with pytest.raises(V3Error) as exc:
            router.dispatch("evidence", "custody_graph", {"root": "missing"})
        assert exc.value.code is V3ErrorCode.NOT_FOUND
        with pytest.raises(V3Error):
            router.dispatch("evidence", "compare", {"left": {}, "right": []})
    finally:
        set_default_service(old)


def test_default_service_singleton() -> None:
    original = default_service()
    custom = EvidenceLabService()
    set_default_service(custom)
    assert default_service() is custom
    set_default_service(original)
    assert default_service() is original
