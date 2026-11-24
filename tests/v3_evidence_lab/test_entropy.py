"""Tests for entropy estimation."""

from __future__ import annotations

from io import BytesIO

import pytest

from redscribe.v3.evidence_lab.entropy import (
    build_buckets,
    byte_histogram,
    entropy_bucket_total,
    entropy_delta,
    entropy_from_histogram,
    entropy_profile,
    estimate_stream_entropy,
    normalized_entropy,
    rolling_entropy,
    shannon_entropy,
)
from redscribe.v3.evidence_lab.errors import InvalidInputError


def test_shannon_entropy_known_values() -> None:
    assert shannon_entropy(b"") == 0.0
    assert shannon_entropy(b"aaaaaaaa") == 0.0
    assert shannon_entropy(b"ab") == 1.0
    assert round(shannon_entropy(b"abcd"), 6) == 2.0
    assert round(shannon_entropy(bytes(range(256))), 6) == 8.0


def test_histogram_and_from_histogram() -> None:
    hist = byte_histogram(b"aab")
    assert len(hist) == 256
    assert hist[ord("a")] == 2
    assert hist[ord("b")] == 1
    assert round(entropy_from_histogram(hist), 6) == round(shannon_entropy(b"aab"), 6)
    assert entropy_from_histogram([0] * 256, 0) == 0.0
    with pytest.raises(InvalidInputError):
        entropy_from_histogram([0] * 4)


def test_normalized_and_classification() -> None:
    assert normalized_entropy(b"") == 0.0
    assert normalized_entropy(b"a" * 64) == 0.0
    assert normalized_entropy(bytes(range(256))) == 1.0
    assert entropy_profile(b"a" * 64).classification == "empty"
    assert entropy_profile(bytes(range(256))).classification == "random"


def test_entropy_report_buckets() -> None:
    report = entropy_profile(bytes(range(256)))
    assert len(report.histogram) == 256
    assert len(report.buckets) == 8
    assert sum(bucket.count for bucket in report.buckets) == 256
    assert report.buckets[0].high - report.buckets[0].low >= 0
    assert entropy_bucket_total(report, "empty") == 32
    assert report.as_dict()["normalized"] == 1.0


def test_entropy_report_from_stream_is_bounded() -> None:
    with BytesIO(bytes(range(256)) * 8) as stream:
        report = estimate_stream_entropy(stream, max_bytes=256, chunk_size=64, total_bytes=2048)
    assert report.sample_bytes == 256
    assert report.total_bytes == 2048
    assert report.truncated is True
    assert report.normalized == 1.0


def test_entropy_report_past_eof() -> None:
    with BytesIO(b"abc") as stream:
        report = estimate_stream_entropy(stream, max_bytes=64)
    assert report.sample_bytes == 3
    assert report.truncated is False


def test_rolling_entropy() -> None:
    values = rolling_entropy(bytes(range(256)), window=16, step=8)
    assert len(values) > 1
    assert all(value == pytest.approx(4.0) for value in values)
    with pytest.raises(InvalidInputError):
        rolling_entropy(b"abcd", window=1)


def test_entropy_delta() -> None:
    low = entropy_profile(b"a" * 256)
    high = entropy_profile(bytes(range(256)))
    assert entropy_delta(low, high) == 1.0
    assert entropy_delta(high, low) == -1.0


def test_entropy_invalid_parameters() -> None:
    with BytesIO(b"abc") as stream:
        with pytest.raises(InvalidInputError):
            estimate_stream_entropy(stream, max_bytes=0)
        with pytest.raises(InvalidInputError):
            estimate_stream_entropy(stream, chunk_size=0)
    with pytest.raises(InvalidInputError):
        build_buckets([0] * 256, 0, count=0)
