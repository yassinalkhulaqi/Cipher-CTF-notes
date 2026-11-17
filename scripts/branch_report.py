from __future__ import annotations

import argparse
import json
from collections import defaultdict

from loc_gate import FileChange, collect, emit, resolve_base, summarize

GROUPS = {
    "backend": ("src/redscribe/",),
    "frontend": ("frontend/src/",),
    "tests": ("tests/", "frontend/scripts/"),
    "scripts": ("scripts/",),
}


def group_changes(changes: list[FileChange]) -> dict[str, list[FileChange]]:
    grouped: dict[str, list[FileChange]] = defaultdict(list)
    for change in changes:
        path = change.path
        if path.startswith(GROUPS["tests"]):
            grouped["tests"].append(change)
        elif path.startswith(GROUPS["backend"]):
            grouped["backend"].append(change)
        elif path.startswith(GROUPS["frontend"]):
            grouped["frontend"].append(change)
        elif path.startswith(GROUPS["scripts"]):
            grouped["scripts"].append(change)
        else:
            grouped["other"].append(change)
    return dict(grouped)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report per-branch change mix.")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    changes = collect(args.base)
    summary = summarize(changes)
    grouped = group_changes(changes)
    payload = {
        "base": resolve_base(args.base),
        "summary": summary,
        "groups": {
            name: {
                "files": len(items),
                "added": sum(change.added for change in items),
                "deleted": sum(change.deleted for change in items),
            }
            for name, items in grouped.items()
        },
    }

    if args.json:
        emit(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    emit(f"Branch report vs {payload['base'][:12]}")
    emit(f"{'group':<10} {'files':>6} {'added':>8} {'deleted':>8}")
    for name in ("backend", "frontend", "tests", "scripts", "other"):
        stats = payload["groups"].get(name)
        if stats is None:
            continue
        emit(f"{name:<10} {stats['files']:>6} {stats['added']:>8} {stats['deleted']:>8}")
    emit(f"{'TOTAL':<10} {summary['files']:>6} {summary['added']:>8} {summary['deleted']:>8}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
