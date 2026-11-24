"""Tests for chunked hex dump generation and offset navigation."""

from __future__ import annotations

from io import BytesIO

import pytest

from redscribe.v3.evidence_lab.errors import InvalidInputError
from redscribe.v3.evidence_lab.hexdump import (
    ascii_for_bytes,
    build_hex_window,
    find_row_at_offset,
    format_hex_row,
    format_offset,
    hex_dump_bytes,
    iter_hex_rows,
    normalize_selection,
    offset_for_row_index,
    read_bounded,
    row_index_for_offset,
    slice_rows,
    stream_size,
)


def test_ascii_and_offset_formatting() -> None:
    assert ascii_for_bytes(b"AB\x00\xffz") == "AB..z"
    assert format_offset(0) == "00000000"
    assert format_offset(0x1A, width=4) == "001a"
    with pytest.raises(InvalidInputError):
        format_offset(-1)


def test_hex_row_rendering() -> None:
    row = format_hex_row(b"\x00\x0f\x10\x7f", 0x20, bytes_per_row=8)
    assert row.offset == 0x20
    assert row.cells == ("00", "0f", "10", "7f")
    assert row.ascii_text.startswith("....")
    assert row.ascii_text.endswith("    ")
    assert row.byte_count == 4
    assert row.end_offset == 0x24
    assert row.as_dict()["offset_hex"] == "00000020"
    with pytest.raises(InvalidInputError):
        format_hex_row(b"x", 0, bytes_per_row=0)


def test_selection_normalization() -> None:
    assert normalize_selection(None, 4) is None
    assert normalize_selection(9, 3) == (3, 9)
    assert normalize_selection(2, 2) == (2, 2)
    with pytest.raises(InvalidInputError):
        normalize_selection(-1, 5)


def test_offset_row_conversions() -> None:
    assert row_index_for_offset(33, bytes_per_row=16) == 2
    assert offset_for_row_index(2, bytes_per_row=16) == 32
    with pytest.raises(InvalidInputError):
        row_index_for_offset(-1)


def test_stream_size_does_not_move_cursor() -> None:
    with BytesIO(b"abcdef") as stream:
        stream.seek(2)
        assert stream_size(stream) == 6
        assert stream.tell() == 2


def test_read_bounded_is_length_limited() -> None:
    with BytesIO(bytes(range(256))) as stream:
        data, truncated = read_bounded(stream, 250, 20, chunk_size=8)
        assert len(data) == 6
        assert truncated is True
        assert data == bytes(range(250, 256))


def test_hex_window_offsets_and_ascii() -> None:
    data = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    window = hex_dump_bytes(data, bytes_per_row=8)
    assert window.total_bytes == 26
    assert window.length == 26
    assert len(window.rows) == 4
    assert window.rows[0].cells == tuple(f"{byte:02x}" for byte in b"ABCDEFGH")
    assert window.rows[0].ascii_text == "ABCDEFGH"
    assert window.rows[-1].ascii_text.startswith("YZ")
    assert window.as_dict()["rows"][0]["offset_hex"] == "00000000"


def test_hex_window_start_offset_and_selection() -> None:
    data = bytes(range(64))
    window = hex_dump_bytes(data, start=16, bytes_per_row=16, selection=(20, 25))
    assert window.start == 16
    assert window.rows[0].offset == 16
    assert window.rows[0].selected is True
    assert window.rows[1].selected is False
    assert len(window.selected_rows) == 1
    assert window.as_dict()["selection_start"] == 20


def test_build_hex_window_enforces_budget() -> None:
    with BytesIO(bytes(range(256))) as stream:
        window = build_hex_window(stream, length=256, max_window_bytes=32)
        assert window.length == 32
        assert window.truncated is True
        assert window.total_bytes == 256


def test_build_hex_window_past_eof() -> None:
    with BytesIO(b"abc") as stream:
        window = build_hex_window(stream, start=100, length=8)
        assert window.start == 3
        assert window.length == 0
        assert window.rows == ()
        assert window.truncated is True


def test_find_row_and_slice_rows() -> None:
    window = hex_dump_bytes(bytes(range(40)), bytes_per_row=8)
    row = find_row_at_offset(window, 9)
    assert row is not None
    assert row.offset == 8
    assert find_row_at_offset(window, 400) is None
    sliced = slice_rows(window, 1, 2)
    assert sliced.start == 8
    assert sliced.length == 16
    assert len(sliced.rows) == 2


def test_iter_hex_rows_streams_incrementally() -> None:
    with BytesIO(bytes(range(100))) as stream:
        rows = list(iter_hex_rows(stream, start=0, length=100, bytes_per_row=16, chunk_size=7))
    assert sum(row.byte_count for row in rows) == 100
    assert rows[0].offset == 0
    assert rows[-1].end_offset == 100


def test_iter_hex_rows_respects_start_and_selection() -> None:
    with BytesIO(bytes(range(64))) as stream:
        rows = list(
            iter_hex_rows(
                stream,
                start=10,
                length=20,
                bytes_per_row=8,
                chunk_size=4,
                selection=(12, 14),
            )
        )
    assert rows[0].offset == 10
    assert sum(1 for row in rows if row.selected) == 1
    assert sum(row.byte_count for row in rows) == 20
