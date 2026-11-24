"""Static invariant: the SDK has no arbitrary code execution path."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from redscribe.v3.api_sdk.errors import SafetyViolationError

FORBIDDEN_IMPORTS: frozenset[str] = frozenset(
    {
        "code",
        "codeop",
        "commands",
        "ctypes",
        "http",
        "importlib",
        "marshal",
        "multiprocessing",
        "os",
        "pickle",
        "pty",
        "requests",
        "runpy",
        "shlex",
        "socket",
        "subprocess",
        "urllib",
        "webbrowser",
    }
)

FORBIDDEN_CALLS: frozenset[str] = frozenset({"__import__", "compile", "eval", "exec", "execfile"})

FORBIDDEN_PATHS: frozenset[str] = frozenset(
    {
        "builtins.eval",
        "builtins.exec",
        "builtins.compile",
        "builtins.__import__",
        "importlib.import_module",
        "importlib.reload",
        "marshal.loads",
        "os.execv",
        "os.execl",
        "os.popen",
        "os.spawnl",
        "os.system",
        "pickle.load",
        "pickle.loads",
        "runpy.run_module",
        "runpy.run_path",
        "socket.socket",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.run",
        "urllib.request.urlopen",
    }
)


@dataclass(frozen=True, slots=True)
class SafetyFinding:
    """One forbidden construct found by the static audit."""

    path: str
    line: int
    symbol: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "path": self.path,
            "line": self.line,
            "symbol": self.symbol,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class SafetyReport:
    """Result of auditing a set of source files."""

    files: tuple[str, ...]
    findings: tuple[SafetyFinding, ...] = ()
    calls_checked: int = 0

    @property
    def clean(self) -> bool:
        """Return whether no forbidden construct was found."""
        return not self.findings

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""
        return {
            "files": list(self.files),
            "clean": self.clean,
            "calls_checked": self.calls_checked,
            "findings": [item.as_dict() for item in self.findings],
        }


def _dotted(node: ast.AST) -> str:
    """Render an attribute chain into a dotted name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


class _AuditVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.findings: list[SafetyFinding] = []
        self.calls_checked = 0

    def _record(self, node: ast.AST, symbol: str, reason: str) -> None:
        self.findings.append(
            SafetyFinding(
                path=self.path,
                line=getattr(node, "lineno", 0),
                symbol=symbol,
                reason=reason,
            )
        )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            if root in FORBIDDEN_IMPORTS:
                self._record(node, alias.name, "runtime or execution import is forbidden")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        root = module.split(".", 1)[0]
        if root in FORBIDDEN_IMPORTS:
            self._record(node, module, "runtime or execution import is forbidden")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        self.calls_checked += 1
        name = _dotted(node.func)
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            self._record(node, node.func.id, "dynamic code execution is forbidden")
        if name in FORBIDDEN_PATHS:
            self._record(node, name, "process, network, or deserialization call is forbidden")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        name = _dotted(node)
        if name in FORBIDDEN_PATHS and not isinstance(getattr(node, "ctx", None), ast.Load):
            self._record(node, name, "execution helper reference is forbidden")
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._record(node, "lambda", "inline code objects are forbidden in the SDK")
        self.generic_visit(node)


def audit_source(path: Path, *, display: str = "") -> tuple[SafetyFinding, ...]:
    """Audit one Python source file."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    visitor = _AuditVisitor(display or path.name)
    visitor.visit(tree)
    return tuple(visitor.findings)


def audit_sources(
    paths: Iterable[Path],
    *,
    root: Path | None = None,
) -> SafetyReport:
    """Audit a set of source files and collect all findings."""
    files: list[str] = []
    findings: list[SafetyFinding] = []
    calls = 0
    base = root.resolve() if root is not None else None
    for path in sorted(set(paths)):
        resolved = path.resolve()
        if base is not None and resolved.is_relative_to(base):
            display = str(resolved.relative_to(base))
        else:
            display = resolved.name
        files.append(display)
        text = resolved.read_text(encoding="utf-8")
        visitor = _AuditVisitor(display)
        visitor.visit(ast.parse(text, filename=str(resolved)))
        findings.extend(visitor.findings)
        calls += visitor.calls_checked
    return SafetyReport(
        files=tuple(files),
        findings=tuple(findings),
        calls_checked=calls,
    )


def package_sources(root: Path | None = None) -> tuple[Path, ...]:
    """Return every Python file owned by this SDK and its namespace route."""
    base = root or Path(__file__).resolve().parent
    sdk_dir = Path(base)
    sources = sorted(sdk_dir.glob("*.py"))
    namespace = sdk_dir.parent / "namespaces" / "extensions.py"
    if namespace.is_file():
        sources.append(namespace)
    return tuple(sources)


def assert_no_code_execution(paths: Iterable[Path] | None = None) -> SafetyReport:
    """Raise when any audited source contains a code execution path."""
    sources = tuple(paths) if paths is not None else package_sources()
    report = audit_sources(sources, root=Path(__file__).resolve().parent.parent)
    if not report.clean:
        details = "; ".join(f"{item.path}:{item.line} {item.symbol}" for item in report.findings)
        raise SafetyViolationError(f"Code execution invariant violated: {details}")
    return report
