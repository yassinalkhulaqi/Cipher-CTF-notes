# RedScribe v4 Quality Gates

These gates are mandatory for every `dev/v4-*` branch. Never disable or weaken a
gate to make a branch pass.

## 1. Python

```bash
python3 -m ruff check .
python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
```

- Ruff: `E,F,W,I,N,UP,B,A,C4,DTZ,T10,T20,SIM,PT,RUF`, line length 100, double quotes.
- mypy: strict, `python_version = 3.10`, `warn_unreachable`.
- pytest: strict markers/config, warnings as errors, `PYTHONPATH=src`.

## 2. Frontend

```bash
cd frontend
npm test
npm run format:check
npm run typecheck
npm run build
```

- Tests are `node --test` bundles selected by `scripts/test-suites/*.json`.
- `REDSCRIBE_SKIP_TYPECHECK=1` is a local triage escape hatch only; CI always typechecks.

## 3. LOC gate

```bash
python3 scripts/loc_gate.py --baseline V4_BASELINE --min-net 2500 --min-test-loc 400
python3 scripts/loc_gate.py --aggregate \
  --baseline V4_BASELINE --branches dev/v4-01-...,dev/v4-02-... \
  --min-net 2500 --program-min-net 25000
```

- Net LOC = additions − deletions against the fixed baseline.
- Lockfiles, generated static assets, and `node_modules` are excluded.
- The gate rejects a seeded 2,499-net branch.

## 4. Gate failures

If a gate is blocked by the environment, record the exact command and failure
output, then retry when the environment recovers. Do not skip the gate.
