"""Secret detection helpers for notes, exports, and operator input."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

Severity = str


@dataclass(frozen=True, slots=True)
class SecretPattern:
    """A named detector used to identify likely secrets in text."""

    name: str
    pattern: re.Pattern[str]
    severity: Severity = "high"
    description: str = ""
    tags: tuple[str, ...] = ()
    entropy_hint: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "regex": self.pattern.pattern,
            "severity": self.severity,
            "description": self.description,
            "tags": list(self.tags),
            "entropy_hint": self.entropy_hint,
        }


@dataclass(frozen=True, slots=True)
class SecretFinding:
    """One detected secret candidate with location and confidence metadata."""

    name: str
    severity: Severity
    start: int
    end: int
    line: int
    column: int
    value: str
    masked: str
    confidence: float
    tags: tuple[str, ...] = field(default_factory=tuple)
    context: str = ""

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity,
            "start": self.start,
            "end": self.end,
            "line": self.line,
            "column": self.column,
            "length": self.length,
            "value": self.value,
            "masked": self.masked,
            "confidence": round(self.confidence, 4),
            "tags": list(self.tags),
            "context": self.context,
        }


@dataclass(frozen=True, slots=True)
class SecretScanResult:
    """Aggregate output of a secret scan over one text payload."""

    findings: tuple[SecretFinding, ...]
    scanned_characters: int
    scanned_lines: int
    pattern_count: int
    entropy_flagged: int = 0

    @property
    def count(self) -> int:
        return len(self.findings)

    @property
    def highest_severity(self) -> Severity:
        return _highest_severity(item.severity for item in self.findings)

    def by_name(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.name] = counts.get(finding.name, 0) + 1
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "highest_severity": self.highest_severity,
            "scanned_characters": self.scanned_characters,
            "scanned_lines": self.scanned_lines,
            "pattern_count": self.pattern_count,
            "entropy_flagged": self.entropy_flagged,
            "by_name": self.by_name(),
            "findings": [finding.as_dict() for finding in self.findings],
        }


_PATTERNS: tuple[SecretPattern, ...] = (
    SecretPattern(
        "aws_access_key_id",
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "critical",
        "Amazon Web Services access key identifier.",
        ("cloud", "aws", "credential"),
    ),
    SecretPattern(
        "aws_secret_access_key",
        re.compile(
            r"(?i)\b(?:aws[_-]?secret(?:[_-]?access)?[_-]?key|secret)\b\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"
        ),
        "critical",
        "Amazon Web Services secret access key assignment.",
        ("cloud", "aws", "credential"),
    ),
    SecretPattern(
        "github_token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
        "critical",
        "GitHub personal or app token.",
        ("scm", "github", "token"),
    ),
    SecretPattern(
        "gitlab_token",
        re.compile(r"\bglpat-[A-Za-z0-9\-_]{20,}\b"),
        "critical",
        "GitLab personal access token.",
        ("scm", "gitlab", "token"),
    ),
    SecretPattern(
        "slack_token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        "high",
        "Slack API token.",
        ("chat", "slack", "token"),
    ),
    SecretPattern(
        "stripe_secret_key",
        re.compile(r"\b(?:sk_live|rk_live)_[A-Za-z0-9]{16,}\b"),
        "critical",
        "Stripe live secret or restricted key.",
        ("payments", "stripe", "credential"),
    ),
    SecretPattern(
        "google_api_key",
        re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
        "high",
        "Google API key.",
        ("cloud", "google", "token"),
    ),
    SecretPattern(
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "high",
        "JSON Web Token value.",
        ("auth", "jwt", "token"),
    ),
    SecretPattern(
        "private_key_block",
        re.compile(
            r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP)? ?PRIVATE KEY-----"
            r"[\s\S]{20,}?"
            r"-----END (?:RSA|EC|DSA|OPENSSH|PGP)? ?PRIVATE KEY-----"
        ),
        "critical",
        "PEM or armored private key material.",
        ("crypto", "private-key"),
    ),
    SecretPattern(
        "password_assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|passphrase)\b\s*[:=]\s*['\"]?([^\s'\"`,;]{6,})['\"]?"
        ),
        "high",
        "Password or passphrase assignment.",
        ("auth", "password"),
    ),
    SecretPattern(
        "api_key_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|token|secret|client[_-]?secret|access[_-]?token)\b\s*[:=]\s*['\"]?([A-Za-z0-9._\-+/=]{8,})['\"]?"
        ),
        "high",
        "Generic credential assignment.",
        ("credential", "assignment"),
    ),
    SecretPattern(
        "basic_auth_url",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@[^/\s]+", re.IGNORECASE),
        "high",
        "URL containing embedded credentials.",
        ("url", "credential"),
    ),
    SecretPattern(
        "bearer_header",
        re.compile(r"(?i)\bauthorization\b\s*[:=]\s*['\"]?bearer\s+[A-Za-z0-9._\-+/=]{8,}['\"]?"),
        "high",
        "Bearer authorization header value.",
        ("auth", "header"),
    ),
    SecretPattern(
        "ssh_public_key_private_hint",
        re.compile(r"(?i)\bssh-rsa\s+AAAA[0-9A-Za-z+/]{80,}={0,3}\b"),
        "medium",
        "Potentially sensitive SSH material in exported context.",
        ("ssh", "key"),
    ),
    SecretPattern(
        "database_uri",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|mssql):\/\/[^\s'\"<>]+",
            re.IGNORECASE,
        ),
        "high",
        "Database connection URI that may include credentials.",
        ("database", "uri"),
    ),
    SecretPattern(
        "hex_secret",
        re.compile(r"\b[a-f0-9]{32,64}\b", re.IGNORECASE),
        "medium",
        "Long hexadecimal string that may be a key or hash.",
        ("entropy", "hex"),
        3.3,
    ),
    SecretPattern(
        "base64ish_secret",
        re.compile(r"\b[A-Za-z0-9+/]{28,}={0,2}\b"),
        "medium",
        "Long base64-like token that may be sensitive.",
        ("entropy", "base64"),
        4.0,
    ),
)


_SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _highest_severity(values: Iterable[Severity]) -> Severity:
    best = "none"
    best_rank = -1
    for value in values:
        rank = _SEVERITY_ORDER.get(value, 0)
        if rank > best_rank:
            best = value
            best_rank = rank
    return best


def builtin_secret_patterns() -> tuple[SecretPattern, ...]:
    """Return the built-in detector catalog."""
    return _PATTERNS


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    if len(value) <= 16:
        return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def _line_col(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    column = offset + 1 if last_newline < 0 else offset - last_newline
    return line, column


def _context(text: str, start: int, end: int, radius: int = 24) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    snippet = text[left:right].replace("\n", " ")
    return snippet.strip()


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    frequencies: dict[str, int] = {}
    for char in value:
        frequencies[char] = frequencies.get(char, 0) + 1
    entropy = 0.0
    length = len(value)
    for count in frequencies.values():
        probability = count / length
        entropy -= probability * math.log2(probability)
    return entropy


def _confidence(pattern: SecretPattern, value: str) -> float:
    base = {
        "critical": 0.97,
        "high": 0.9,
        "medium": 0.72,
        "low": 0.55,
        "info": 0.4,
    }.get(pattern.severity, 0.5)
    if pattern.entropy_hint > 0:
        entropy = _shannon_entropy(value)
        if entropy >= pattern.entropy_hint + 1.0:
            base = min(0.99, base + 0.15)
        elif entropy >= pattern.entropy_hint:
            base = min(0.95, base + 0.08)
        else:
            base = max(0.3, base - 0.2)
    if len(value) >= 48:
        base = min(0.99, base + 0.03)
    return base


def _candidate_value(match: re.Match[str]) -> str:
    groups = [group for group in match.groups() if isinstance(group, str) and group]
    if groups:
        return groups[-1]
    return match.group(0)


def scan_secrets(
    text: str,
    *,
    patterns: Sequence[SecretPattern] | None = None,
    include_entropy: bool = True,
    context_radius: int = 24,
    max_findings: int = 500,
) -> SecretScanResult:
    """Scan text for likely secrets using regex and entropy heuristics."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if context_radius < 0:
        raise ValueError("context_radius must be non-negative")
    if max_findings < 1:
        raise ValueError("max_findings must be at least 1")

    active_patterns = tuple(patterns) if patterns is not None else _PATTERNS
    findings: list[SecretFinding] = []
    seen: set[tuple[str, int, int, str]] = set()
    entropy_flagged = 0

    for pattern in active_patterns:
        for match in pattern.pattern.finditer(text):
            value = _candidate_value(match)
            if not value:
                continue
            start = match.start(0)
            end = match.end(0)
            if match.groups():
                group_index = match.lastindex or 0
                if group_index:
                    try:
                        start = match.start(group_index)
                        end = match.end(group_index)
                    except IndexError:
                        start = match.start(0)
                        end = match.end(0)
            key = (pattern.name, start, end, value)
            if key in seen:
                continue
            confidence = _confidence(pattern, value)
            if include_entropy and pattern.entropy_hint > 0:
                if _shannon_entropy(value) < pattern.entropy_hint:
                    continue
                entropy_flagged += 1
            line, column = _line_col(text, start)
            findings.append(
                SecretFinding(
                    name=pattern.name,
                    severity=pattern.severity,
                    start=start,
                    end=end,
                    line=line,
                    column=column,
                    value=value,
                    masked=_mask(value),
                    confidence=confidence,
                    tags=pattern.tags,
                    context=_context(text, start, end, context_radius),
                )
            )
            seen.add(key)
            if len(findings) >= max_findings:
                break
        if len(findings) >= max_findings:
            break

    findings.sort(key=lambda item: (item.start, item.end, item.name))
    return SecretScanResult(
        findings=tuple(findings),
        scanned_characters=len(text),
        scanned_lines=text.count("\n") + (1 if text or not findings else 0),
        pattern_count=len(active_patterns),
        entropy_flagged=entropy_flagged,
    )


def patterns_from_names(names: Iterable[str]) -> tuple[SecretPattern, ...]:
    """Select built-in patterns by name."""
    wanted = {name.strip().lower() for name in names if name.strip()}
    if not wanted:
        return _PATTERNS
    selected = tuple(pattern for pattern in _PATTERNS if pattern.name.lower() in wanted)
    return selected or _PATTERNS


def scan_mapping(
    payload: Mapping[str, Any],
    *,
    keys: Sequence[str] | None = None,
    patterns: Sequence[SecretPattern] | None = None,
) -> dict[str, Any]:
    """Scan selected string values inside a mapping payload."""
    selected_keys = list(keys) if keys is not None else [str(key) for key in payload]
    results: dict[str, Any] = {}
    total = 0
    highest = "none"
    for key in selected_keys:
        value = payload.get(key)
        if not isinstance(value, str):
            continue
        result = scan_secrets(value, patterns=patterns)
        results[str(key)] = result.as_dict()
        total += result.count
        if _SEVERITY_ORDER.get(result.highest_severity, -1) > _SEVERITY_ORDER.get(highest, -1):
            highest = result.highest_severity
    return {"count": total, "highest_severity": highest, "fields": results}
