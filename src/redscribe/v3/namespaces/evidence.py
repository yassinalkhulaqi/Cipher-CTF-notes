"""Evidence-lab V3 API namespace.

Routes are registered through ``router.add("evidence", action, handler)`` so
the module is discovered automatically by ``V3Router.install_namespaces``.
Handlers are thin adapters: they validate JSON input, delegate to the lab
service, and translate lab failures into stable V3 error envelopes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from redscribe.v3.api import (
    V3Error,
    V3ErrorCode,
    optional_str,
    require_bool,
    require_str,
)
from redscribe.v3.api.router import V3Router
from redscribe.v3.entities import EntityKind, EntityRef
from redscribe.v3.evidence_lab.bundle import entries_from_records
from redscribe.v3.evidence_lab.custody import CustodyStep, custody_summary
from redscribe.v3.evidence_lab.entropy import entropy_profile
from redscribe.v3.evidence_lab.errors import (
    EvidenceLabError,
    EvidenceNotFoundError,
    InvalidInputError,
    PayloadTooLargeError,
)
from redscribe.v3.evidence_lab.service import EvidenceLabService, default_service
from redscribe.v3.evidence_lab.types import StringEncoding, StringScan

ENCODINGS = ("ascii", "utf8", "utf16le", "utf16be")
ERROR_CODE_BY_TYPE: dict[type[EvidenceLabError], V3ErrorCode] = {
    InvalidInputError: V3ErrorCode.INVALID_REQUEST,
    PayloadTooLargeError: V3ErrorCode.PAYLOAD_TOO_LARGE,
    EvidenceNotFoundError: V3ErrorCode.NOT_FOUND,
}


def lab_service() -> EvidenceLabService:
    """Return the active lab service."""
    return default_service()


def translate_error(error: EvidenceLabError) -> V3Error:
    """Translate a lab error into a V3 error with a stable code."""
    code = ERROR_CODE_BY_TYPE.get(type(error), V3ErrorCode.INVALID_REQUEST)
    return V3Error(
        code,
        error.message,
        field=error.context.get("field", "")
        if isinstance(error.context.get("field", ""), str)
        else "",
        context=dict(error.context),
    )


def evidence_ref(body: Mapping[str, Any], *, field: str = "ref") -> EntityRef:
    """Build an evidence reference from a request field."""
    value = require_str(body, field, limit=128)
    label = optional_str(body, "label", limit=200)
    try:
        return EntityRef.of(EntityKind.EVIDENCE, value, label)
    except ValueError as error:
        raise V3Error(V3ErrorCode.INVALID_REQUEST, str(error), field=field) from error


def optional_int(body: Mapping[str, Any], key: str, default: int) -> int:
    """Read an optional bounded integer field."""
    value = body.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise V3Error(V3ErrorCode.INVALID_TYPE, f"'{key}' must be an integer", field=key)
    return value


def data_bytes(body: Mapping[str, Any], service: EvidenceLabService) -> bytes:
    """Decode the base64 ``data`` payload from a request."""
    encoded = require_str(body, "data", limit=64 * 1024 * 1024)
    try:
        return service.decode_payload(encoded)
    except EvidenceLabError as error:
        raise translate_error(error) from error


def _integer_choice(
    body: Mapping[str, Any], key: str, default: int, choices: tuple[int, ...]
) -> int:
    """Read an integer that must belong to a fixed choice set."""
    value = optional_int(body, key, default)
    if value not in choices:
        raise V3Error(V3ErrorCode.INVALID_CHOICE, f"'{key}' has an unsupported value", field=key)
    return value


def handle_manifest(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Return lab capability and budget metadata."""
    del headers, body
    service = lab_service()
    return {**service.manifest(), "custody": service.custody_index()}


def handle_inspect(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Inspect an uploaded byte payload and return a full report."""
    del headers
    service = lab_service()
    ref = evidence_ref(body)
    if "data" not in body:
        return service.get_report(str(ref)).as_dict()
    payload = data_bytes(body, service)
    raw_size = optional_int(body, "expected_size", -1)
    expected_size = raw_size if raw_size >= 0 else None
    encoding_name = optional_str(body, "encoding", default="ascii", limit=32)
    if encoding_name not in ENCODINGS:
        raise V3Error(V3ErrorCode.INVALID_CHOICE, "Unsupported encoding", field="encoding")
    try:
        report = service.inspect_bytes(
            payload,
            ref=ref,
            filename=optional_str(body, "filename", limit=240),
            expected_sha256=optional_str(body, "expected_sha256", limit=128),
            expected_blake2b=optional_str(body, "expected_blake2b", limit=128),
            expected_size=expected_size,
            hex_start=max(0, optional_int(body, "hex_start", 0)),
            hex_length=max(1, optional_int(body, "hex_length", 512)),
            bytes_per_row=_integer_choice(body, "bytes_per_row", 16, (8, 16, 24, 32)),
            selection_start=body.get("selection_start")
            if isinstance(body.get("selection_start"), int)
            else None,
            selection_end=body.get("selection_end")
            if isinstance(body.get("selection_end"), int)
            else None,
            min_string_length=max(1, optional_int(body, "min_string_length", 4)),
            encoding=StringEncoding.parse(encoding_name),
            include_hex=require_bool(body, "include_hex", default=True),
            include_strings=require_bool(body, "include_strings", default=True),
            include_entropy=require_bool(body, "include_entropy", default=True),
        )
    except EvidenceLabError as error:
        raise translate_error(error) from error
    return report.as_dict()


def handle_hex(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Render a bounded hex window from an uploaded payload."""
    del headers
    service = lab_service()

    payload = data_bytes(body, service)
    window = service.inspect_bytes(
        payload,
        ref=evidence_ref(body),
        hex_start=max(0, optional_int(body, "start", 0)),
        hex_length=max(1, optional_int(body, "length", 256)),
        bytes_per_row=_integer_choice(body, "bytes_per_row", 16, (8, 16, 24, 32)),
        include_strings=False,
        include_entropy=False,
    ).hex_window
    if window is None:
        raise V3Error(V3ErrorCode.INTERNAL, "Hex window was not generated")
    return window.as_dict()


def handle_strings(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Extract printable strings from an uploaded payload."""
    del headers
    service = lab_service()
    encoding_name = optional_str(body, "encoding", default="ascii", limit=32)
    if encoding_name not in ENCODINGS:
        raise V3Error(V3ErrorCode.INVALID_CHOICE, "Unsupported encoding", field="encoding")
    report = service.inspect_bytes(
        data_bytes(body, service),
        ref=evidence_ref(body),
        min_string_length=max(1, optional_int(body, "min_length", 4)),
        encoding=StringEncoding.parse(encoding_name),
        include_hex=False,
        include_entropy=False,
    )
    return (report.strings or _empty_strings()).as_dict()


def handle_entropy(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Estimate entropy of an uploaded payload."""
    del headers
    service = lab_service()
    report = service.inspect_bytes(
        data_bytes(body, service),
        ref=evidence_ref(body),
        include_hex=False,
        include_strings=False,
    )
    return (report.entropy or entropy_profile(b"")).as_dict()


def handle_classify(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Classify an uploaded payload from its magic bytes."""
    del headers
    service = lab_service()
    report = service.inspect_bytes(
        data_bytes(body, service),
        ref=evidence_ref(body),
        include_hex=False,
        include_strings=False,
        include_entropy=False,
    )
    return report.file_class.as_dict()


def handle_hashes(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Return the dual hash panel and integrity badge."""
    del headers
    service = lab_service()
    report = service.inspect_bytes(
        data_bytes(body, service),
        ref=evidence_ref(body),
        expected_sha256=optional_str(body, "expected_sha256", limit=128),
        expected_blake2b=optional_str(body, "expected_blake2b", limit=128),
        include_hex=False,
        include_strings=False,
        include_entropy=False,
    )
    return {"panel": report.panel.as_dict(), "badge": report.badge.as_dict()}


def handle_verify(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Compare a cached report against stored provenance values."""
    del headers
    service = lab_service()
    report = service.get_report(str(evidence_ref(body)))
    return {
        "ref": str(report.ref),
        "badge": report.badge.as_dict(),
        "panel": report.panel.as_dict(),
    }


def handle_ranges(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Satisfy a byte-range header against an uploaded payload."""
    del headers
    service = lab_service()
    from io import BytesIO

    payload = data_bytes(body, service)
    header = require_str(body, "range", limit=400)
    with BytesIO(payload) as stream:
        try:
            chunks = service.read_range_header(stream, header, total_size=len(payload))
        except EvidenceLabError as error:
            raise translate_error(error) from error
    return {"chunks": list(chunks), "total_size": len(payload)}


def handle_register(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Register an uploaded payload as an evidence record."""
    del headers
    service = lab_service()
    ref = evidence_ref(body)
    report = service.inspect_bytes(
        data_bytes(body, service),
        ref=ref,
        filename=require_str(body, "filename", limit=240),
        include_hex=False,
        include_strings=False,
        include_entropy=False,
    )
    return service.get_record(str(ref)).as_dict() | {"verified": report.badge.ok}


def handle_custody(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Build a custody graph from JSON step records."""
    del headers
    service = lab_service()
    root = require_str(body, "root", limit=128)
    raw_steps = body.get("steps")
    if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes, Mapping)):
        raise V3Error(V3ErrorCode.INVALID_TYPE, "'steps' must be a list", field="steps")
    steps = tuple(
        CustodyStep(**dict(step)) if isinstance(step, Mapping) else step for step in raw_steps
    )
    try:
        graph = service.register_custody(
            root,
            steps,
            include_actors=require_bool(body, "include_actors", default=True),
        )
    except EvidenceLabError as error:
        raise translate_error(error) from error
    return graph.as_dict() | {"summary": custody_summary(graph)}


def handle_custody_graph(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Return a cached custody graph."""
    del headers
    service = lab_service()
    try:
        graph = service.get_graph(require_str(body, "root", limit=128))
    except EvidenceLabError as error:
        raise translate_error(error) from error
    return graph.as_dict()


def handle_compare(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Compare two ad-hoc bundles supplied as entry lists."""
    del headers
    service = lab_service()
    left = body.get("left")
    right = body.get("right")
    if not isinstance(left, Sequence) or isinstance(left, (str, bytes, Mapping)):
        raise V3Error(V3ErrorCode.INVALID_TYPE, "'left' must be a list", field="left")
    if not isinstance(right, Sequence) or isinstance(right, (str, bytes, Mapping)):
        raise V3Error(V3ErrorCode.INVALID_TYPE, "'right' must be a list", field="right")
    try:
        return service.compare_entries(entries_from_records(left), entries_from_records(right))
    except EvidenceLabError as error:
        raise translate_error(error) from error


def handle_bundle(body: Mapping[str, Any], headers: Mapping[str, str]) -> dict[str, Any]:
    """Register two bundles and compare them by name."""
    del headers
    service = lab_service()
    name = require_str(body, "name", limit=120)
    other = require_str(body, "compare_to", limit=120)
    entries = body.get("entries")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, Mapping)):
        raise V3Error(V3ErrorCode.INVALID_TYPE, "'entries' must be a list", field="entries")
    try:
        service.register_bundle(name, entries_from_records(entries))
        return service.compare_bundles(name, other)
    except EvidenceLabError as error:
        raise translate_error(error) from error


def _empty_strings() -> StringScan:
    """Return an empty string-scan shape for defensive fallbacks."""
    from redscribe.v3.evidence_lab.strings import scan_bytes

    return scan_bytes(b"")


def register(router: V3Router) -> None:
    """Register every evidence-lab route on the supplied router."""
    router.add("evidence", "manifest", handle_manifest, public=True)
    router.add("evidence", "inspect", handle_inspect)
    router.add("evidence", "hex", handle_hex)
    router.add("evidence", "strings", handle_strings)
    router.add("evidence", "entropy", handle_entropy)
    router.add("evidence", "classify", handle_classify)
    router.add("evidence", "hashes", handle_hashes)
    router.add("evidence", "verify", handle_verify)
    router.add("evidence", "ranges", handle_ranges)
    router.add("evidence", "register", handle_register)
    router.add("evidence", "custody", handle_custody)
    router.add("evidence", "custody_graph", handle_custody_graph)
    router.add("evidence", "compare", handle_compare)
    router.add("evidence", "bundle", handle_bundle)
