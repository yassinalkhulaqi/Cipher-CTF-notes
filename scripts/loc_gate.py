from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CODE_SUFFIXES = (".py", ".ts", ".tsx", ".css", ".mjs", ".js", ".jsx")
EXCLUDED_PREFIXES = (
    ".agent/",
    ".autonomous/",
    ".opencode/",
    "frontend/node_modules/",
    "node_modules/",
    "src/redscribe/ui/web/static/",
)
LOCKFILES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "Pipfile.lock",
}
TEST_PREFIXES = ("tests/", "frontend/scripts/")


def emit(line: str) -> None:
    sys.stdout.write(line + "\n")


@dataclass(frozen=True)
class FileChange:
    path: str
    added: int
    deleted: int

    @property
    def is_test(self) -> bool:
        name = Path(self.path).name
        return self.path.startswith(TEST_PREFIXES) and (
            self.path.startswith("tests/") or ".test." in name or name.endswith("_test.py")
        )

    @property
    def is_code(self) -> bool:
        return is_countable(self.path) and not self.is_test


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def normalize_path(path: str) -> str:
    cleaned = path.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if " => " not in cleaned:
        return cleaned
    if "{" in cleaned and "}" in cleaned:
        prefix = cleaned.split("{", 1)[1].split("}", 1)[0]
        right = prefix.split(" => ", 1)[1]
        return cleaned.replace("{" + prefix + "}", right)
    return cleaned.split(" => ", 1)[1].strip()


def is_countable(path: str) -> bool:
    cleaned = normalize_path(path)
    if not cleaned or cleaned.startswith(EXCLUDED_PREFIXES):
        return False
    if Path(cleaned).name in LOCKFILES:
        return False
    if "/__snapshots__/" in cleaned or cleaned.endswith((".snap", ".png", ".jpg", ".svg")):
        return False
    return cleaned.endswith(CODE_SUFFIXES)


def parse_numstat(text: str) -> list[FileChange]:
    changes: list[FileChange] = []
    for line in text.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if not added.isdigit() or not deleted.isdigit() or not is_countable(path):
            continue
        changes.append(FileChange(normalize_path(path), int(added), int(deleted)))
    return changes


def untracked_changes() -> list[FileChange]:
    changes: list[FileChange] = []
    for raw in _git("ls-files", "--others", "--exclude-standard").splitlines():
        path = normalize_path(raw)
        if not is_countable(path):
            continue
        absolute = ROOT / path
        if not absolute.is_file():
            continue
        try:
            added = len(absolute.read_text(encoding="utf-8").splitlines())
        except OSError:
            continue
        changes.append(FileChange(path, added, 0))
    return changes


def resolve_base(base: str) -> str:
    return _git("merge-base", base, "HEAD").strip()


def collect(base: str) -> list[FileChange]:
    base_commit = resolve_base(base)
    changes = parse_numstat(_git("diff", "--numstat", base_commit, "--"))
    seen = {change.path for change in changes}
    for change in untracked_changes():
        if change.path not in seen:
            changes.append(change)
    return changes


def summarize(changes: list[FileChange]) -> dict[str, int]:
    code = [change for change in changes if change.is_code]
    tests = [change for change in changes if change.is_test]
    added = sum(change.added for change in changes)
    deleted = sum(change.deleted for change in changes)
    return {
        "files": len(changes),
        "code_files": len(code),
        "test_files": len(tests),
        "added": added,
        "deleted": deleted,
        "net": added - deleted,
        "code_added": sum(change.added for change in code),
        "code_deleted": sum(change.deleted for change in code),
        "tests_added": sum(change.added for change in tests),
        "tests_deleted": sum(change.deleted for change in tests),
    }


def evaluate(
    summary: dict[str, int],
    min_added: int,
    min_tests: int,
    min_net: int = 0,
) -> list[str]:
    failures: list[str] = []
    if summary["added"] < min_added:
        failures.append(f"added {summary['added']} lines, need at least {min_added}")
    if summary["tests_added"] < min_tests:
        failures.append(f"added {summary['tests_added']} test lines, need at least {min_tests}")
    if min_net and summary["net"] < min_net:
        failures.append(f"net {summary['net']} lines, need at least {min_net}")
    return failures


def collect_against(ref: str, baseline: str) -> list[FileChange]:
    """Collect committed changes between an exact baseline and a branch ref."""
    return parse_numstat(_git("diff", "--numstat", baseline, ref, "--"))


def aggregate(branches: list[str], baseline: str) -> tuple[list[dict[str, int]], dict[str, int]]:
    """Summarize each branch and the whole program against one baseline."""
    rows: list[dict[str, int]] = []
    for branch in branches:
        summary = summarize(collect_against(branch, baseline))
        summary["net"] = summary["added"] - summary["deleted"]
        rows.append(summary)
    totals = {
        key: sum(row[key] for row in rows)
        for key in (
            "files",
            "code_files",
            "test_files",
            "added",
            "deleted",
            "net",
            "code_added",
            "code_deleted",
            "tests_added",
            "tests_deleted",
        )
    }
    return rows, totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce per-branch LOC budgets.")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--baseline", default="", help="Exact V3 baseline ref.")
    parser.add_argument("--min-added", type=int, default=4000)
    parser.add_argument("--min-tests", type=int, default=500)
    parser.add_argument("--min-net", type=int, default=0)
    parser.add_argument("--min-test-loc", type=int, default=0)
    parser.add_argument("--aggregate", action="store_true", help="Aggregate all branches.")
    parser.add_argument("--branches", default="", help="Comma-separated branch refs.")
    parser.add_argument("--program-min-net", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="Emit a JSON summary.")
    args = parser.parse_args(argv)

    if args.aggregate:
        baseline = args.baseline or resolve_base(args.base)
        branch_list = [item.strip() for item in args.branches.split(",") if item.strip()]
        rows, totals = aggregate(branch_list, baseline)
        failures: list[str] = []
        for branch, row in zip(branch_list, rows, strict=True):
            row["branch"] = branch
            if row["net"] < args.min_net:
                failures.append(f"{branch}: net {row['net']} < {args.min_net}")
            if row["tests_added"] < (args.min_test_loc or args.min_tests):
                failures.append(
                    f"{branch}: test lines {row['tests_added']} < "
                    f"{args.min_test_loc or args.min_tests}"
                )
        if totals["net"] < args.program_min_net:
            failures.append(f"program net {totals['net']} < {args.program_min_net}")
        payload = {
            "baseline": baseline,
            "branches": rows,
            "totals": totals,
            "ok": not failures,
            "failures": failures,
        }
        if args.json:
            emit(json.dumps(payload, indent=2, sort_keys=True))
        else:
            emit(f"V3 program LOC gate vs {baseline[:12]}")
            for row in rows:
                emit(
                    f"  {row['branch']}: net {row['net']} "
                    f"(added {row['added']}, tests {row['tests_added']})"
                )
            emit(f"  TOTAL net: {totals['net']} / {args.program_min_net} ({len(rows)} branches)")
            for failure in failures:
                emit(f"  FAIL: {failure}")
            if not failures:
                emit("  PASS")
        return 1 if failures else 0

    base_ref = args.baseline or args.base
    changes = collect(base_ref)
    summary = summarize(changes)
    failures = evaluate(
        summary,
        args.min_added,
        args.min_tests or args.min_test_loc,
        args.min_net,
    )
    summary["base"] = resolve_base(base_ref) if not args.baseline else base_ref
    summary["ok"] = not failures
    summary["failures"] = failures

    if args.json:
        emit(json.dumps(summary, indent=2, sort_keys=True))
    else:
        emit(f"LOC gate vs {summary['base'][:12]}")
        emit(
            f"  files: {summary['files']} "
            f"(code {summary['code_files']}, tests {summary['test_files']})"
        )
        emit(f"  added: {summary['added']} / {args.min_added}")
        if args.min_net:
            emit(f"  net: {summary['net']} / {args.min_net}")
        emit(f"  test lines: {summary['tests_added']} / {args.min_tests or args.min_test_loc}")
        emit(f"  deleted: {summary['deleted']}")
        if failures:
            for failure in failures:
                emit(f"  FAIL: {failure}")
        else:
            emit("  PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
