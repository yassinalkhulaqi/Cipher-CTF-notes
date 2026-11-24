"""Orchestration service for the evidence inspection lab.

The service composes the streaming primitives into one report while enforcing
memory budgets and the B00 capability gate. It keeps an in-memory registry of
inspected records, custody graphs, and named bundles so API handlers stay thin.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping, Sequence
from io import BytesIO
from typing import Any, BinaryIO

from redscribe.v3.capabilities import CAP_EVIDENCE_LAB, Capabilities, CapabilityError
from redscribe.v3.clock import Clock, SystemClock
from redscribe.v3.entities import EntityId, EntityRef
from redscribe.v3.events import EventBus, make_event
from redscribe.v3.evidence_lab.bundle import (
    bundle_index,
    diff_bundles,
    summarize_bundle,
)
from redscribe.v3.evidence_lab.custody import (
    CustodyStep,
    build_custody_graph,
    custody_summary,
)
from redscribe.v3.evidence_lab.entropy import estimate_stream_entropy
from redscribe.v3.evidence_lab.errors import (
    CapabilityDisabledError,
    EvidenceLabError,
    EvidenceNotFoundError,
    InvalidInputError,
    PayloadTooLargeError,
)
from redscribe.v3.evidence_lab.hashing import hash_stream_panel, verify_panel
from redscribe.v3.evidence_lab.hexdump import (
    build_hex_window,
    normalize_selection,
    stream_size,
)
from redscribe.v3.evidence_lab.magic import classify_stream, signature_table
from redscribe.v3.evidence_lab.ranges import parse_range_header, read_ranges
from redscribe.v3.evidence_lab.strings import scan_stream
from redscribe.v3.evidence_lab.thumbnails import (
    make_ingest_record,
    make_thumbnail,
    thumbnail_note,
)
from redscribe.v3.evidence_lab.types import (
    DEFAULT_BYTES_PER_ROW,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_ENTROPY_SAMPLE,
    DEFAULT_MAX_PREVIEW_BYTES,
    DEFAULT_MAX_WINDOW_BYTES,
    DEFAULT_MIN_STRING_LENGTH,
    BundleEntry,
    CustodyGraph,
    EvidenceReport,
    HashPanel,
    IngestRecord,
    StringEncoding,
)

DEFAULT_MAX_SCAN_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_PAYLOAD_BYTES = 32 * 1024 * 1024


class EvidenceLabService:
    """Streaming inspection service with an in-memory provenance registry."""

    def __init__(
        self,
        *,
        capabilities: Capabilities | None = None,
        bus: EventBus | None = None,
        clock: Clock | None = None,
        max_window_bytes: int = DEFAULT_MAX_WINDOW_BYTES,
        max_scan_bytes: int = DEFAULT_MAX_SCAN_BYTES,
        max_preview_bytes: int = DEFAULT_MAX_PREVIEW_BYTES,
        max_payload_bytes: int = DEFAULT_MAX_PAYLOAD_BYTES,
        entropy_sample_bytes: int = DEFAULT_ENTROPY_SAMPLE,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
    ) -> None:
        self._capabilities = capabilities or Capabilities()
        self._bus = bus
        self._clock: Clock = clock or SystemClock()
        self._max_window_bytes = max_window_bytes
        self._max_scan_bytes = max_scan_bytes
        self._max_preview_bytes = max_preview_bytes
        self._max_payload_bytes = max_payload_bytes
        self._entropy_sample_bytes = entropy_sample_bytes
        self._chunk_size = chunk_size
        self._records: dict[str, IngestRecord] = {}
        self._reports: dict[str, EvidenceReport] = {}
        self._graphs: dict[str, CustodyGraph] = {}
        self._bundles: dict[str, tuple[BundleEntry, ...]] = {}

    @property
    def capabilities(self) -> Capabilities:
        """Return the capability set used by the service."""
        return self._capabilities

    def require_capability(self) -> None:
        """Raise a lab error when the capability is disabled."""
        try:
            self._capabilities.require(CAP_EVIDENCE_LAB)
        except CapabilityError as error:
            raise CapabilityDisabledError(str(error)) from error

    def inspect_stream(
        self,
        stream: BinaryIO,
        *,
        ref: EntityRef,
        filename: str = "",
        expected_sha256: str = "",
        expected_blake2b: str = "",
        expected_size: int | None = None,
        hex_start: int = 0,
        hex_length: int = DEFAULT_BYTES_PER_ROW * 32,
        bytes_per_row: int = DEFAULT_BYTES_PER_ROW,
        selection_start: int | None = None,
        selection_end: int | None = None,
        min_string_length: int = DEFAULT_MIN_STRING_LENGTH,
        encoding: StringEncoding | str = StringEncoding.ASCII,
        include_hex: bool = True,
        include_strings: bool = True,
        include_entropy: bool = True,
        tags: tuple[str, ...] = (),
        source: str = "local",
    ) -> EvidenceReport:
        """Inspect a seekable stream without loading it into memory."""
        self.require_capability()
        total = stream_size(stream)
        stream.seek(0, 0)
        panel = hash_stream_panel(
            stream,
            chunk_size=self._chunk_size,
            computed_at=self._clock.now_iso(),
            expected_sha256=expected_sha256,
            expected_blake2b=expected_blake2b,
        )
        stream.seek(0, 0)
        file_class = classify_stream(stream)
        badge = verify_panel(
            panel,
            stored_sha256=expected_sha256,
            stored_blake2b=expected_blake2b,
            stored_size=expected_size,
        )
        selection = normalize_selection(selection_start, selection_end)
        hex_window = None
        if include_hex:
            stream.seek(0, 0)
            hex_window = build_hex_window(
                stream,
                start=hex_start,
                length=hex_length,
                bytes_per_row=bytes_per_row,
                chunk_size=self._chunk_size,
                max_window_bytes=self._max_window_bytes,
                total_bytes=total,
                selection=selection,
            )
        strings = None
        if include_strings:
            stream.seek(0, 0)
            strings = scan_stream(
                stream,
                min_length=min_string_length,
                encoding=encoding,
                max_bytes=self._max_scan_bytes,
                chunk_size=self._chunk_size,
                offset_base=0,
            )
        entropy = None
        if include_entropy:
            stream.seek(0, 0)
            entropy = estimate_stream_entropy(
                stream,
                max_bytes=self._entropy_sample_bytes,
                chunk_size=self._chunk_size,
                total_bytes=total,
            )
        stream.seek(0, 0)
        thumbnail = make_thumbnail(
            ref,
            file_class,
            panel,
            generated_at=self._clock.now_iso(),
            note=thumbnail_note(file_class, panel),
        )
        record = make_ingest_record(
            ref,
            filename or str(ref),
            panel,
            file_class,
            thumbnail,
            tags=tags,
            ingested_at=self._clock.now_iso(),
            source=source,
        )
        warnings: list[str] = []
        if not badge.ok:
            warnings.append(f"integrity: {badge.state.value}")
        if strings is not None and strings.truncated:
            warnings.append("string scan was truncated")
        if entropy is not None and entropy.truncated:
            warnings.append("entropy sample was truncated")
        report = EvidenceReport(
            ref=ref,
            size_bytes=total,
            panel=panel,
            badge=badge,
            file_class=file_class,
            hex_window=hex_window,
            strings=strings,
            entropy=entropy,
            thumbnail=thumbnail,
            warnings=tuple(warnings),
        )
        key = str(ref)
        self._records[key] = record
        self._reports[key] = report
        self._publish("evidence.lab.inspected", ref, size=total, state=badge.state.value)
        if expected_sha256 or expected_blake2b or expected_size is not None:
            self._publish("evidence.lab.verified", ref, verified=badge.ok)
        return report

    def inspect_bytes(
        self,
        data: bytes,
        *,
        ref: EntityRef,
        **kwargs: Any,
    ) -> EvidenceReport:
        """Inspect an in-memory byte string via a bounded wrapper."""
        with BytesIO(data) as stream:
            return self.inspect_stream(stream, ref=ref, **kwargs)

    def decode_payload(self, value: str) -> bytes:
        """Decode a bounded base64 request payload."""
        if not isinstance(value, str) or not value:
            raise InvalidInputError("data must be a non-empty base64 string")
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise InvalidInputError("data is not valid base64") from error
        if not decoded:
            raise InvalidInputError("data decodes to zero bytes")
        if len(decoded) > self._max_payload_bytes:
            raise PayloadTooLargeError(
                "Payload exceeds the configured byte budget",
                context={"size": len(decoded), "budget": self._max_payload_bytes},
            )
        return decoded

    def get_report(self, ref: str) -> EvidenceReport:
        """Return a cached inspection report by reference."""
        report = self._reports.get(ref)
        if report is None:
            raise EvidenceNotFoundError(f"Unknown evidence report: {ref}")
        return report

    def get_record(self, ref: str) -> IngestRecord:
        """Return a cached ingest record by reference."""
        record = self._records.get(ref)
        if record is None:
            raise EvidenceNotFoundError(f"Unknown evidence record: {ref}")
        return record

    def list_records(self) -> tuple[IngestRecord, ...]:
        """Return registered records in stable order."""
        return tuple(self._records[key] for key in sorted(self._records))

    def register_custody(
        self,
        root: str,
        steps: Sequence[CustodyStep] | Sequence[Mapping[str, Any]],
        *,
        include_actors: bool = True,
    ) -> CustodyGraph:
        """Build, cache, and publish a custody graph."""
        self.require_capability()
        typed = tuple(
            step if isinstance(step, CustodyStep) else CustodyStep(**dict(step)) for step in steps
        )
        graph = build_custody_graph(typed, root=root, include_actors=include_actors)
        self._graphs[root] = graph
        try:
            subject = EntityRef.of("evidence", root).entity_id
        except ValueError:
            subject = None
        self._publish(
            "evidence.custody.registered",
            subject,
            root=root,
            nodes=len(graph.nodes),
            verified=graph.verified,
        )
        return graph

    def get_graph(self, root: str) -> CustodyGraph:
        """Return a cached custody graph."""
        graph = self._graphs.get(root)
        if graph is None:
            raise EvidenceNotFoundError(f"Unknown custody graph: {root}")
        return graph

    def register_bundle(self, name: str, entries: Sequence[BundleEntry]) -> None:
        """Register a named bundle for later comparison."""
        self.require_capability()
        if not name.strip():
            raise InvalidInputError("Bundle name cannot be blank")
        self._bundles[name] = tuple(bundle_index(entries).values())

    def compare_bundles(self, left: str, right: str) -> dict[str, Any]:
        """Compare two named bundles."""
        self.require_capability()
        if left not in self._bundles:
            raise EvidenceNotFoundError(f"Unknown bundle: {left}")
        if right not in self._bundles:
            raise EvidenceNotFoundError(f"Unknown bundle: {right}")
        diff = diff_bundles(self._bundles[left], self._bundles[right], left_id=left, right_id=right)
        return diff.as_dict()

    def compare_entries(
        self,
        left: Sequence[BundleEntry],
        right: Sequence[BundleEntry],
    ) -> dict[str, Any]:
        """Compare two ad-hoc bundle entry sets."""
        self.require_capability()
        return diff_bundles(left, right).as_dict()

    def bundle_summary(self, entries: Sequence[BundleEntry]) -> dict[str, object]:
        """Return statistics for a bundle entry set."""
        self.require_capability()
        return summarize_bundle(entries)

    def read_range_header(
        self,
        stream: BinaryIO,
        header: str,
        *,
        total_size: int | None = None,
        max_bytes: int | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Parse and satisfy a byte-range header against a stream."""
        self.require_capability()
        size = total_size if total_size is not None else stream_size(stream)
        specs = parse_range_header(header, size=size)
        budget = self._max_preview_bytes if max_bytes is None else max_bytes
        chunks = read_ranges(
            stream, specs, size=size, max_bytes=budget, chunk_size=self._chunk_size
        )
        return tuple(chunk.as_dict() for chunk in chunks)

    def panel_for(self, ref: str) -> HashPanel:
        """Return the hash panel for a cached report."""
        return self.get_report(ref).panel

    def manifest(self) -> dict[str, Any]:
        """Return a capability and budget manifest for the namespace."""
        return {
            "capability": CAP_EVIDENCE_LAB,
            "enabled": self._capabilities.has(CAP_EVIDENCE_LAB),
            "max_window_bytes": self._max_window_bytes,
            "max_scan_bytes": self._max_scan_bytes,
            "max_preview_bytes": self._max_preview_bytes,
            "max_payload_bytes": self._max_payload_bytes,
            "entropy_sample_bytes": self._entropy_sample_bytes,
            "chunk_size": self._chunk_size,
            "signatures": len(signature_table()),
            "records": len(self._records),
            "graphs": len(self._graphs),
        }

    def custody_index(self) -> dict[str, dict[str, object]]:
        """Return summaries of all registered custody graphs."""
        return {root: custody_summary(graph) for root, graph in sorted(self._graphs.items())}

    def _publish(
        self,
        kind: str,
        subject: EntityRef | EntityId | None,
        **payload: Any,
    ) -> None:
        """Publish a domain event when a bus is configured."""
        if self._bus is None:
            return
        if isinstance(subject, EntityRef):
            entity_id: EntityId | None = subject.entity_id
        else:
            entity_id = subject
        self._bus.publish(make_event(kind, entity_id, **payload))


_default_service: EvidenceLabService | None = None


def default_service() -> EvidenceLabService:
    """Return the process-wide evidence lab service."""
    global _default_service
    if _default_service is None:
        _default_service = EvidenceLabService()
    return _default_service


def set_default_service(service: EvidenceLabService | None) -> None:
    """Replace the process-wide service (used by tests and embedding apps)."""
    global _default_service
    _default_service = service


def service_error_dict(error: EvidenceLabError) -> dict[str, Any]:
    """Translate a lab error into a stable JSON payload."""
    return error.as_dict()
