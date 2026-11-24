"""Static proof that the SDK and extensions namespace cannot execute code."""

from __future__ import annotations

from pathlib import Path

import pytest

from redscribe.v3.api_sdk.errors import SafetyViolationError
from redscribe.v3.api_sdk.safety import (
    FORBIDDEN_CALLS,
    FORBIDDEN_IMPORTS,
    SafetyReport,
    assert_no_code_execution,
    audit_source,
    audit_sources,
    package_sources,
)


def _write(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_package_sources_cover_sdk_and_namespace() -> None:
    sources = package_sources()
    names = [path.name for path in sources]
    assert "cli.py" in names
    assert "client.py" in names
    assert "extensions.py" in names
    assert all(path.suffix == ".py" for path in sources)


def test_shipped_sources_are_clean() -> None:
    report = assert_no_code_execution()
    assert isinstance(report, SafetyReport)
    assert report.clean
    assert report.calls_checked > 0
    assert len(report.files) >= 10
    assert report.as_dict()["findings"] == []


@pytest.mark.parametrize(
    "source",
    [
        "result = eval('1 + 1')\n",
        "exec('x = 1')\n",
        "code = compile('1', 'x', 'eval')\n",
        "__import__('os')\n",
        "import subprocess\n",
        "from os import system\n",
        "import pickle\npickle.loads(b'x')\n",
        "import socket\nsocket.socket()\n",
        "fn = lambda x: x\n",
    ],
)
def test_forbidden_constructs_are_found(tmp_path: Path, source: str) -> None:
    path = _write(tmp_path, "unsafe.py", source)
    findings = audit_source(path)
    assert findings
    assert all(finding.line >= 1 for finding in findings)
    assert findings[0].as_dict()["symbol"]


def test_path_level_forbidden_calls_are_found(tmp_path: Path) -> None:
    source = "import os\nos.system('echo hi')\n"
    findings = audit_source(_write(tmp_path, "process.py", source))
    symbols = {item.symbol for item in findings}
    assert "os" in symbols
    assert "os.system" in symbols


def test_auditing_many_files_aggregates(tmp_path: Path) -> None:
    clean = _write(tmp_path, "clean.py", "value = 1 + 1\n")
    unsafe = _write(tmp_path, "unsafe.py", "value = eval('1 + 1')\n")
    report = audit_sources([clean, unsafe], root=tmp_path)
    assert not report.clean
    assert report.files == ("clean.py", "unsafe.py")
    assert report.findings[0].path == "unsafe.py"
    assert report.as_dict()["calls_checked"] >= 1


def test_assert_raises_on_unsafe_sources(tmp_path: Path) -> None:
    unsafe = _write(tmp_path, "unsafe.py", "exec('x = 1')\n")
    with pytest.raises(SafetyViolationError) as excinfo:
        assert_no_code_execution([unsafe])
    assert "exec" in excinfo.value.message
    assert excinfo.value.status == 403


def test_forbidden_catalogs_are_stable() -> None:
    assert {"eval", "exec", "__import__"} <= FORBIDDEN_CALLS
    assert {"subprocess", "socket", "pickle", "os", "importlib"} <= FORBIDDEN_IMPORTS
