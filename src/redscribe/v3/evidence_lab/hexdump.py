"""Chunked hexadecimal dump generation over file-like objects.

Every reader in this module uses ``seek``/``read`` with an explicit byte budget.
A caller asking for a 64 KiB window of a 100 MiB file allocates only that window;
no function here ever calls ``stream.read()`` without a size limit.
"""

from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from typing import BinaryIO

from redscribe.v3.evidence_lab.errors import InvalidInputError
from redscribe.v3.evidence_lab.types import (
    DEFAULT_BYTES_PER_ROW,
    DEFAULT_CHUNK_SIZE,
    HexRow,
    HexWindow,
)

MIN_PRINTABLE = 0x20
MAX_PRINTABLE = 0x7E


def validate_positive(value: int, name: str) -> int:
    """Validate a strictly positive integer parameter."""
    if value < 1:
        raise InvalidInputError(f"{name} must be positive", context={"value": value})
    return value


def validate_non_negative(value: int, name: str) -> int:
    """Validate a non-negative integer parameter."""
    if value < 0:
        raise InvalidInputError(f"{name} cannot be negative", context={"value": value})
    return value


def ascii_for_bytes(data: bytes) -> str:
    """Render bytes as printable ASCII, replacing others with a dot."""
    return "".join(chr(byte) if MIN_PRINTABLE <= byte <= MAX_PRINTABLE else "." for byte in data)


def format_offset(offset: int, *, width: int = 8) -> str:
    """Format a byte offset as fixed-width lowercase hexadecimal."""
    validate_non_negative(offset, "offset")
    return f"{offset:0{width}x}"


def format_hex_row(
    data: bytes,
    offset: int,
    *,
    bytes_per_row: int = DEFAULT_BYTES_PER_ROW,
    selected: bool = False,
) -> HexRow:
    """Render a single row of hex cells and its ASCII gutter."""
    validate_positive(bytes_per_row, "bytes_per_row")
    cells = tuple(f"{byte:02x}" for byte in data[:bytes_per_row])
    padded = data[:bytes_per_row] + b" " * (bytes_per_row - len(data[:bytes_per_row]))
    return HexRow(offset=offset, cells=cells, ascii_text=ascii_for_bytes(padded), selected=selected)


def normalize_selection(start: int | None, end: int | None) -> tuple[int, int] | None:
    """Normalize an inclusive byte selection, returning ``None`` when absent."""
    if start is None or end is None:
        return None
    validate_non_negative(start, "selection_start")
    validate_non_negative(end, "selection_end")
    return (min(start, end), max(start, end))


def selection_touches_row(row: HexRow, selection: tuple[int, int] | None) -> bool:
    """Return whether a row intersects a byte selection."""
    if selection is None:
        return False
    low, high = selection
    return row.offset <= high and row.end_offset >= low


def row_index_for_offset(offset: int, *, bytes_per_row: int = DEFAULT_BYTES_PER_ROW) -> int:
    """Return the zero-based row index containing an offset."""
    validate_non_negative(offset, "offset")
    validate_positive(bytes_per_row, "bytes_per_row")
    return offset // bytes_per_row


def offset_for_row_index(index: int, *, bytes_per_row: int = DEFAULT_BYTES_PER_ROW) -> int:
    """Return the starting offset of a row index."""
    validate_non_negative(index, "row_index")
    validate_positive(bytes_per_row, "bytes_per_row")
    return index * bytes_per_row


def stream_size(stream: BinaryIO) -> int:
    """Return the total byte length of a seekable stream without reading it."""
    current = stream.tell()
    stream.seek(0, 2)
    total = stream.tell()
    stream.seek(current, 0)
    return total


def read_bounded(
    stream: BinaryIO,
    start: int,
    length: int,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> tuple[bytes, bool]:
    """Read at most ``length`` bytes from ``start`` in bounded chunks.

    Returns the bytes and whether the requested range ran past end-of-file.
    """
    validate_non_negative(start, "start")
    validate_non_negative(length, "length")
    validate_positive(chunk_size, "chunk_size")
    stream.seek(start, 0)
    parts: list[bytes] = []
    remaining = length
    while remaining > 0:
        chunk = stream.read(min(chunk_size, remaining))
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise InvalidInputError("Binary streams must return bytes")
        parts.append(chunk)
        remaining -= len(chunk)
    return b"".join(parts), remaining > 0


def iter_hex_rows(
    stream: BinaryIO,
    *,
    start: int = 0,
    length: int | None = None,
    bytes_per_row: int = DEFAULT_BYTES_PER_ROW,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    selection: tuple[int, int] | None = None,
) -> Iterator[HexRow]:
    """Yield hex rows incrementally without materializing the whole stream."""
    validate_positive(bytes_per_row, "bytes_per_row")
    total = stream_size(stream)
    begin = min(validate_non_negative(start, "start"), total)
    span = (
        total - begin
        if length is None
        else min(validate_non_negative(length, "length"), total - begin)
    )
    span = max(0, span)
    stream.seek(begin, 0)
    pending = bytearray()
    emitted = 0
    remaining = span
    while remaining > 0:
        chunk = stream.read(min(chunk_size, remaining))
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise InvalidInputError("Binary streams must return bytes")
        pending.extend(chunk)
        remaining -= len(chunk)
        while len(pending) >= bytes_per_row:
            raw = bytes(pending[:bytes_per_row])
            del pending[:bytes_per_row]
            absolute = begin + emitted * bytes_per_row
            emitted += 1
            row = HexRow(absolute, tuple(f"{byte:02x}" for byte in raw), "", False)
            yield format_hex_row(
                raw,
                absolute,
                bytes_per_row=bytes_per_row,
                selected=selection_touches_row(row, selection),
            )
    if pending:
        absolute = begin + emitted * bytes_per_row
        row = HexRow(absolute, tuple(f"{byte:02x}" for byte in pending), "", False)
        yield format_hex_row(
            bytes(pending),
            absolute,
            bytes_per_row=bytes_per_row,
            selected=selection_touches_row(row, selection),
        )


def build_hex_window(
    stream: BinaryIO,
    *,
    start: int = 0,
    length: int = DEFAULT_BYTES_PER_ROW * 32,
    bytes_per_row: int = DEFAULT_BYTES_PER_ROW,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    max_window_bytes: int = 4 * 1024 * 1024,
    total_bytes: int | None = None,
    selection: tuple[int, int] | None = None,
) -> HexWindow:
    """Build a bounded hex window from a seekable stream."""
    validate_non_negative(start, "start")
    validate_positive(length, "length")
    validate_positive(bytes_per_row, "bytes_per_row")
    validate_positive(max_window_bytes, "max_window_bytes")
    bounded_length = min(length, max_window_bytes)
    total = stream_size(stream) if total_bytes is None else total_bytes
    begin = min(start, total)
    data, hit_eof = read_bounded(stream, begin, bounded_length, chunk_size=chunk_size)
    rows: list[HexRow] = []
    for index in range(0, len(data), bytes_per_row):
        raw = data[index : index + bytes_per_row]
        absolute = begin + index
        row = HexRow(absolute, tuple(f"{byte:02x}" for byte in raw), "", False)
        rows.append(
            format_hex_row(
                raw,
                absolute,
                bytes_per_row=bytes_per_row,
                selected=selection_touches_row(row, selection),
            )
        )
    return HexWindow(
        start=begin,
        length=len(data),
        bytes_per_row=bytes_per_row,
        rows=tuple(rows),
        total_bytes=total,
        truncated=hit_eof or begin + len(data) < total,
        selection_start=selection[0] if selection else None,
        selection_end=selection[1] if selection else None,
    )


def hex_dump_bytes(
    data: bytes,
    *,
    start: int = 0,
    bytes_per_row: int = DEFAULT_BYTES_PER_ROW,
    selection: tuple[int, int] | None = None,
) -> HexWindow:
    """Build a hex window from an in-memory byte string."""
    with BytesIO(data) as stream:
        return build_hex_window(
            stream,
            start=start,
            length=len(data),
            bytes_per_row=bytes_per_row,
            selection=selection,
        )


def find_row_at_offset(window: HexWindow, offset: int) -> HexRow | None:
    """Find the row containing a byte offset inside a window."""
    for row in window.rows:
        if row.offset <= offset < row.end_offset:
            return row
    return None


def slice_rows(window: HexWindow, first_row: int, row_count: int) -> HexWindow:
    """Return a sub-window containing a slice of rows."""
    validate_non_negative(first_row, "first_row")
    validate_positive(row_count, "row_count")
    rows = window.rows[first_row : first_row + row_count]
    start = rows[0].offset if rows else window.start
    length = sum(row.byte_count for row in rows)
    return HexWindow(
        start=start,
        length=length,
        bytes_per_row=window.bytes_per_row,
        rows=rows,
        total_bytes=window.total_bytes,
        truncated=window.truncated,
        selection_start=window.selection_start,
        selection_end=window.selection_end,
    )
