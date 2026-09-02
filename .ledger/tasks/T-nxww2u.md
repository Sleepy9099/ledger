---
id: T-nxww2u
title: Remove dead ## Commits lines: scan --prune and ledger unlink, with a Log line each
status: todo
priority: p1
size: s
created: 2026-09-02T08:54:43Z
tags: integrity
---

## Spec

### Defect (heavy-session feedback 2026-09-02, #2; verified)

Nothing removes a `## Commits` line: `_link_commits` and `scan --write` only append, and `sha-unreachable`'s fix_hint claims `scan --write re-materializes live links`, which does not touch dead pointers. The only repair was a hand rewrite of 42 lines across 35 files — an operation the protocol forbids. (Removing a Commits line cannot trip log-tamper: `_tamper_violations` only collects removals matching LOG_LINE_RE.)

### Design

- `ledger scan --prune` (implies `--write`): after backfilling, drop every cited sha that is not reachable from HEAD (the same set as #1), appending `unlink: <sha7> (unreachable from HEAD after a history rewrite)` to each affected task's Log — auditable, one file per task, skips structurally broken files like `--write` does. Reports `pruned: [{task, sha}]`.
- `ledger unlink <id> <sha>...`: explicit single removal with `unlink: <sha7> <reason>` (optional `--why`); refuses `no-such-commit-line` when the sha is not cited. Removing live evidence is loud, not silent: `done-evidence` / `coverage` catch a task or commit that loses its last link.
- `sha-unreachable` fix_hint: "normal after a history rewrite: `ledger scan --prune` drops dead pointers (each removal is journaled) and `scan --write` re-adds live trailer links".
- DESIGN §2 (`## Commits` stays append-only in the ordinary flow; prune/unlink are the journaled exceptions), README rows, PROTOCOL "after any merge or rebase" line names `--prune` (protocol bump; size pin).
- Tests: prune after a rewrite leaves reachable lines, removes dead ones, journals each, is idempotent, strict validate goes green; unlink refusals and Log line; done-evidence after unlinking the last commit.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-09-02T08:54:43Z [claude-2026-09-01-b] add: created: Remove dead ## Commits lines: scan --prune and ledger unlink, with a Log line each [p1/s] (tags: integrity)
