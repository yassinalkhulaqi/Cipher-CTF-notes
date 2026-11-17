# Branch Playbook

The V2 work is a 12-step branch train. Every branch is based on the tip of its
predecessor, lands through the full gate, and is merged in numeric order.

## Branch train

| Branch | Theme | Base |
| --- | --- | --- |
| `dev/v2-00-platform-kernel` | Rescue, schema v4, API v2, UI primitives, gates | `main` |
| `dev/v2-01-engagement-core` | Engagements, targets, assets, services, findings | B00 |
| `dev/v2-02-evidence-vault` | Evidence records, hashing, attachments, chain of custody | B01 |
| `dev/v2-03-block-editor` | Block model, editor engine, autosave, mentions | B02 |
| `dev/v2-04-search-commands` | Search index, command palette, saved queries | B03 |
| `dev/v2-05-playbooks-snippets` | Playbooks, snippets, templates, variables | B04 |
| `dev/v2-06-graph-intel` | Graph model, link intelligence, clustering | B05 |
| `dev/v2-07-reporting-studio` | Report builder, exports, redaction, print | B06 |
| `dev/v2-08-sync-portability` | Backup, restore, import/export, conflict handling | B07 |
| `dev/v2-09-security-privacy` | Encryption at rest, secrets, privacy modes | B08 |
| `dev/v2-10-a11y-i18n-themes` | Accessibility, localization, theming | B09 |
| `dev/v2-11-performance-offline` | Benchmarks, offline mode, large-vault tuning | B10 |

## Naming and remote policy

Local experiments may use any name, but only `dev/*` branches may be pushed to
`origin`. The server rejects other names with:

```text
BLOCKED: only dev/* branches may be pushed
```

Use `dev/v2-NN-short-theme`. Do not push `main`. Do not force-push a shared
branch. Do not rewrite a branch after review has started without telling the
reviewer.

## Starting a branch

```bash
git switch main
git pull --ff-only origin main
git switch -c dev/v2-01-engagement-core
```

For later branches, base on the merged predecessor rather than `main` until the
train is complete:

```bash
git switch dev/v2-00-platform-kernel
git pull --ff-only origin dev/v2-00-platform-kernel
git switch -c dev/v2-01-engagement-core
```

## Rescue and salvage

Dirty work found before B00 was preserved on `wip/aurora-editor-a11y` in commit
`e84c977`. That branch is local-only and contains the editor engine and
accessibility experiments. Its files are intentionally not part of B00 so the
baseline stays green.

Untracked tool state under `.autonomous/` and `.opencode/` is ignored by the
gate. `.agent/` is excluded via `.git/info/exclude`; the canonical plan is
`docs/V2_MASTER_PLAN.md` on `dev/v2-master-plan`.

## Stale branches

The repository has many old `feat/*`, `agent/*`, and `fix/*` branches. Triage
rules:

1. Keep any branch with unique work not present on `origin/main`.
2. Salvage unique commits with `git cherry-pick` onto the owning v2 branch.
3. Delete the stale branch only after its content is reachable from a v2 branch.
4. Never delete `wip/*` rescue branches before the owning feature branch lands.

## Merge discipline

- One branch, one theme. Unrelated fixes go in their own small PR.
- Rebase on the predecessor before opening a PR; merge after green gates.
- Keep migrations append-only and namespace reservations documented.
- Shared primitives change only in B00 or a reviewed cross-cutting branch.
- Every branch must add at least 4,000 code lines and 500 test lines.

## PR checklist

- [ ] Branch name starts with `dev/`.
- [ ] `python scripts/loc_gate.py --base origin/main --min-added 4000 --min-tests 500` passes.
- [ ] `python scripts/branch_report.py --base origin/main` shows the expected mix.
- [ ] API changes are documented in `docs/API_V2.md`.
- [ ] New routes, migrations, or primitives are registered in their registry.
- [ ] Full CI is green.
