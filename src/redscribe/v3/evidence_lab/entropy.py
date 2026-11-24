"""Shannon entropy estimation over bounded byte samples.

Entropy is computed from a 256-bin histogram, so memory use is constant
regardless of the file size. Streaming calls read a fixed prefix in chunks and
never retain the bytes after a bin has been incremented.
"""

from __future__ import annotations

import math
from typing import BinaryIO

from redscribe.v3.evidence_lab.errors import InvalidInputError
from redscribe.v3.evidence_lab.types import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_ENTROPY_SAMPLE,
    ENTROPY_BUCKET_LABELS,
    EntropyBucket,
    EntropyReport,
)

HISTOGRAM_BINS = 256
MAX_ENTROPY = 8.0


def byte_histogram(data: bytes, *, base: int = 0) -> list[int]:
    """Build a 256-bin byte histogram, optionally offsetting every bin."""
    histogram = [base] * HISTOGRAM_BINS
    for byte in data:
        histogram[byte] += 1
    return histogram


def entropy_from_histogram(histogram: list[int], total: int | None = None) -> float:
    """Compute Shannon entropy in bits per byte from a histogram."""
    if len(histogram) != HISTOGRAM_BINS:
        raise InvalidInputError("Histogram must contain 256 bins")
    count = total if total is not None else sum(histogram)
    if count <= 0:
        return 0.0
    entropy = 0.0
    for frequency in histogram:
        if frequency <= 0:
            continue
        probability = frequency / count
        entropy -= probability * math.log2(probability)
    return entropy


def shannon_entropy(data: bytes) -> float:
    """Return Shannon entropy of a byte string."""
    return entropy_from_histogram(byte_histogram(data))


def normalized_entropy(data: bytes) -> float:
    """Return entropy normalized to the 0..1 range."""
    if not data:
        return 0.0
    return min(1.0, shannon_entropy(data) / MAX_ENTROPY)


def classify_entropy(normalized: float) -> str:
    """Map a normalized entropy value to a human-readable band."""
    if normalized <= 0.02:
        return "empty"
    if normalized < 0.25:
        return "very_low"
    if normalized < 0.5:
        return "low"
    if normalized < 0.7:
        return "medium"
    if normalized < 0.85:
        return "high"
    if normalized < 0.95:
        return "very_high"
    return "random"


def build_buckets(histogram: list[int], total: int, *, count: int = 8) -> tuple[EntropyBucket, ...]:
    """Group histogram bins into evenly spaced chart buckets."""
    if count < 1:
        raise InvalidInputError("Bucket count must be positive")
    width = HISTOGRAM_BINS / count
    buckets: list[EntropyBucket] = []
    for index in range(count):
        low = int(index * width)
        high = int((index + 1) * width) - 1
        label = ENTROPY_BUCKET_LABELS[index] if index < len(ENTROPY_BUCKET_LABELS) else f"b{index}"
        buckets.append(EntropyBucket(label, low, high, sum(histogram[low : high + 1])))
    return tuple(buckets)


def make_report(
    histogram: list[int],
    sample_bytes: int,
    total_bytes: int,
    *,
    truncated: bool = False,
) -> EntropyReport:
    """Assemble an entropy report from a histogram."""
    entropy = entropy_from_histogram(histogram, sample_bytes)
    normalized = min(1.0, entropy / MAX_ENTROPY) if sample_bytes else 0.0
    return EntropyReport(
        sample_bytes=sample_bytes,
        total_bytes=total_bytes,
        entropy=entropy,
        normalized=normalized,
        histogram=tuple(histogram),
        classification=classify_entropy(normalized),
        buckets=build_buckets(histogram, sample_bytes),
        truncated=truncated,
    )


def entropy_profile(data: bytes, *, total_bytes: int | None = None) -> EntropyReport:
    """Build an entropy report from an in-memory byte string."""
    total = len(data) if total_bytes is None else total_bytes
    return make_report(byte_histogram(data), len(data), total, truncated=total > len(data))


def estimate_stream_entropy(
    stream: BinaryIO,
    *,
    max_bytes: int = DEFAULT_ENTROPY_SAMPLE,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    total_bytes: int | None = None,
) -> EntropyReport:
    """Estimate entropy from a bounded prefix of a seekable stream."""
    if max_bytes < 1:
        raise InvalidInputError("max_bytes must be positive")
    if chunk_size < 1:
        raise InvalidInputError("chunk_size must be positive")
    histogram = [0] * HISTOGRAM_BINS
    sampled = 0
    truncated = False
    while sampled < max_bytes:
        chunk = stream.read(min(chunk_size, max_bytes - sampled))
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            raise InvalidInputError("Binary streams must return bytes")
        for byte in chunk:
            histogram[byte] += 1
        sampled += len(chunk)
        if sampled >= max_bytes:
            truncated = True
    total = total_bytes if total_bytes is not None else sampled
    return make_report(histogram, sampled, total, truncated=truncated)


def rolling_entropy(
    data: bytes, *, window: int = 256, step: int | None = None
) -> tuple[float, ...]:
    """Compute sliding-window entropy values for a byte string."""
    if window < 2:
        raise InvalidInputError("window must be at least 2")
    stride = step or window
    if stride < 1:
        raise InvalidInputError("step must be positive")
    values: list[float] = []
    for start in range(0, max(1, len(data) - window + 1), stride):
        segment = data[start : start + window]
        if len(segment) < window:
            break
        values.append(shannon_entropy(segment))
    return tuple(values)


def entropy_delta(left: EntropyReport, right: EntropyReport) -> float:
    """Return the signed difference in normalized entropy."""
    return round(right.normalized - left.normalized, 6)


def entropy_bucket_total(report: EntropyReport, label: str) -> int:
    """Return the sample count for one named bucket."""
    for bucket in report.buckets:
        if bucket.label == label:
            return bucket.count
    return 0
