from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("loc_gate", ROOT / "scripts" / "loc_gate.py")
assert _SPEC is not None
assert _SPEC.loader is not None
loc_gate = importlib.util.module_from_spec(_SPEC)
sys.modules["loc_gate"] = loc_gate
_SPEC.loader.exec_module(loc_gate)

FileChange = loc_gate.FileChange


def test_normalize_path_handles_plain_and_brace_renames() -> None:
    assert loc_gate.normalize_path("src/old.py => src/new.py") == "src/new.py"
    assert loc_gate.normalize_path("src/{old => new}/file.py") == "src/new/file.py"


def test_is_countable_excludes_generated_and_lockfiles() -> None:
    assert loc_gate.is_countable("src/redscribe/domain.py")
    assert loc_gate.is_countable("frontend/src/ui/Button.tsx")
    assert loc_gate.is_countable("frontend/scripts/router.test.ts")
    assert not loc_gate.is_countable("frontend/package-lock.json")
    assert not loc_gate.is_countable("src/redscribe/ui/web/static/assets/app.css")
    assert not loc_gate.is_countable(".autonomous/state.py")
    assert not loc_gate.is_countable("docs/demo.png")


def test_parse_numstat_keeps_only_countable_rows() -> None:
    text = "12\t3\tsrc/redscribe/domain.py\n-\t-\tdocs/demo.png\n20\t0\ttests/test_api.py\n"
    changes = loc_gate.parse_numstat(text)
    assert [(change.path, change.added) for change in changes] == [
        ("src/redscribe/domain.py", 12),
        ("tests/test_api.py", 20),
    ]


def test_summarize_counts_code_and_tests_separately() -> None:
    changes = [
        FileChange("src/redscribe/domain.py", 100, 5),
        FileChange("frontend/src/ui/Button.tsx", 50, 0),
        FileChange("tests/test_api.py", 30, 0),
        FileChange("frontend/scripts/router.test.ts", 20, 0),
    ]
    summary = loc_gate.summarize(changes)
    assert summary["added"] == 200
    assert summary["code_added"] == 150
    assert summary["tests_added"] == 50
    assert summary["code_files"] == 2
    assert summary["test_files"] == 2


def test_evaluate_reports_each_shortfall() -> None:
    summary = {"added": 3999, "tests_added": 100}
    failures = loc_gate.evaluate(summary, 4000, 500)
    assert len(failures) == 2
    assert "3999" in failures[0]
    assert "100" in failures[1]
    assert loc_gate.evaluate({"added": 4000, "tests_added": 500}, 4000, 500) == []
