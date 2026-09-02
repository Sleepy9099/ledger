---
id: T-cnpl6r
title: Prune safety: reachability from every ref, shallow refusal, last-evidence guard, replacement candidates
status: todo
priority: p1
size: s
created: 2026-09-02T11:44:57Z
tags: integrity
---

## Spec

### Defects (sweep 2026-09-02, correctness #1, orchestration #3; verified by the reviewers)

`scan --prune` and `sha-unreachable` decide from `git rev-list HEAD` only. That is right after a rewrite but wrong (a) on a shallow clone — validate refuses those, prune does not, and the sha-unreachable hint even recommends prune "or a shallow clone" — and (b) on a worker branch that does not contain other tasks' commits: prune deleted real evidence in both cases. After a squash merge, `scan --write --prune` removed a done task's last evidence (nothing backfilled, the squash message quotes trailers mid-body) and left `done-evidence` red.

### Design

- `reachable_index` walks `git rev-list --branches --tags --remotes` (fallback HEAD): every fetched ref counts, refs/original/* and the reflog do not, so the rewriter's checkout and a clone still agree while worker branches present locally keep their evidence.
- `scan --prune` refuses on a shallow clone (`coverage`-style refusal, exit 2).
- Prune never removes the LAST ## Commits line of a done task unless that task was backfilled in the same run; such tasks are reported in `prune_refused: [{task, sha, replacement_candidates}]` with an error-severity row naming `ledger link <id> <sha>`; replacement candidates = reachable commits whose subject equals the pruned line's subject (a hint the agent confirms, never an automatic link).
- sha-unreachable fix_hint drops "or a shallow clone" and names the guard.
- Tests: shallow refusal; worker-branch evidence survives; squash-merge case refuses and names candidates; the rewrite case still prunes.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T11:44:57Z [claude-2026-09-01-b] add: created: Prune safety: reachability from every ref, shallow refusal, last-evidence guard, replacement candidates [p1/s] (tags: integrity)
