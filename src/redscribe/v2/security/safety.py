"""URL and command safety checks for operator workflows."""

from __future__ import annotations

import ipaddress
import re
import shlex
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class UrlSafety:
    url: str
    safe: bool
    scheme: str
    host: str
    reasons: tuple[str, ...]
    risk: str

    def as_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "safe": self.safe,
            "scheme": self.scheme,
            "host": self.host,
            "reasons": list(self.reasons),
            "risk": self.risk,
        }


@dataclass(frozen=True, slots=True)
class CommandSafety:
    command: str
    safe: bool
    risk: str
    reasons: tuple[str, ...]
    tokens: tuple[str, ...]
    destructive: bool = False
    networked: bool = False
    privileged: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "safe": self.safe,
            "risk": self.risk,
            "reasons": list(self.reasons),
            "tokens": list(self.tokens),
            "destructive": self.destructive,
            "networked": self.networked,
            "privileged": self.privileged,
        }


_SAFE_SCHEMES = {"https", "http"}
_BLOCKED_SCHEMES = {"file", "javascript", "data", "vbscript"}
_SUSPICIOUS_HOST_RE = re.compile(r"^[0-9a-f:.]+$", re.IGNORECASE)

_DANGEROUS_PATTERNS = (
    (re.compile(r"\brm\s+-rf\b"), "recursive delete", "high", "destructive"),
    (re.compile(r"\bmkfs\b|\bdd\s+if="), "disk or filesystem write", "high", "destructive"),
    (
        re.compile(r"\bshutdown\b|\breboot\b|\bpoweroff\b"),
        "system power action",
        "high",
        "destructive",
    ),
    (
        re.compile(r"\bcurl\b[^\n|]*\|\s*(?:bash|sh)\b"),
        "remote script piped to shell",
        "critical",
        "networked",
    ),
    (
        re.compile(r"\bwget\b[^\n|]*\|\s*(?:bash|sh)\b"),
        "remote script piped to shell",
        "critical",
        "networked",
    ),
    (re.compile(r"\bchmod\s+777\b"), "overly permissive permissions", "medium", "destructive"),
    (re.compile(r"\bsudo\b"), "privileged execution", "medium", "privileged"),
    (re.compile(r"\bnc\b|\bncat\b|\bsocat\b"), "network socket utility", "medium", "networked"),
    (re.compile(r"\bssh\b"), "remote access command", "low", "networked"),
    (re.compile(r"\bscp\b|\brsync\b"), "remote transfer command", "low", "networked"),
    (re.compile(r">\s*/etc/"), "writes to system configuration", "high", "destructive"),
)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _risk_from_reasons(reasons: list[str], *, critical: bool = False, high: bool = False) -> str:
    if critical:
        return "critical"
    if high or len(reasons) >= 2:
        return "high" if high else "medium"
    if reasons:
        return "medium" if len(reasons) > 1 else "low"
    return "none"


def _is_local_host(host: str) -> bool:
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def analyze_url(
    url: str,
    *,
    allowed_schemes: set[str] | None = None,
    allow_localhost: bool = True,
    allow_private_networks: bool = False,
) -> UrlSafety:
    """Analyze a URL and return a conservative safety assessment."""
    if not isinstance(url, str) or not url.strip():
        return UrlSafety(
            url=str(url), safe=False, scheme="", host="", reasons=("empty_url",), risk="medium"
        )
    raw = url.strip()
    reasons: list[str] = []
    if _CONTROL_CHARS_RE.search(raw):
        reasons.append("control_characters")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if scheme in _BLOCKED_SCHEMES:
        reasons.append(f"blocked_scheme:{scheme}")
    allowed = {item.lower() for item in (allowed_schemes or _SAFE_SCHEMES)}
    if scheme and scheme not in allowed and scheme not in _BLOCKED_SCHEMES:
        reasons.append(f"disallowed_scheme:{scheme}")
    if not scheme:
        reasons.append("missing_scheme")
    if not host and scheme in {"http", "https"}:
        reasons.append("missing_host")
    if parsed.username or parsed.password:
        reasons.append("embedded_credentials")
    if host:
        if _is_local_host(host) and not allow_localhost:
            reasons.append("localhost_target")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        if ip is not None:
            if ip.is_private and not allow_private_networks:
                reasons.append("private_network_target")
            if ip.is_link_local:
                reasons.append("link_local_target")
            if ip.is_multicast:
                reasons.append("multicast_target")
        elif host.count(".") == 0 and host not in {"localhost"}:
            reasons.append("unqualified_host")
        if "xn--" in host:
            reasons.append("punycode_host")
    if raw.count("@") > 1:
        reasons.append("multiple_at_signs")
    if len(raw) > 2048:
        reasons.append("url_too_long")
    risk = _risk_from_reasons(
        reasons,
        critical=any(reason.startswith("blocked_scheme") for reason in reasons),
        high=any("credential" in reason or "private" in reason for reason in reasons),
    )
    safe = not reasons
    return UrlSafety(
        url=raw, safe=safe, scheme=scheme, host=host, reasons=tuple(reasons), risk=risk
    )


def is_safe_url(url: str, **kwargs: object) -> bool:
    return analyze_url(url, **kwargs).safe  # type: ignore[arg-type]


def analyze_command(command: object) -> CommandSafety:
    """Analyze a shell command string for risky patterns."""
    if not isinstance(command, str):
        command = str(command)
    text = command.strip()
    reasons: list[str] = []
    destructive = False
    networked = False
    privileged = False
    critical = False
    high = False
    if not text:
        return CommandSafety(
            command=text, safe=False, risk="medium", reasons=("empty_command",), tokens=()
        )
    if _CONTROL_CHARS_RE.search(text):
        reasons.append("control_characters")
        high = True
    lowered = text.lower()
    for pattern, reason, severity, flag in _DANGEROUS_PATTERNS:
        if pattern.search(lowered):
            reasons.append(reason)
            if severity == "critical":
                critical = True
            if severity in {"critical", "high"}:
                high = True
            if flag == "destructive":
                destructive = True
            if flag == "networked":
                networked = True
            if flag == "privileged":
                privileged = True
    if "&&" in text or ";" in text:
        reasons.append("chained_commands")
    if "|" in text:
        reasons.append("pipeline")
    if "`" in text or "$(" in text:
        reasons.append("command_substitution")
        high = True
    if re.search(r">\s*\S+", text):
        reasons.append("output_redirection")
    try:
        tokens = tuple(shlex.split(text, posix=True))
    except ValueError:
        tokens = tuple(text.split())
        reasons.append("unbalanced_quotes")
        high = True
    if len(tokens) > 64:
        reasons.append("excessive_arguments")
    risk = _risk_from_reasons(reasons, critical=critical, high=high)
    safe = not reasons
    return CommandSafety(
        command=text,
        safe=safe,
        risk=risk,
        reasons=tuple(dict.fromkeys(reasons)),
        tokens=tokens,
        destructive=destructive,
        networked=networked,
        privileged=privileged,
    )


def is_safe_command(command: str) -> bool:
    return analyze_command(command).safe
