# V3 Branch Playbook

## Train

`dev/v3-00-platform-kernel` → `dev/v3-14-polish-release`. The plan is on
`dev/v3-master-plan`; baseline is `main` at `c65e699`.

| Branch | Theme |
| --- | --- |
| `dev/v3-00-platform-kernel` | universal entities, events, API v3, schema v5, gates, tokens |
| `dev/v3-01-command-center` | command bar, navigation, focus mode, panes |
| `dev/v3-02-finding-studio` | finding lifecycle, CVSS v4, remediation, retest |
| `dev/v3-03-evidence-lab` | hex, strings, hashes, custody, bundle diff |
| `dev/v3-04-graph-workbench` | layouts, clusters, paths, relationship editor |
| `dev/v3-05-search-intelligence` | query v2, facets, pivots, saved searches |
| `dev/v3-06-playbook-automation` | DAG engine, traced dry-run, variables, runs |
| `dev/v3-07-report-designer` | page designer, themes, pagination, exports |
| `dev/v3-08-timeline-activity` | event stream, filters, digests, retrospection |
| `dev/v3-09-sync-portability-pro` | encrypted bundles, vectors, 3-way merge |
| `dev/v3-10-security-vault` | encryption lifecycle, keys, recovery, policy |
| `dev/v3-11-performance-scale` | virtualization, incremental index, budgets |
| `dev/v3-12-a11y-i18n-refinement` | WCAG, RTL, locales, theme/motion unification |
| `dev/v3-13-extensibility-cli` | SDK, scripting CLI, data-only manifests |
| `dev/v3-14-polish-release` | onboarding, design system, golden-path E2E |

## Rules

1. Only `dev/*` branches are pushed. Never push `main`; never force-push.
2. Each branch adds ≥ 2,000 net LOC (targets in `docs/V3_MASTER_PLAN.md` are
   higher) and ≥ 600 test LOC.
3. Each branch has: domain logic, services, tests, frontend feature, CSS, docs,
   and its own `frontend/scripts/test-suites/NN.json`.
4. Shared files are additive registries (§4 of `docs/V3_ARCHITECTURE.md`).
5. Run every gate before push. If a gate is environment-blocked, record the
   exact command and failure; never skip or weaken it.
6. Merge numeric order. Rebase on the merged predecessor before opening a PR.

## Worktrees

```bash
mkdir -p /tmp/opencode/v3wt
git worktree add -b dev/v3-NN-slug /tmp/opencode/v3wt/wtNN dev/v3-00-platform-kernel
```

Never stage `node_modules` or generated bundles. Rebuild the frontend bundle
with `npm run build` after CSS changes.
