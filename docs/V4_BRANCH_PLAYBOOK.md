# RedScribe v4 Branch Playbook

**Baseline:** `V4_BASELINE` = `c2123b9`
**Naming:** `dev/v4-XX-slug`
**Only `dev/*` is pushed. Never push `main`. Never force-push a shared branch.**

## 1. Day-zero checklist

```bash
git fetch origin --prune
git rev-parse HEAD > /tmp/opencode/v4-baseline.txt
git status --porcelain
git switch -c dev/v4-master-plan
```

## 2. Cutting a branch

```bash
BASE=$(cat /tmp/opencode/v4-baseline.txt)
git worktree add -b dev/v4-01-capture-inbox /tmp/opencode/v4wt/wt01 "$BASE"
ln -s "$PWD/frontend/node_modules" /tmp/opencode/v4wt/wt01/frontend/node_modules
```

Each branch is cut from the fixed baseline, not from the previous branch. This
keeps LOC measurable and makes integration deterministic.

## 3. Required contents per branch

1. **Implementation** under `src/redscribe/v4/<slug>/` (models, service, storage, api).
2. **Tests** under `tests/v4_<slug>/`.
3. **Frontend slice** under `frontend/src/features/<slug>/` + CSS.
4. **Frontend test** under `frontend/scripts/v4-<slug>.test.ts`.
5. **Manifest** `frontend/scripts/test-suites/v4-XX.json`.
6. **Docs** `docs/v4/<slug>.md`.

## 4. Conflict rules

- Never edit `src/redscribe/v4/__init__.py` (dynamic discovery picks you up).
- Never edit `frontend/scripts/test.mjs` (manifests are the extension point).
- Never edit another branch's manifest, CSS, or docs.
- Never edit `frontend/src/styles/tokens-v4.css`; import it.

## 5. Gates

```bash
python3 -m ruff check .
python3 -m ruff format --check .
PYTHONPATH=src python3 -m mypy src
PYTHONPATH=src python3 -m pytest -q -p no:asyncio
cd frontend && npm test
cd frontend && npm run format:check
cd frontend && npm run typecheck
cd frontend && npm run build
python3 scripts/loc_gate.py --baseline "$BASE" --min-net 2500 --min-test-loc 400
```

## 6. Commit discipline

- Commit only intended files.
- Never stage `node_modules`, `.venv`, build output, or tool state.
- Commit message: `feat(v4): <slug> — <one-line outcome>`.

## 7. Integration

1. Fetch and merge `main` into the feature branch.
2. Resolve conflicts with the canonical universal files (contracts, registries, tokens).
3. Re-run all gates.
4. Commit the merge and push only the `dev/*` branch.
5. Open a PR into `main`; do not merge from the working tree.
