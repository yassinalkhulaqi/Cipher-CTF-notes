# Quality Gates

Every V2 and V3 branch must pass the same gates locally and in CI. A red gate
blocks merge; do not work around it with skips or generated-file edits.

## V3 additions

V3 branches measure **net** LOC against `V3_BASELINE` (`main` at `c65e699`):

```bash
python scripts/loc_gate.py --baseline c65e699 --min-net 2000 --min-test-loc 600
python scripts/loc_gate.py --baseline c65e699 --aggregate \
  --branches dev/v3-00-platform-kernel,... --program-min-net 30000
python scripts/branch_report.py --baseline c65e699
```

V3 tests live in `tests/v3_*` packages and `frontend/scripts/v3*.test.ts`. Each
V3 branch registers its frontend tests in
`frontend/scripts/test-suites/NN.json`. All V3 Python modules live under
`src/redscribe/v3/`, and V3 frontend code under `frontend/src/v3/` or
`frontend/src/features/<name>/`.

## Automated commands

```bash
# Python
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
python3 -m ruff check .
python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src

# Frontend
cd frontend
npm ci
npm test
npm run format:check
npm run typecheck
npm run build

# Packaging
python -m build
python scripts/smoke_web.py

# Branch accounting
python scripts/loc_gate.py --base origin/main --min-added 4000 --min-tests 500
python scripts/branch_report.py --base origin/main
```

`-p no:asyncio` is required locally because this environment treats pytest
warnings as errors. CI installs the dev extra and runs pytest normally.

## LOC gate

`scripts/loc_gate.py` compares the working tree with the merge base of
`origin/main` and `HEAD`.

- Counts `.py`, `.ts`, `.tsx`, `.css`, `.mjs`, `.js`, and `.jsx`.
- Excludes lockfiles, snapshots, images, generated bundle output, and tool state.
- Counts files under `tests/` and `frontend/scripts/*.test.ts` as test lines.
- Requires at least 4,000 added code lines per branch.
- Requires at least 500 added test lines per branch.

Use `--json` for machine-readable output. `scripts/branch_report.py` prints the
backend/frontend/tests/scripts mix and is the human-readable companion.

## CI jobs

| Job | Checks |
| --- | --- |
| `test` | CLI smoke tests, ruff, format, mypy, pytest with coverage |
| `contracts` | v2 API, migration, event, and idempotency contract suites |
| `frontend` | Prettier, unit tests, typecheck, build, committed bundle freshness |
| `gates` | LOC floor, test-line floor, branch report |
| `package` | Wheel build, install smoke test, web smoke test |

Python matrix: 3.10, 3.11, 3.12, 3.13, plus Windows 3.12. Node: 20.

## Coverage

The pytest job requires 85% total coverage. New storage and API modules must be
covered by contract tests, not only incidental coverage from integration tests.
Idempotency, migration chains, cursor decoding, and error envelopes have
dedicated tests.

## Manual checks

Before merging a UI branch:

- Keyboard-only pass through new primitives and routes.
- Screen-reader labels on dialogs, menus, tables, toasts, and icon buttons.
- Reduced-motion mode leaves content usable.
- Both themes keep sufficient contrast for new surfaces.
- Existing v1 flows still work without a hard refresh.

Before merging a storage branch:

- Upgrade a fresh v1, v2, and v3 vault to the new schema.
- Confirm a downgrade is not attempted silently.
- Verify backup/restore round-trips the new tables.
- Confirm migrations are append-only and checksummed.

## Exit criteria for B00

- Clean checkout passes every gate above.
- v1 frontend behavior is unchanged.
- v2 routes are callable over HTTP with stable envelopes.
- LOC gate rejects a seeded 3,999-line branch.
- Branch backlog triage is documented in `docs/BRANCH_PLAYBOOK.md`.
