"""Printable-string extraction with bounded streaming support.

The scanner treats a printable run as a maximal sequence of printable code
units. ASCII and UTF-8 share a byte-oriented scanner; UTF-16 variants use a
two-byte code-unit scanner. Streaming scans keep a small overlap buffer so runs
that cross a chunk boundary are never split.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import BinaryIO

from redscribe.v3.evidence_lab.errors import (
    InvalidInputError,
    UnsupportedEncodingError,
)
from redscribe.v3.evidence_lab.types import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_STRING_LENGTH,
    DEFAULT_MIN_STRING_LENGTH,
    StringEncoding,
    StringHit,
    StringScan,
)

PRINTABLE_LOW = 0x20
PRINTABLE_HIGH = 0x7E
URL_PATTERN = re.compile(r"^(https?|ftp)://", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
IPV4_PATTERN = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
PATH_PATTERN = re.compile(r"^(/|\./|\.\./|[A-Za-z]:[\\/])")
HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{16,}$")


def encoding_from_name(name: str) -> StringEncoding:
    """Parse a string encoding, translating failures to a lab error."""
    try:
        return StringEncoding.parse(name)
    except ValueError as error:
        raise UnsupportedEncodingError(str(error)) from error


def is_printable_byte(byte: int, *, allow_whitespace: bool = True) -> bool:
    """Return whether one byte belongs to a printable run."""
    if PRINTABLE_LOW <= byte <= PRINTABLE_HIGH:
        return True
    return allow_whitespace and byte in (0x09, 0x0A, 0x0D)


def is_printable_unit(value: int) -> bool:
    """Return whether a UTF-16 code unit is printable ASCII."""
    return PRINTABLE_LOW <= value <= PRINTABLE_HIGH


def classify_hit(text: str) -> str:
    """Assign a semantic label to an extracted string."""
    stripped = text.strip()
    if URL_PATTERN.match(stripped):
        return "url"
    if EMAIL_PATTERN.match(stripped):
        return "email"
    if IPV4_PATTERN.match(stripped):
        return "ipv4"
    if PATH_PATTERN.match(stripped):
        return "path"
    if HEX_PATTERN.fullmatch(stripped):
        return "hex"
    if len(stripped) >= 24 and all(char.isalnum() or char in "+/=" for char in stripped):
        return "base64"
    return "plain"


def _ratio(chars: str, raw_units: int) -> float:
    """Return the printable ratio for a candidate run."""
    if raw_units <= 0:
        return 0.0
    return min(1.0, len(chars) / raw_units)


def _finish_run(
    units: list[int],
    start_offset: int,
    encoding: StringEncoding,
    min_length: int,
    max_string_length: int,
    allow_whitespace: bool,
) -> StringHit | None:
    """Convert a pending code-unit run into a hit when it is long enough."""
    if not units:
        return None
    raw = bytes(value & 0xFF for value in units)
    text = "".join(chr(value) for value in units)[:max_string_length]
    if len(text) < min_length:
        return None
    ratio = _ratio(text, len(units))
    if allow_whitespace and not text.strip():
        return None
    return StringHit(
        offset=start_offset,
        text=text,
        encoding=encoding,
        length=len(raw),
        printable_ratio=ratio,
        kind=classify_hit(text),
    )


def scan_bytes(
    data: bytes,
    *,
    min_length: int = DEFAULT_MIN_STRING_LENGTH,
    encoding: StringEncoding | str = StringEncoding.ASCII,
    offset_base: int = 0,
    max_hits: int = 10_000,
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH,
    allow_whitespace: bool = True,
) -> StringScan:
    """Extract printable runs from an in-memory byte string."""
    parsed = encoding_from_name(encoding) if isinstance(encoding, str) else encoding
    if min_length < 1:
        raise InvalidInputError("min_length must be positive")
    if max_hits < 1:
        raise InvalidInputError("max_hits must be positive")
    hits: list[StringHit] = []
    pending: list[int] = []
    pending_start = 0
    unit_size = parsed.unit_size
    for index in range(0, len(data) - unit_size + 1, unit_size):
        if parsed is StringEncoding.UTF16LE:
            value = int.from_bytes(data[index : index + 2], "little")
            printable = is_printable_unit(value)
        elif parsed is StringEncoding.UTF16BE:
            value = int.from_bytes(data[index : index + 2], "big")
            printable = is_printable_unit(value)
        else:
            value = data[index]
            printable = is_printable_byte(value, allow_whitespace=allow_whitespace)
        if printable:
            if not pending:
                pending_start = index
            pending.append(value)
        else:
            hit = _finish_run(
                pending,
                offset_base + pending_start,
                parsed,
                min_length,
                max_string_length,
                allow_whitespace,
            )
            if hit is not None:
                hits.append(hit)
                if len(hits) >= max_hits:
                    return _finalize(hits, parsed, min_length, len(data), True)
            pending = []
    hit = _finish_run(
        pending,
        offset_base + pending_start,
        parsed,
        min_length,
        max_string_length,
        allow_whitespace,
    )
    if hit is not None and len(hits) < max_hits:
        hits.append(hit)
    return _finalize(hits, parsed, min_length, len(data), len(hits) >= max_hits)


def _finalize(
    hits: Sequence[StringHit],
    encoding: StringEncoding,
    min_length: int,
    bytes_scanned: int,
    truncated: bool,
) -> StringScan:
    """Build a scan result with per-kind counts."""
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.kind] = counts.get(hit.kind, 0) + 1
    return StringScan(
        hits=tuple(hits),
        encoding=encoding,
        min_length=min_length,
        bytes_scanned=bytes_scanned,
        truncated=truncated,
        counts=counts,
    )


def scan_stream(
    stream: BinaryIO,
    *,
    min_length: int = DEFAULT_MIN_STRING_LENGTH,
    encoding: StringEncoding | str = StringEncoding.ASCII,
    max_bytes: int = 16 * 1024 * 1024,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_hits: int = 10_000,
    offset_base: int = 0,
    allow_whitespace: bool = True,
) -> StringScan:
    """Scan a bounded prefix of a stream, keeping only a small overlap."""
    parsed = encoding_from_name(encoding) if isinstance(encoding, str) else encoding
    if min_length < 1:
        raise InvalidInputError("min_length must be positive")
    if max_bytes < 1:
        raise InvalidInputError("max_bytes must be positive")
    unit_size = parsed.unit_size
    carry_limit = max(unit_size * max(1, min_length - 1), DEFAULT_MAX_STRING_LENGTH)
    carry = b""
    carry_start = 0
    hits: list[StringHit] = []
    consumed = 0
    truncated = False
    while consumed < max_bytes:
        request = min(chunk_size, max_bytes - consumed)
        if unit_size > 1:
            request -= request % unit_size
            if request == 0:
                request = unit_size
        chunk = stream.read(request)
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise InvalidInputError("Binary streams must return bytes")
        combined_offset = carry_start if carry else consumed
        combined = carry + chunk
        consumed += len(chunk)
        if consumed >= max_bytes:
            truncated = True
        new_hits, trailing, trailing_start = _scan_segment(
            combined,
            combined_offset,
            offset_base,
            parsed,
            min_length,
            max_string_length=DEFAULT_MAX_STRING_LENGTH,
            allow_whitespace=allow_whitespace,
        )
        for hit in new_hits:
            hits.append(hit)
            if len(hits) >= max_hits:
                return _finalize(hits, parsed, min_length, consumed, True)
        carry = trailing[-carry_limit:]
        carry_start = trailing_start
    if carry:
        tail, _, _ = _scan_segment(
            carry,
            carry_start,
            offset_base,
            parsed,
            min_length,
            max_string_length=DEFAULT_MAX_STRING_LENGTH,
            allow_whitespace=allow_whitespace,
            final=True,
        )
        hits.extend(tail)
    return _finalize(
        hits[:max_hits], parsed, min_length, consumed, truncated or len(hits) >= max_hits
    )


def _scan_segment(
    data: bytes,
    data_start: int,
    offset_base: int,
    encoding: StringEncoding,
    min_length: int,
    *,
    max_string_length: int,
    allow_whitespace: bool,
    final: bool = False,
) -> tuple[list[StringHit], bytes, int]:
    """Scan one bounded segment and return hits plus a trailing partial run."""
    unit_size = encoding.unit_size
    hits: list[StringHit] = []
    pending: list[int] = []
    pending_start = data_start
    limit = len(data) if final else len(data) - unit_size + 1
    for index in range(0, max(0, limit), unit_size):
        if index + unit_size > len(data):
            break
        if encoding is StringEncoding.UTF16LE:
            value = int.from_bytes(data[index : index + 2], "little")
            printable = is_printable_unit(value)
        elif encoding is StringEncoding.UTF16BE:
            value = int.from_bytes(data[index : index + 2], "big")
            printable = is_printable_unit(value)
        else:
            value = data[index]
            printable = is_printable_byte(value, allow_whitespace=allow_whitespace)
        if printable:
            if not pending:
                pending_start = data_start + index
            pending.append(value)
        else:
            hit = _finish_run(
                pending,
                offset_base + pending_start,
                encoding,
                min_length,
                max_string_length,
                allow_whitespace,
            )
            if hit is not None:
                hits.append(hit)
            pending = []
    if final:
        hit = _finish_run(
            pending,
            offset_base + pending_start,
            encoding,
            min_length,
            max_string_length,
            allow_whitespace,
        )
        if hit is not None:
            hits.append(hit)
        return hits, b"", data_start
    if pending:
        raw_units = bytearray()
        for value in pending:
            if encoding is StringEncoding.UTF16LE:
                raw_units.extend(value.to_bytes(2, "little"))
            elif encoding is StringEncoding.UTF16BE:
                raw_units.extend(value.to_bytes(2, "big"))
            else:
                raw_units.append(value & 0xFF)
        return hits, bytes(raw_units), pending_start
    return hits, b"", data_start


def merge_hits(hits: Iterable[StringHit], *, max_gap: int = 1) -> tuple[StringHit, ...]:
    """Merge adjacent runs separated by at most ``max_gap`` bytes."""
    ordered = sorted(hits, key=lambda hit: hit.offset)
    merged: list[StringHit] = []
    for hit in ordered:
        if (
            merged
            and hit.encoding is merged[-1].encoding
            and hit.offset - merged[-1].end <= max_gap
        ):
            previous = merged[-1]
            merged[-1] = StringHit(
                offset=previous.offset,
                text=previous.text + " " * (hit.offset - previous.end) + hit.text,
                encoding=previous.encoding,
                length=hit.end - previous.offset,
                printable_ratio=min(previous.printable_ratio, hit.printable_ratio),
                kind=classify_hit(previous.text + hit.text),
            )
        else:
            merged.append(hit)
    return tuple(merged)


def string_summary(scan: StringScan) -> dict[str, object]:
    """Return a compact summary for dashboards and tests."""
    longest = max((hit.length for hit in scan.hits), default=0)
    return {
        "count": len(scan.hits),
        "counts": dict(scan.counts),
        "longest": longest,
        "encoding": scan.encoding.value,
        "bytes_scanned": scan.bytes_scanned,
    }
