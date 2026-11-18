"""Checksum utilities for snapshot integrity and verification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from redscribe.v2.sync.errors import ChecksumError, ValidationError


def checksum_bytes(data: bytes, algorithm: str = "sha256") -> str:
    """Return a hex digest for raw bytes."""
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:
        raise ValidationError(f"Unsupported checksum algorithm: {algorithm}") from exc
    digest.update(data)
    return digest.hexdigest()


def checksum_text(text: str, algorithm: str = "sha256") -> str:
    """Return a hex digest for UTF-8 text."""
    return checksum_bytes(text.encode("utf-8"), algorithm=algorithm)


def checksum_file(path: str | Path, algorithm: str = "sha256") -> str:
    """Stream a file and return its hex digest."""
    source = Path(path)
    if not source.is_file():
        raise ValidationError(f"Checksum source is not a file: {source}")
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:
        raise ValidationError(f"Unsupported checksum algorithm: {algorithm}") from exc
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    """Serialize JSON with stable ordering for deterministic checksums."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def checksum_json(value: Any, algorithm: str = "sha256") -> str:
    """Return a digest for a canonical JSON payload."""
    return checksum_text(canonical_json(value), algorithm=algorithm)


def normalize_checksum_map(values: Mapping[str, Any] | None) -> dict[str, str]:
    """Normalize a mapping of path -> checksum strings."""
    result: dict[str, str] = {}
    for key, value in (values or {}).items():
        path = str(key).strip().replace("\\", "/")
        if not path:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"Invalid checksum for {path}")
        result[path] = value.strip()
    return dict(sorted(result.items()))


@dataclass(slots=True)
class ChecksumReport:
    """Result of comparing expected and actual checksums."""

    algorithm: str
    expected: dict[str, str] = field(default_factory=dict)
    actual: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    mismatched: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.missing and not self.extra and not self.mismatched

    def as_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "ok": self.ok,
            "expected": dict(self.expected),
            "actual": dict(self.actual),
            "missing": list(self.missing),
            "extra": list(self.extra),
            "mismatched": {key: dict(value) for key, value in self.mismatched.items()},
            "counts": {
                "expected": len(self.expected),
                "actual": len(self.actual),
                "missing": len(self.missing),
                "extra": len(self.extra),
                "mismatched": len(self.mismatched),
            },
        }


class ChecksumVerifier:
    """Verify checksum manifests and file trees."""

    def __init__(self, algorithm: str = "sha256") -> None:
        self.algorithm = algorithm

    def compare(
        self,
        expected: Mapping[str, Any],
        actual: Mapping[str, Any],
        *,
        allow_extra: bool = False,
    ) -> ChecksumReport:
        expected_map = normalize_checksum_map(expected)
        actual_map = normalize_checksum_map(actual)
        missing = [path for path in expected_map if path not in actual_map]
        extra = [path for path in actual_map if path not in expected_map]
        if allow_extra:
            extra = []
        mismatched: dict[str, dict[str, str]] = {}
        for path, digest in expected_map.items():
            current = actual_map.get(path)
            if current is None:
                continue
            if current != digest:
                mismatched[path] = {"expected": digest, "actual": current}
        return ChecksumReport(
            algorithm=self.algorithm,
            expected=expected_map,
            actual=actual_map,
            missing=sorted(missing),
            extra=sorted(extra),
            mismatched=dict(sorted(mismatched.items())),
        )

    def require(
        self,
        expected: Mapping[str, Any],
        actual: Mapping[str, Any],
        *,
        allow_extra: bool = False,
        context: str = "checksum verification",
    ) -> ChecksumReport:
        report = self.compare(expected, actual, allow_extra=allow_extra)
        if not report.ok:
            raise ChecksumError(
                f"{context} failed",
                details=report.as_dict(),
            )
        return report

    def verify_files(
        self,
        root: str | Path,
        expected: Mapping[str, Any],
        *,
        allow_extra: bool = False,
    ) -> ChecksumReport:
        base = Path(root)
        if not base.exists():
            raise ValidationError(f"Checksum root does not exist: {base}")
        actual: dict[str, str] = {}
        for relative in expected:
            path = base / relative
            if path.is_file():
                actual[relative] = checksum_file(path, algorithm=self.algorithm)
        return self.require(expected, actual, allow_extra=allow_extra, context="file checksums")

    def file_map(self, root: str | Path, files: Iterable[str]) -> dict[str, str]:
        base = Path(root)
        result: dict[str, str] = {}
        for relative in files:
            path = base / relative
            if path.is_file():
                result[str(relative).replace("\\", "/")] = checksum_file(
                    path, algorithm=self.algorithm
                )
        return dict(sorted(result.items()))
