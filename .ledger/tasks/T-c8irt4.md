---
id: T-c8irt4
title: Historical append-only Log verification
status: todo
priority: p1
size: m
created: 2026-08-28T11:54:59Z
tags: integrity
---

## Spec

Replace the baseline->worktree net-diff log-tamper check with commit-by-commit verification: for every commit in scope, diff parent->commit under .ledger/tasks/ and flag (a) removed/modified Log lines not re-added in that same commit, (b) task-file deletions. Keep the existing baseline->worktree pass so UNCOMMITTED tampering is still caught pre-commit.

Why: the current net diff cannot see a Log line that was added after baseline and later deleted (add-then-delete nets out). The intended invariant: once a Log event enters repository history, no later state may remove or alter it.

Implementation notes:
- One 'git log -p <range> -- .ledger/tasks/' pass (with -c diff.noprefix=false -c core.quotePath=false --no-ext-diff) parses per-commit patches without N subprocesses.
- Merge commits: plain log -p omits merge diffs; diff the merge against EACH parent - any parent's Log line missing from the merge result is a violation (the keep-both-sides rule makes this exact).
- Stays warning-tier under code log-tamper (strict promotes). Regression tests: add->commit->delete->commit history must fail; keep-both merge resolution must stay clean.

## Next Steps

## Open Questions

## Commits

## Log

- 2026-08-28T11:54:59Z [claude-2026-08-28-a] add: created: Historical append-only Log verification
