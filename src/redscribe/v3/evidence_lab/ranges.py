"""HTTP-style byte-range parsing and bounded range reads."""

from __future__ import annotations

import re
from typing import BinaryIO

from redscribe.v3.evidence_lab.errors import InvalidInputError, InvalidRangeError
from redscribe.v3.evidence_lab.types import DEFAULT_CHUNK_SIZE, RangeChunk, RangeSpec

RANGE_PATTERN = re.compile(r"^(\d*)-(\d*)$")
DEFAULT_MAX_RANGE_BYTES = 8 * 1024 * 1024


def parse_single_range(text: str, *, size: int) -> RangeSpec:
    """Parse one ``first-last`` range token."""
    match = RANGE_PATTERN.fullmatch(text.strip())
    if match is None or (not match.group(1) and not match.group(2)):
        raise InvalidRangeError(f"Invalid byte range: {text}")
    first, last = match.group(1), match.group(2)
    if first:
        start = int(first)
        end = int(last) if last else None
        if end is not None and end < start:
            raise InvalidRangeError("Range end precedes range start")
        return RangeSpec(start=start, end=end)
    suffix = int(last)
    if suffix < 1:
        raise InvalidRangeError("Suffix length must be positive")
    return RangeSpec(start=suffix, end=None, suffix=True)


def parse_range_header(value: str, *, size: int) -> tuple[RangeSpec, ...]:
    """Parse an RFC-style ``bytes=`` header into range specifications."""
    if size < 0:
        raise InvalidInputError("size cannot be negative")
    text = value.strip()
    if not text:
        raise InvalidRangeError("Range header cannot be blank")
    if "=" in text:
        unit, _, remainder = text.partition("=")
        if unit.strip().casefold() != "bytes":
            raise InvalidRangeError("Only byte ranges are supported")
        text = remainder
    tokens = [token.strip() for token in text.split(",") if token.strip()]
    if not tokens:
        raise InvalidRangeError("Range header contains no ranges")
    return tuple(parse_single_range(token, size=size) for token in tokens)


def range_bounds(spec: RangeSpec, size: int) -> tuple[int, int]:
    """Resolve a range specification against a concrete size."""
    if spec.suffix:
        start = max(0, size - spec.start)
        return start, size
    start = min(spec.start, size)
    end = size if spec.end is None else min(spec.end + 1, size)
    return start, max(start, end)


def satisfy_ranges(specs: tuple[RangeSpec, ...], size: int) -> tuple[tuple[int, int], ...]:
    """Resolve ranges to clamped, merged, half-open bounds."""
    bounds = sorted(range_bounds(spec, size) for spec in specs)
    merged: list[tuple[int, int]] = []
    for start, end in bounds:
        if merged and start <= merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return tuple(merged)


def total_requested(specs: tuple[RangeSpec, ...], size: int) -> int:
    """Return the number of distinct bytes requested."""
    return sum(end - start for start, end in satisfy_ranges(specs, size))


def is_satisfiable(specs: tuple[RangeSpec, ...], size: int) -> bool:
    """Return whether at least one range maps to a non-empty slice."""
    return any(end > start for start, end in satisfy_ranges(specs, size))


def enforce_budget(specs: tuple[RangeSpec, ...], size: int, max_bytes: int) -> None:
    """Raise when the combined ranges exceed a memory budget."""
    if max_bytes < 1:
        raise InvalidInputError("max_bytes must be positive")
    requested = total_requested(specs, size)
    if requested > max_bytes:
        raise InvalidRangeError(
            f"Requested {requested} bytes exceeds the {max_bytes} byte budget",
            context={"requested": requested, "budget": max_bytes},
        )


def read_range(
    stream: BinaryIO,
    start: int,
    length: int,
    *,
    total_size: int | None = None,
    max_bytes: int = DEFAULT_MAX_RANGE_BYTES,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> RangeChunk:
    """Read one bounded slice from a seekable stream."""
    if start < 0 or length < 0:
        raise InvalidRangeError("Range start and length must be non-negative")
    if length > max_bytes:
        raise InvalidRangeError(
            "Range exceeds the configured byte budget",
            context={"length": length, "budget": max_bytes},
        )
    if chunk_size < 1:
        raise InvalidInputError("chunk_size must be positive")
    size = total_size if total_size is not None else _stream_size(stream)
    begin = min(start, size)
    amount = min(length, max(0, size - begin))
    stream.seek(begin, 0)
    parts: list[bytes] = []
    remaining = amount
    while remaining > 0:
        chunk = stream.read(min(chunk_size, remaining))
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise InvalidInputError("Binary streams must return bytes")
        parts.append(chunk)
        remaining -= len(chunk)
    data = b"".join(parts)
    return RangeChunk(
        start=begin,
        end=begin + len(data),
        total_size=size,
        data=data,
        truncated=remaining > 0,
    )


def read_ranges(
    stream: BinaryIO,
    specs: tuple[RangeSpec, ...],
    *,
    size: int | None = None,
    max_bytes: int = DEFAULT_MAX_RANGE_BYTES,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> tuple[RangeChunk, ...]:
    """Read every satisfiable range from a stream."""
    total = size if size is not None else _stream_size(stream)
    enforce_budget(specs, total, max_bytes)
    return tuple(
        read_range(
            stream,
            start,
            end - start,
            total_size=total,
            max_bytes=max_bytes,
            chunk_size=chunk_size,
        )
        for start, end in satisfy_ranges(specs, total)
    )


def format_content_range(start: int, end: int, size: int) -> str:
    """Format a content-range header value."""
    return f"bytes {start}-{max(start, end - 1)}/{size}"


def _stream_size(stream: BinaryIO) -> int:
    """Return the length of a seekable stream without consuming it."""
    current = stream.tell()
    stream.seek(0, 2)
    total = stream.tell()
    stream.seek(current, 0)
    return total
